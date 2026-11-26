"""PII masking applied to questions, history and logs."""

from __future__ import annotations

import re

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_CARD = re.compile(r"\b\d(?:[ -]?\d){12,18}\b")
_SSN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
# International (+44 20 ...) or separated national format (555-123-4567); bare digit runs are
# usually order/ticket IDs, not phones.
_PHONE = re.compile(r"\+\d[\d ()-]{7,}\d|\(?\b\d{3}\)?[ .-]\d{3}[ .-]\d{4}\b")
_URL = re.compile(r"https?://\S+")


def _luhn_ok(candidate: str) -> bool:
    digits = [int(d) for d in re.sub(r"\D", "", candidate)][::-1]
    total = sum(d if i % 2 == 0 else (d * 2 - 9 if d * 2 > 9 else d * 2) for i, d in enumerate(digits))
    return total % 10 == 0


def _mask_card(m: re.Match) -> str:
    # Only Luhn-valid numbers are cards; order/ticket numbers are left alone.
    return "<CARD>" if _luhn_ok(m.group(0)) else m.group(0)


def mask_pii(text: str) -> str:
    """Replace PII with placeholder tokens before it reaches logs, models or LLMs.

    Regex-based: covers emails, URLs, card numbers, US SSNs and phone numbers.
    Names and postal addresses need an NER model (e.g. Presidio) in production.
    """
    text = _EMAIL.sub("<EMAIL>", text)
    text = _URL.sub("<URL>", text)
    text = _SSN.sub("<SSN>", text)
    text = _CARD.sub(_mask_card, text)
    text = _PHONE.sub("<PHONE>", text)
    return text
