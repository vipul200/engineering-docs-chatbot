import pytest
from fastapi.testclient import TestClient

from docs_chatbot.api import app


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def test_health(client):
    body = client.get("/health").json()
    assert body["status"] == "ok" and body["chatbot_loaded"] and body["llm_enabled"] is False


def test_chat_endpoint_offline_returns_extractive(client):
    body = client.post("/chat", json={"question": "What is the public API rate limit?"}).json()
    assert body["status"] == "extractive" and body["sources"] and body["grounding"] == 0.0


def test_chat_validates_history_roles(client):
    r = client.post("/chat", json={"question": "hi", "history": [{"role": "system", "content": "x"}]})
    assert r.status_code == 422


def test_overlong_question_is_422(client):
    assert client.post("/chat", json={"question": "x" * 5000}).status_code == 422


def test_api_key_required_when_configured(client, monkeypatch):
    monkeypatch.setenv("AIP_API_KEY", "s3cret")
    assert client.post("/chat", json={"question": "rate limit?"}).status_code == 401
    ok = client.post("/chat", json={"question": "rate limit?"}, headers={"X-API-Key": "s3cret"})
    assert ok.status_code == 200
