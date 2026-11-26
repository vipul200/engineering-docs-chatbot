from __future__ import annotations

from types import SimpleNamespace

import pytest

from docs_chatbot import llm


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    """Isolate tests from the developer's shell: clear all AIP_* settings so defaults apply,
    and never hit the network unless a test opts in with `fake_llm`."""
    import os
    for key in [k for k in os.environ if k.startswith("AIP_")]:
        monkeypatch.delenv(key)
    monkeypatch.setenv("AIP_OFFLINE", "1")
    llm.get_client.cache_clear()


@pytest.fixture
def fake_llm(monkeypatch):
    """Enable the LLM path with a stub client; set `create_result` / `raise_exc` per test."""
    stub = SimpleNamespace(calls=[], create_result=None, raise_exc=None)

    def create(**kwargs):
        stub.calls.append(kwargs)
        if stub.raise_exc:
            raise stub.raise_exc
        return stub.create_result

    client = SimpleNamespace(
        messages=SimpleNamespace(create=create),
        beta=SimpleNamespace(messages=SimpleNamespace(create=create)),
    )
    monkeypatch.setenv("AIP_OFFLINE", "0")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr(llm, "get_client", lambda: client)
    return stub
