"""
Intent Detector for magicpin AI Challenge (Vera)
Identifies:
1. WhatsApp Business automated replies
2. Action commitments (switching immediately to action execution mode)
3. Hostile/opt-out signals (graceful termination)
4. Off-topic/curveball requests (polite redirection)
5. General conversational engagement
"""

from __future__ import annotations

import re
from enum import Enum
from typing import Optional, Tuple


class IntentType(Enum):
    AUTO_REPLY = "auto_reply"
    ACTION_COMMITMENT = "action_commitment"
    HOSTILE_OPTOUT = "hostile_optout"
    OFF_TOPIC = "off_topic"
    NORMAL_ENGAGEMENT = "normal_engagement"


# Common WhatsApp Business automated reply signatures (English + Hindi/Hinglish)
AUTO_REPLY_PATTERNS = [
    r"thank\s+you\s+for\s+contacting",
    r"thanks\s+for\s+reaching\s+out",
    r"our\s+team\s+will\s+respond\s+shortly",
    r"we\s+will\s+get\s+back\s+to\s+you",
    r"currently\s+unavailable",
    r"automated\s+assistant",
    r"auto-?generated",
    r"auto-?reply",
    r"outside\s+(our\s+)?business\s+hours",
    r"aapki\s+jaankari\s+ke\s+liye\s+bahut",
    r"hamari\s+team\s+tak\s+pahuncha",
    r"humari\s+team\s+tak\s+pahuncha",
    r"main\s+ek\s+automated\s+assistant\s+hoon",
    r"sampark\s+karne\s+ke\s+liye\s+dhanyaw?ad",
    r"shukriya.*team\s+tak",
]

# Explicit commitment/action phrases signaling intent to proceed
ACTION_COMMITMENT_PATTERNS = [
    r"\b(ok|okay)\s+(lets?|let\s+us)\s+do\s+it\b",
    r"\bwhats?\s+next\b",
    r"\byes\s+(please|send|draft|schedule|proceed|do\s+it)\b",
    r"\bsend\s+(me\s+)?(the\s+)?(abstract|draft|details|pdf|link|post)\b",
    r"\bdraft\s+(the\s+)?(post|whatsapp|message|campaign)\b",
    r"\bgo\s+ahead\b",
    r"\blet'?s\s+proceed\b",
    r"\bproceed\s+with\b",
    r"\bmujhe\s+(magicpin\s+)?(jud?rna|join\s+karna)\s+hai\b",
    r"\bi\s+want\s+to\s+join\b",
    r"\bi\s+am\s+ready\b",
    r"\bchalo\s+karte\s+hain\b",
    r"\bkardo\b",
    r"\bkar\s+do\b",
    r"\bhaan\s+(kar\s+do|bhejo|shuru\s+karo)\b",
    r"\bconfirm(ed)?\b",
]

# Hostile or explicit opt-out phrases
HOSTILE_OPTOUT_PATTERNS = [
    r"\bstop\s+(messaging|sending|bothering)\b",
    r"\bstop\b",
    r"\bunsubscribe\b",
    r"\buseless\s+spam\b",
    r"\bspam\b",
    r"\bnot\s+interested\b",
    r"\bdon'?t\s+message\s+(me|again)\b",
    r"\bwhy\s+are\s+you\s+bothering\s+me\b",
    r"\bleave\s+me\s+alone\b",
    r"\bmat\s+bhejo\b",
    r"\bband\s+karo\b",
    r"\bnahi\s+chahiye\b",
    r"\bpareshan\s+mat\s+karo\b",
]

# Off-topic requests outside Vera's marketing/GBP scope
OFF_TOPIC_PATTERNS = [
    (r"\b(gst|gst\s+filing|gst\s+return)\b", "GST filing"),
    (r"\b(income\s+tax|itr|tax\s+filing)\b", "income tax filing"),
    (r"\b(accounting|audit|balance\s+sheet)\b", "accounting/audit"),
    (r"\b(bank\s+loan|business\s+loan)\b", "bank loans"),
    (r"\b(legal\s+case|court\s+notice)\b", "legal consultation"),
]


class IntentDetector:
    @staticmethod
    def detect(
        message: str,
        consecutive_same_inbound_count: int = 1,
        turn_number: int = 1,
    ) -> Tuple[IntentType, Optional[str]]:
        """
        Analyze incoming message and return (IntentType, matched_detail).
        """
        msg_clean = message.strip().lower()

        # 1. Check repeated inbound messages (2+ identical messages = auto-reply)
        if consecutive_same_inbound_count >= 2:
            return IntentType.AUTO_REPLY, "consecutive_identical_inbound"

        # 2. Check auto-reply regex signatures
        for pat in AUTO_REPLY_PATTERNS:
            if re.search(pat, msg_clean):
                return IntentType.AUTO_REPLY, f"pattern_match:{pat}"

        # 3. Check hostile / opt-out
        for pat in HOSTILE_OPTOUT_PATTERNS:
            if re.search(pat, msg_clean):
                return IntentType.HOSTILE_OPTOUT, f"pattern_match:{pat}"

        # 4. Check action commitment
        for pat in ACTION_COMMITMENT_PATTERNS:
            if re.search(pat, msg_clean):
                return IntentType.ACTION_COMMITMENT, f"pattern_match:{pat}"

        # 5. Check off-topic curveballs
        for pat, topic in OFF_TOPIC_PATTERNS:
            if re.search(pat, msg_clean):
                return IntentType.OFF_TOPIC, topic

        # Default normal engagement
        return IntentType.NORMAL_ENGAGEMENT, None
