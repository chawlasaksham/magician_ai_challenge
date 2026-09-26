"""
Vera Composition Engine for magicpin AI Challenge
Coordinates 4-context resolution, LLM generation with fallback, guardrails, and reply handling.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from deterministic_engine import DeterministicEngine
from guardrails import ComplianceGuard
from intent_detector import IntentDetector, IntentType
from llm_client import LLMClient


class VeraComposer:
    def __init__(self):
        self.llm = LLMClient()

    def compose_tick_action(
        self,
        category: Dict[str, Any],
        merchant: Dict[str, Any],
        trigger: Dict[str, Any],
        customer: Optional[Dict[str, Any]] = None,
        past_sent_bodies: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Compose a proactive message action for /v1/tick."""
        # 1. Try LLM composer if available
        action_data = None
        if self.llm.is_available():
            try:
                action_data = self.llm.compose(category, merchant, trigger, customer)
            except Exception:
                action_data = None

        # 2. Fall back to deterministic engine if LLM unavailable or timed out
        if not action_data or not action_data.get("body"):
            action_data = DeterministicEngine.compose_tick(
                category=category,
                merchant=merchant,
                trigger=trigger,
                customer=customer,
            )

        # 3. Guardrails & Compliance
        body = action_data.get("body", "")
        cleaned_body = ComplianceGuard.clean_body(body, category)

        # Anti-repetition check
        if past_sent_bodies:
            cleaned_body = ComplianceGuard.ensure_unique_body(
                cleaned_body,
                past_sent_bodies,
                merchant.get("identity", {}).get("name", ""),
            )

        cta, _ = ComplianceGuard.validate_cta(action_data.get("cta", "open_ended"), cleaned_body)

        scope = trigger.get("scope", "merchant")
        send_as = "merchant_on_behalf" if (scope == "customer" or customer is not None) else "vera"

        return {
            "conversation_id": action_data.get("conversation_id", f"conv_{merchant.get('merchant_id')}_{trigger.get('id')}"),
            "merchant_id": merchant.get("merchant_id", ""),
            "customer_id": customer.get("customer_id") if customer else trigger.get("customer_id"),
            "send_as": send_as,
            "trigger_id": trigger.get("id", ""),
            "template_name": action_data.get("template_name", "vera_standard_v1"),
            "template_params": action_data.get("template_params", [merchant.get("identity", {}).get("name", "Merchant")]),
            "body": cleaned_body,
            "cta": cta,
            "suppression_key": action_data.get("suppression_key", trigger.get("suppression_key", "")),
            "rationale": action_data.get("rationale", "Composed with 4-context framework"),
        }

    def compose_reply_action(
        self,
        conversation_id: str,
        merchant: Dict[str, Any],
        category: Dict[str, Any],
        message: str,
        turn_number: int,
        consecutive_same_count: int,
        past_sent_bodies: List[str],
    ) -> Dict[str, Any]:
        """Compose response to merchant or customer inbound reply for /v1/reply."""
        intent, detail = IntentDetector.detect(
            message=message,
            consecutive_same_inbound_count=consecutive_same_count,
            turn_number=turn_number,
        )

        m_name = merchant.get("identity", {}).get("name", "there")

        # 1. Auto-reply detection
        if intent == IntentType.AUTO_REPLY:
            if consecutive_same_count >= 2 or turn_number >= 3:
                return {
                    "action": "end",
                    "rationale": f"Detected recurring WhatsApp auto-reply ({detail}); gracefully ending conversation to prevent loops.",
                }
            return {
                "action": "wait",
                "wait_seconds": 14400,
                "rationale": f"Detected WhatsApp Business auto-reply greeting ({detail}); waiting 4 hours for human operator.",
            }

        # 2. Hostile or opt-out
        if intent == IntentType.HOSTILE_OPTOUT:
            return DeterministicEngine.compose_apology_exit()

        # 3. Action commitment (merchant says "let's do it" / "yes send it")
        if intent == IntentType.ACTION_COMMITMENT:
            response = DeterministicEngine.compose_action_reply(m_name)
            response["body"] = ComplianceGuard.clean_body(response["body"], category)
            response["body"] = ComplianceGuard.ensure_unique_body(response["body"], past_sent_bodies, m_name)
            return response

        # 4. Off-topic curveball
        if intent == IntentType.OFF_TOPIC:
            topic_str = detail or "that request"
            response = DeterministicEngine.compose_off_topic_reply(topic_str)
            response["body"] = ComplianceGuard.clean_body(response["body"], category)
            return response

        # 5. Normal conversational follow-up
        body = (
            f"Understood. I am here to help {m_name} grow. "
            f"Here is what we can do next: I can draft a Google post highlighting your services, "
            f"or summarize your recent performance insights. Which would you prefer to see first?"
        )
        body = ComplianceGuard.clean_body(body, category)
        body = ComplianceGuard.ensure_unique_body(body, past_sent_bodies, m_name)

        return {
            "action": "send",
            "body": body,
            "cta": "open_ended",
            "rationale": "Acknowledged merchant reply and offered concrete next actions.",
        }
