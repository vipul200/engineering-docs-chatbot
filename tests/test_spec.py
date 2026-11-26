"""Tests added to close gaps found while writing docs/SPEC.md (IDs refer to the spec)."""

from types import SimpleNamespace

import anthropic
import httpx
from fastapi.testclient import TestClient

from docs_chatbot.guardrails import sanitize_history
from tests.test_chatbot import make_bot, response, text_block


def _cited(text, quote="Run `deployer rollback <service> --env prod`."):
    return text_block(text, [SimpleNamespace(document_index=0, cited_text=quote)])


def test_chat_fr_24_llm_error_degrades_to_extractive(fake_llm):
    fake_llm.raise_exc = anthropic.APIConnectionError(
        request=httpx.Request("POST", "https://api.anthropic.com/v1/messages"))
    ans = make_bot().ask("How do I roll back a production deploy?")
    assert ans.status == "extractive" and "llm_unavailable" in ans.flags and ans.grounding == 0.0


def test_chat_fr_18_partially_cited_answer_is_flagged_low_grounding(fake_llm):
    fake_llm.create_result = response(
        _cited("Run deployer rollback <service> --env prod to roll back. "),
        text_block("Database migrations are not rolled back and are not covered in these documents at all."),
    )
    ans = make_bot().ask("How do I roll back a production deploy?")
    assert ans.status == "answered" and 0.3 <= ans.grounding < 0.6 and "low_grounding" in ans.flags


def test_chat_fr_20_truncated_answer_is_flagged(fake_llm):
    fake_llm.create_result = response(_cited("Run deployer rollback"), stop_reason="max_tokens")
    assert "truncated" in make_bot().ask("How do I roll back a production deploy?").flags


def test_chat_fr_22_secrets_never_echoed_in_answer(fake_llm):
    fake_llm.create_result = response(_cited("Use token sk-abcdefghijklmnopqrstuvwxyz1234 to roll back"))
    ans = make_bot().ask("How do I roll back a production deploy?")
    assert "sk-abcdef" not in ans.answer and "<REDACTED_SECRET>" in ans.answer


def test_chat_fr_16_sentinel_prefix_maps_to_not_found(fake_llm):
    fake_llm.create_result = response(text_block("NOT_IN_DOCS - the docs do not say"))
    assert make_bot().ask("What is the exact on-call allowance in euros?").status == "not_found"


def test_chat_fr_04_history_limited_to_last_six_turns():
    hist = [{"role": "user", "content": f"turn {i}"} for i in range(10)]
    clean = sanitize_history(hist)
    assert len(clean) == 6 and clean[0]["content"] == "turn 4"


def test_chat_fr_26_service_starts_without_docs_and_returns_503(tmp_path, monkeypatch):
    from docs_chatbot.api import app
    monkeypatch.setenv("AIP_DOCS_DIR", str(tmp_path))
    with TestClient(app) as c:
        assert c.get("/health").json()["chatbot_loaded"] is False
        assert c.post("/chat", json={"question": "hi"}).status_code == 503
