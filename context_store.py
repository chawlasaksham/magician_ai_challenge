"""
Context Store for magicpin AI Challenge (Vera)
Maintains versioned category, merchant, customer, and trigger contexts.
Supports atomic replacement, version conflict detection (409), and suppression tracking.
"""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple


class ContextStore:
    def __init__(self):
        self._lock = threading.RLock()
        # Storage keyed by (scope, context_id) -> {"version": int, "payload": dict, "updated_at": str}
        self._contexts: Dict[Tuple[str, str], Dict[str, Any]] = {}

        # Fast lookup indexes
        self.categories: Dict[str, Dict[str, Any]] = {}  # slug -> payload
        self.merchants: Dict[str, Dict[str, Any]] = {}   # merchant_id -> payload
        self.customers: Dict[str, Dict[str, Any]] = {}   # customer_id -> payload
        self.triggers: Dict[str, Dict[str, Any]] = {}    # trigger_id -> payload

        # Suppression store: suppression_key -> expires_at (ISO string or None)
        self._suppressions: Dict[str, Optional[str]] = {}
        self._preload_seeds()

    def _preload_seeds(self):
        """Optionally preload seed customers so customer attributes are available."""
        try:
            from pathlib import Path
            import json
            seed_file = Path(__file__).parent / "dataset" / "customers_seed.json"
            if seed_file.exists():
                with open(seed_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for c in data.get("customers", []):
                        cid = c.get("customer_id")
                        if cid:
                            self.customers[cid] = c
        except Exception:
            pass

    def push(
        self, scope: str, context_id: str, version: int, payload: Dict[str, Any], delivered_at: str
    ) -> Tuple[bool, str, int]:
        """
        Ingest a context push atomically.
        Returns:
            (accepted: bool, reason: str, version: int)
        """
        with self._lock:
            key = (scope, context_id)
            current = self._contexts.get(key)

            if current is not None:
                current_ver = current["version"]
                if version < current_ver:
                    return False, "stale_version", current_ver
                elif version == current_ver:
                    return True, "idempotent_noop", current_ver

            # Atomically update or insert
            now_iso = datetime.now(timezone.utc).isoformat()
            self._contexts[key] = {
                "version": version,
                "payload": payload,
                "delivered_at": delivered_at,
                "stored_at": now_iso,
            }

            # Update specialized indexes
            if scope == "category":
                slug = payload.get("slug") or context_id
                self.categories[slug] = payload
            elif scope == "merchant":
                mid = payload.get("merchant_id") or context_id
                self.merchants[mid] = payload
            elif scope == "customer":
                cid = payload.get("customer_id") or context_id
                self.customers[cid] = payload
            elif scope == "trigger":
                tid = payload.get("id") or context_id
                self.triggers[tid] = payload

            return True, "accepted", version

    def get(self, scope: str, context_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            entry = self._contexts.get((scope, context_id))
            return entry["payload"] if entry else None

    def get_version(self, scope: str, context_id: str) -> Optional[int]:
        with self._lock:
            entry = self._contexts.get((scope, context_id))
            return entry["version"] if entry else None

    def counts(self) -> Dict[str, int]:
        with self._lock:
            counts = {"category": 0, "merchant": 0, "customer": 0, "trigger": 0}
            for (scope, _), _ in self._contexts.items():
                if scope in counts:
                    counts[scope] += 1
            return counts

    def suppress(self, suppression_key: str, expires_at: Optional[str] = None):
        """Mark a suppression key as active until expires_at."""
        if not suppression_key:
            return
        with self._lock:
            self._suppressions[suppression_key] = expires_at

    def is_suppressed(self, suppression_key: str, now_iso: Optional[str] = None) -> bool:
        """Check if a suppression key is currently active."""
        if not suppression_key:
            return False
        with self._lock:
            if suppression_key not in self._suppressions:
                return False
            expires_at = self._suppressions[suppression_key]
            if not expires_at:
                return True
            try:
                now_dt = datetime.fromisoformat(now_iso.replace("Z", "+00:00")) if now_iso else datetime.now(timezone.utc)
                exp_dt = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
                if now_dt < exp_dt:
                    return True
                del self._suppressions[suppression_key]
                return False
            except Exception:
                return True

    def clear(self):
        """Clear all stored contexts (teardown)."""
        with self._lock:
            self._contexts.clear()
            self.categories.clear()
            self.merchants.clear()
            self.customers.clear()
            self.triggers.clear()
            self._suppressions.clear()
            self._preload_seeds()

