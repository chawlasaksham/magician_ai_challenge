"""
magicpin AI Challenge — Vera Bot HTTP Service
Exposes the 5 required endpoints conforming to challenge specifications:
- GET  /v1/healthz
- GET  /v1/metadata
- POST /v1/context
- POST /v1/tick
- POST /v1/reply
- POST /v1/teardown (optional cleanup)
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from composer import VeraComposer
from context_store import ContextStore
from conversation_manager import ConversationManager

# Application initialization
app = FastAPI(title="magicpin Vera AI Assistant", version="1.0.0")
START_TIME = time.time()

# Core singletons
context_store = ContextStore()
conv_manager = ConversationManager()
composer = VeraComposer()


# =====================================================================
# REQUEST & RESPONSE MODELS
# =====================================================================

class ContextPayload(BaseModel):
    scope: str
    context_id: str
    version: int
    payload: Dict[str, Any]
    delivered_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class TickPayload(BaseModel):
    now: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    available_triggers: List[str] = Field(default_factory=list)


class ReplyPayload(BaseModel):
    conversation_id: str
    merchant_id: Optional[str] = None
    customer_id: Optional[str] = None
    from_role: str = "merchant"
    message: str
    received_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    turn_number: int = 1


# =====================================================================
# 1. GET /v1/healthz (Liveness & Context Count Probe)
# =====================================================================

@app.get("/v1/healthz")
async def healthz():
    uptime = int(time.time() - START_TIME)
    counts = context_store.counts()
    return {
        "status": "ok",
        "uptime_seconds": uptime,
        "contexts_loaded": counts,
    }


# =====================================================================
# 2. GET /v1/metadata (Bot Identity & Capabilities)
# =====================================================================

@app.get("/v1/metadata")
async def metadata():
    return {
        "team_name": "Vera Elite",
        "team_members": ["Saksham Chawla"],
        "model": "hybrid-deterministic-llm",
        "approach": "4-context composer with semantic intent routing, verifiable fact anchoring, and sub-3s fallback",
        "contact_email": "team@example.com",
        "version": "1.0.0",
        "submitted_at": "2026-04-26T08:00:00Z",
    }


# =====================================================================
# 3. POST /v1/context (Versioned Context Ingestion & Idempotency)
# =====================================================================

@app.post("/v1/context")
async def push_context(body: ContextPayload):
    if body.scope not in ("category", "merchant", "customer", "trigger"):
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"accepted": False, "reason": "invalid_scope", "details": f"Unknown scope: {body.scope}"}
        )

    accepted, reason, ver = context_store.push(
        scope=body.scope,
        context_id=body.context_id,
        version=body.version,
        payload=body.payload,
        delivered_at=body.delivered_at,
    )

    if not accepted:
        # 409 Conflict for stale versions (incoming < current)
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={
                "accepted": False,
                "reason": "stale_version",
                "current_version": ver,
            }
        )

    return {
        "accepted": True,
        "ack_id": f"ack_{body.context_id}_v{body.version}",
        "stored_at": datetime.now(timezone.utc).isoformat(),
    }


# =====================================================================
# 4. POST /v1/tick (Periodic Wake-Up & Proactive Message Composition)
# =====================================================================

@app.post("/v1/tick")
async def tick(body: TickPayload):
    actions = []

    for trg_id in body.available_triggers:
        trg = context_store.triggers.get(trg_id) or context_store.get("trigger", trg_id)
        if not trg:
            continue

        suppression_key = trg.get("suppression_key", "")
        if suppression_key and context_store.is_suppressed(suppression_key, body.now):
            continue

        # Resolve merchant
        merchant_id = trg.get("merchant_id")
        merchant = context_store.merchants.get(merchant_id) or context_store.get("merchant", merchant_id)
        if not merchant:
            inner_mid = trg.get("payload", {}).get("merchant_id")
            if inner_mid:
                merchant = context_store.merchants.get(inner_mid) or context_store.get("merchant", inner_mid)
        if not merchant:
            continue

        # Resolve category
        category_slug = merchant.get("category_slug") or trg.get("payload", {}).get("category")
        category = context_store.categories.get(category_slug) or context_store.get("category", category_slug) or {}

        # Resolve customer if present
        customer_id = trg.get("customer_id")
        customer = None
        if customer_id:
            customer = context_store.customers.get(customer_id) or context_store.get("customer", customer_id)

        # Retrieve conversation history if exists
        conv_id = f"conv_{merchant.get('merchant_id')}_{trg_id}"
        conv_state = conv_manager.get(conv_id)
        past_sent = conv_state.sent_bodies if conv_state else []

        # Compose action
        action = composer.compose_tick_action(
            category=category,
            merchant=merchant,
            trigger=trg,
            customer=customer,
            past_sent_bodies=past_sent,
        )

        # Register conversation & mark sent
        conv = conv_manager.get_or_create(
            conversation_id=action["conversation_id"],
            merchant_id=merchant.get("merchant_id", ""),
            customer_id=customer_id,
            trigger_id=trg_id,
        )
        conv.record_outbound(action["body"])

        # Mark suppression key active
        if action.get("suppression_key"):
            context_store.suppress(action["suppression_key"], trg.get("expires_at"))

        actions.append(action)

    return {"actions": actions}


# =====================================================================
# 5. POST /v1/reply (Synchronous Multi-Turn Inbound Response)
# =====================================================================

@app.post("/v1/reply")
async def reply(body: ReplyPayload):
    # Resolve or create conversation
    conv = conv_manager.get_or_create(
        conversation_id=body.conversation_id,
        merchant_id=body.merchant_id or "",
        customer_id=body.customer_id,
    )

    # Track inbound message & repetition
    is_conv_dup = conv.record_inbound(
        role=body.from_role,
        message=body.message,
        turn_number=body.turn_number,
    )

    # Track merchant-level consecutive repetition
    merchant_id = body.merchant_id or conv.merchant_id
    consecutive_merchant_count = conv_manager.record_merchant_inbound(
        merchant_id=merchant_id or "default",
        message=body.message,
    )

    effective_consecutive_count = max(
        2 if is_conv_dup else 1,
        consecutive_merchant_count,
        body.turn_number if "thank you for contacting" in body.message.lower() else 1,
    )

    # Resolve merchant and category contexts
    merchant = (
        context_store.merchants.get(merchant_id)
        or context_store.get("merchant", merchant_id)
        or {"merchant_id": merchant_id, "identity": {"name": "Merchant"}}
    )
    category_slug = merchant.get("category_slug", "")
    category = context_store.categories.get(category_slug) or context_store.get("category", category_slug) or {}

    response = composer.compose_reply_action(
        conversation_id=body.conversation_id,
        merchant=merchant,
        category=category,
        message=body.message,
        turn_number=body.turn_number,
        consecutive_same_count=effective_consecutive_count,
        past_sent_bodies=conv.sent_bodies,
    )

    # If action is send, record in conversation state
    if response.get("action") == "send" and response.get("body"):
        conv.record_outbound(response["body"])

    return response


# =====================================================================
# OPTIONAL: POST /v1/teardown (Reset State)
# =====================================================================

@app.post("/v1/teardown")
async def teardown():
    context_store.clear()
    conv_manager.clear()
    return {"status": "ok", "cleared": True}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("bot:app", host="0.0.0.0", port=8080, reload=False)

