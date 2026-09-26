"""
LLM Client for magicpin AI Challenge (Vera)
Supports optional LLM invocation across OpenAI, Anthropic, Gemini, Groq, DeepSeek.
Enforces a strict 3.0s timeout to guarantee safety within the simulator's latency budget.
Returns None on any error or timeout to trigger seamless deterministic fallback.
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from typing import Any, Dict, Optional


LLM_TIMEOUT = 3.0  # seconds


class LLMClient:
    def __init__(self):
        self.openai_key = os.environ.get("OPENAI_API_KEY") or os.environ.get("LLM_API_KEY", "")
        self.gemini_key = os.environ.get("GEMINI_API_KEY", "")
        self.anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "")
        self.groq_key = os.environ.get("GROQ_API_KEY", "")
        self.deepseek_key = os.environ.get("DEEPSEEK_API_KEY", "")

    def is_available(self) -> bool:
        return bool(
            self.openai_key
            or self.gemini_key
            or self.anthropic_key
            or self.groq_key
            or self.deepseek_key
        )

    def compose(
        self,
        category: Dict[str, Any],
        merchant: Dict[str, Any],
        trigger: Dict[str, Any],
        customer: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Attempt to generate message using available LLM within LLM_TIMEOUT.
        Returns parsed JSON or None if unavailable/failed/timed out.
        """
        if not self.is_available():
            return None

        prompt, system = self._build_prompt(category, merchant, trigger, customer)

        try:
            raw_response = None
            if self.openai_key:
                raw_response = self._call_openai(prompt, system)
            elif self.gemini_key:
                raw_response = self._call_gemini(prompt, system)
            elif self.anthropic_key:
                raw_response = self._call_anthropic(prompt, system)
            elif self.groq_key:
                raw_response = self._call_groq(prompt, system)
            elif self.deepseek_key:
                raw_response = self._call_deepseek(prompt, system)

            if raw_response:
                return self._parse_json(raw_response)
        except Exception:
            return None

        return None

    def _build_prompt(
        self,
        category: Dict[str, Any],
        merchant: Dict[str, Any],
        trigger: Dict[str, Any],
        customer: Optional[Dict[str, Any]] = None,
    ) -> tuple[str, str]:
        system = """You are Vera, magicpin's elite AI assistant for Indian local merchants and their customers.
Compose a WhatsApp outbound message following the 4-context framework.
RULES:
1. SPECIFICITY: Anchor strictly on verified numbers, dates, prices, citations from the context. Never fabricate data.
2. CATEGORY FIT: Honor vertical voice (clinical-collegial for dentists, warm-practical for salons, operator-to-operator for restaurants). Avoid taboo words.
3. MERCHANT FIT: Personalize to merchant/owner name, locality, actual active offers, and language preference (use natural Hinglish if hi/hi-en mix).
4. ENGAGEMENT: Use compulsion levers (curiosity, reciprocity, loss aversion, single binary CTA or open-ended question).
5. FORMAT: Return ONLY valid JSON with keys:
{"body": "...", "cta": "open_ended"|"binary_yes_no"|"multi_choice_slot"|"none", "template_name": "...", "template_params": [...], "rationale": "..."}"""

        user_content = json.dumps({
            "category": {
                "slug": category.get("slug"),
                "voice": category.get("voice"),
                "digest": category.get("digest", [])[:2],
                "peer_stats": category.get("peer_stats"),
            },
            "merchant": {
                "identity": merchant.get("identity"),
                "performance": merchant.get("performance"),
                "offers": [o for o in merchant.get("offers", []) if o.get("status") == "active"],
                "signals": merchant.get("signals"),
            },
            "trigger": trigger,
            "customer": customer.get("identity") if customer else None,
        })
        return f"COMPOSE MESSAGE FOR THIS CONTEXT:\n{user_content}", system

    def _parse_json(self, text: str) -> Optional[Dict[str, Any]]:
        try:
            match = re.search(r'\{[\s\S]*\}', text)
            if match:
                data = json.loads(match.group())
                if "body" in data:
                    return data
        except Exception:
            return None
        return None

    def _call_openai(self, prompt: str, system: str) -> Optional[str]:
        body = json.dumps({
            "model": "gpt-4o-mini",
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            "temperature": 0.0,
            "max_tokens": 500,
        }).encode("utf-8")
        req = urllib.request.Request(
            "https://api.openai.com/v1/chat/completions",
            data=body,
            headers={"Authorization": f"Bearer {self.openai_key}", "Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=LLM_TIMEOUT) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data["choices"][0]["message"]["content"]

    def _call_gemini(self, prompt: str, system: str) -> Optional[str]:
        body = json.dumps({
            "contents": [{"parts": [{"text": f"{system}\n\n{prompt}"}]}],
            "generationConfig": {"temperature": 0.0, "maxOutputTokens": 500}
        }).encode("utf-8")
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={self.gemini_key}"
        req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=LLM_TIMEOUT) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data["candidates"][0]["content"]["parts"][0]["text"]

    def _call_anthropic(self, prompt: str, system: str) -> Optional[str]:
        body = json.dumps({
            "model": "claude-3-haiku-20240307",
            "max_tokens": 500,
            "system": system,
            "messages": [{"role": "user", "content": prompt}],
        }).encode("utf-8")
        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages",
            data=body,
            headers={"x-api-key": self.anthropic_key, "Content-Type": "application/json", "anthropic-version": "2023-06-01"}
        )
        with urllib.request.urlopen(req, timeout=LLM_TIMEOUT) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data["content"][0]["text"]

    def _call_groq(self, prompt: str, system: str) -> Optional[str]:
        body = json.dumps({
            "model": "llama-3.1-8b-instant",
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            "temperature": 0.0,
            "max_tokens": 500,
        }).encode("utf-8")
        req = urllib.request.Request(
            "https://api.groq.com/openai/v1/chat/completions",
            data=body,
            headers={"Authorization": f"Bearer {self.groq_key}", "Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=LLM_TIMEOUT) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data["choices"][0]["message"]["content"]

    def _call_deepseek(self, prompt: str, system: str) -> Optional[str]:
        body = json.dumps({
            "model": "deepseek-chat",
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            "temperature": 0.0,
            "max_tokens": 500,
        }).encode("utf-8")
        req = urllib.request.Request(
            "https://api.deepseek.com/v1/chat/completions",
            data=body,
            headers={"Authorization": f"Bearer {self.deepseek_key}", "Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=LLM_TIMEOUT) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data["choices"][0]["message"]["content"]
