"""
Conversation State Manager for magicpin AI Challenge (Vera)
Maintains conversation state, turns, consecutive auto-reply tracking,
intent transitions, and anti-repetition memory per conversation_id.
"""

from __future__ import annotations

import hashlib
import re
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set


def normalize_text(text: str) -> str:
    """Normalize text for repetition comparison."""
    cleaned = re.sub(r'[^\w\s]', '', text.lower())
    return ' '.join(cleaned.split())


@dataclass
class ConversationState:
    conversation_id: str
    merchant_id: str
    customer_id: Optional[str] = None
    trigger_id: Optional[str] = None
    turns: List[Dict[str, Any]] = field(default_factory=list)
    sent_bodies: List[str] = field(default_factory=list)
    sent_hashes: Set[str] = field(default_factory=set)
    consecutive_auto_replies: int = 0
    last_inbound_msg: Optional[str] = None
    last_inbound_role: Optional[str] = None
    mode: str = "normal"  # "normal", "action_execution", "waiting", "ended"
    wait_seconds: int = 0
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def record_outbound(self, body: str):
        norm = normalize_text(body)
        h = hashlib.sha256(norm.encode('utf-8')).hexdigest()
        self.sent_bodies.append(body)
        self.sent_hashes.add(h)
        self.turns.append({
            "from": "vera",
            "body": body,
            "ts": datetime.now(timezone.utc).isoformat()
        })
        self.updated_at = datetime.now(timezone.utc).isoformat()

    def is_repeated(self, body: str) -> bool:
        """Check if this body or a near-verbatim duplicate was already sent in this conversation."""
        norm = normalize_text(body)
        h = hashlib.sha256(norm.encode('utf-8')).hexdigest()
        if h in self.sent_hashes:
            return True
        for sent in self.sent_bodies:
            if norm == normalize_text(sent):
                return True
        return False

    def record_inbound(self, role: str, message: str, turn_number: int) -> bool:
        """
        Record inbound message.
        Returns True if this message is identical to the immediate previous inbound message.
        """
        is_exact_dup = False
        if self.last_inbound_msg is not None:
            if normalize_text(message) == normalize_text(self.last_inbound_msg):
                is_exact_dup = True

        self.last_inbound_msg = message
        self.last_inbound_role = role
        self.turns.append({
            "from": role,
            "msg": message,
            "turn_number": turn_number,
            "ts": datetime.now(timezone.utc).isoformat()
        })
        self.updated_at = datetime.now(timezone.utc).isoformat()
        return is_exact_dup


class ConversationManager:
    def __init__(self):
        self._lock = threading.RLock()
        self._conversations: Dict[str, ConversationState] = {}
        # Also track across merchants to handle merchant-level repetitions if conv_id varies
        self._merchant_last_inbound: Dict[str, str] = {}
        self._merchant_auto_reply_count: Dict[str, int] = {}

    def get_or_create(
        self,
        conversation_id: str,
        merchant_id: str,
        customer_id: Optional[str] = None,
        trigger_id: Optional[str] = None,
    ) -> ConversationState:
        with self._lock:
            if conversation_id not in self._conversations:
                self._conversations[conversation_id] = ConversationState(
                    conversation_id=conversation_id,
                    merchant_id=merchant_id,
                    customer_id=customer_id,
                    trigger_id=trigger_id,
                )
            conv = self._conversations[conversation_id]
            # Update any newly provided linkages
            if merchant_id and not conv.merchant_id:
                conv.merchant_id = merchant_id
            if customer_id and not conv.customer_id:
                conv.customer_id = customer_id
            if trigger_id and not conv.trigger_id:
                conv.trigger_id = trigger_id
            return conv

    def get(self, conversation_id: str) -> Optional[ConversationState]:
        with self._lock:
            return self._conversations.get(conversation_id)

    def record_merchant_inbound(self, merchant_id: str, message: str) -> int:
        """
        Track consecutive identical messages at merchant level.
        Returns the consecutive identical count.
        """
        with self._lock:
            norm = normalize_text(message)
            last = self._merchant_last_inbound.get(merchant_id)
            if last == norm:
                count = self._merchant_auto_reply_count.get(merchant_id, 1) + 1
            else:
                count = 1
            self._merchant_last_inbound[merchant_id] = norm
            self._merchant_auto_reply_count[merchant_id] = count
            return count

    def get_merchant_auto_reply_count(self, merchant_id: str) -> int:
        with self._lock:
            return self._merchant_auto_reply_count.get(merchant_id, 0)

    def reset_merchant_auto_reply_count(self, merchant_id: str):
        with self._lock:
            self._merchant_auto_reply_count[merchant_id] = 0

    def clear(self):
        with self._lock:
            self._conversations.clear()
            self._merchant_last_inbound.clear()
            self._merchant_auto_reply_count.clear()
