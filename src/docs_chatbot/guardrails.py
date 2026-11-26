"""Input / output guardrails for the chatbot."""

from __future__ import annotations

import re

from docs_chatbot.pii import mask_pii

MAX_QUESTION_CHARS = 2000

_INJECTION = re.compile(
    r"(ignore (all|any|the|previous|prior) (instructions|rules)|system prompt|"
    r"you are now|disregard .* instructions|reveal .*prompt)",
    re.I,
)
_SECRETS = re.compile(
    r"(AKIA[0-9A-Z]{16}|sk-[A-Za-z0-9_-]{20,}|ghp_[A-Za-z0-9]{30,}|"
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----)"
)


_DELIMITERS = re.compile(r"</?\s*(message|question|history|documents?)\s*>", re.I)


def neutralize_tags(text: str) -> str:
    """Remove our prompt delimiter tags from user text so it can't break out of them."""
    return _DELIMITERS.sub("", text)


class GuardrailViolation(ValueError):
    pass


def check_question(question: str) -> tuple[str, list[str]]:
    """Validate and sanitise a question. Returns (clean_question, flags)."""
    q = (question or "").strip()
    if not q:
        raise GuardrailViolation("Question is empty.")
    if len(q) > MAX_QUESTION_CHARS:
        raise GuardrailViolation(f"Question exceeds {MAX_QUESTION_CHARS} characters.")
    flags = []
    if _INJECTION.search(q):
        flags.append("possible_prompt_injection")
    if _SECRETS.search(q):
        flags.append("secret_in_input")
        q = _SECRETS.sub("<REDACTED_SECRET>", q)
    masked = mask_pii(q)
    if masked != q:
        flags.append("pii_masked")
    return neutralize_tags(masked), flags


def sanitize_history(history: list[dict[str, str]] | None, max_turns: int = 6) -> list[dict[str, str]]:
    """Apply the same masking/redaction to prior turns as to the current question."""
    clean = []
    for turn in (history or [])[-max_turns:]:
        text = _SECRETS.sub("<REDACTED_SECRET>", turn.get("content", ""))[:MAX_QUESTION_CHARS]
        clean.append({"role": turn.get("role", "user"), "content": neutralize_tags(mask_pii(text))})
    return clean


def scrub_output(text: str) -> str:
    """Last line of defence: never echo secrets back to the user."""
    return _SECRETS.sub("<REDACTED_SECRET>", text)
