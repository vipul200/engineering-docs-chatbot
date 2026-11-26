"""Thin wrapper around the Anthropic SDK shared by both services.

Credentials are resolved by the SDK itself (ANTHROPIC_API_KEY, ANTHROPIC_AUTH_TOKEN
or an `ant auth login` profile). Set AIP_OFFLINE=1 to force the non-LLM paths,
which is what the test-suite and keyless reviewers use.
"""

from __future__ import annotations

import logging
import os
from functools import lru_cache

import anthropic

from docs_chatbot.config import get_settings

log = logging.getLogger(__name__)


class LLMUnavailable(RuntimeError):
    """Raised when the LLM cannot be used; callers fall back to a safe path."""


def llm_enabled() -> bool:
    if get_settings().offline:
        return False
    return bool(os.getenv("ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_AUTH_TOKEN"))


@lru_cache(maxsize=1)
def get_client() -> anthropic.Anthropic:
    # SDK retries 408/409/429/5xx and connection errors with backoff.
    return anthropic.Anthropic(max_retries=3, timeout=60.0)


def translate_error(exc: anthropic.APIError) -> LLMUnavailable:
    """Map SDK errors to one exception type, logging the specific cause."""
    if isinstance(exc, anthropic.AuthenticationError):
        log.error("Claude auth failed; check ANTHROPIC_API_KEY")
    elif isinstance(exc, anthropic.RateLimitError):
        log.warning("Claude rate limited after retries")
    elif isinstance(exc, anthropic.APIStatusError):
        log.warning("Claude API error %s: %s", exc.status_code, exc.message)
    elif isinstance(exc, anthropic.APIConnectionError):
        log.warning("Claude unreachable: %s", exc)
    else:
        log.warning("Claude error: %s", exc)
    return LLMUnavailable(str(exc))
