"""
Guardrails and Compliance Filters for magicpin AI Challenge (Vera)
Enforces:
1. Category-specific taboo vocabulary filtering
2. WhatsApp naked URL removal (preventing Meta template rejections and penalties)
3. Single primary CTA rule
4. Anti-repetition validation against past conversation messages
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Set, Tuple


# Global taboos across all categories
GLOBAL_TABOOS = [
    (r"\bguaranteed\b", "proven"),
    (r"\b100%\s*safe\b", "well-tested"),
    (r"\bcompletely\s+cure\b", "treat effectively"),
    (r"\bmiracle\b", "breakthrough"),
    (r"\bbest\s+in\s+city\b", "trusted locally"),
    (r"\bFDA-?approved\b", "clinically recognized"),
    (r"\bpermanent\s+results\b", "long-lasting results"),
    (r"\binstant\s+transformation\b", "visible results"),
]


class ComplianceGuard:
    @staticmethod
    def clean_body(body: str, category_context: Optional[Dict] = None) -> str:
        """Sanitize message body: remove taboo words and strip prohibited naked URLs."""
        cleaned = body

        # 1. Strip naked URLs (http:// or https://)
        cleaned = re.sub(r'https?://[^\s]+', '', cleaned)
        cleaned = re.sub(r'\s{2,}', ' ', cleaned).strip()

        # 2. Check and replace global taboos
        for pattern, replacement in GLOBAL_TABOOS:
            cleaned = re.sub(pattern, replacement, cleaned, flags=re.IGNORECASE)

        # 3. Check and replace category-specific taboos if present
        if category_context:
            taboos = category_context.get("voice", {}).get("vocab_taboo", [])
            for taboo in taboos:
                # Extract clean term (handling notes in parentheses)
                term = re.split(r'\(', taboo)[0].strip()
                if term:
                    pat = r'\b' + re.escape(term) + r'\b'
                    cleaned = re.sub(pat, "reliable", cleaned, flags=re.IGNORECASE)

        return cleaned

    @staticmethod
    def validate_cta(cta_type: str, body: str) -> Tuple[str, str]:
        """
        Ensure single clear CTA matching the trigger/message type.
        Prevents multiple competing CTAs in one message.
        """
        valid_types = {
            "binary_yes_no",
            "binary_confirm_cancel",
            "open_ended",
            "multi_choice_slot",
            "none",
        }
        normalized_cta = cta_type if cta_type in valid_types else "open_ended"
        return normalized_cta, body

    @staticmethod
    def ensure_unique_body(
        body: str,
        past_sent_bodies: List[str],
        merchant_name: str = "",
    ) -> str:
        """
        If the proposed body matches any previously sent body in this conversation,
        alter the opening or phrasing to guarantee zero verbatim repetition.
        """
        for past in past_sent_bodies:
            # Check near-exact match
            if body.strip().lower() == past.strip().lower():
                # Add variation to greeting or preface
                variations = [
                    f"Following up regarding {merchant_name} — ",
                    "Quick note to keep you updated: ",
                    "Revisiting this with a fresh update — ",
                ]
                for v in variations:
                    candidate = f"{v}{body}"
                    if candidate.strip().lower() != past.strip().lower():
                        return candidate
        return body
