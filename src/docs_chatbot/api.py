"""FastAPI service: POST /chat, GET /health.

Run: PYTHONPATH=src uvicorn docs_chatbot.api:app --reload
"""

from __future__ import annotations

import logging
import os
import secrets
import time
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from docs_chatbot import __version__, llm
from docs_chatbot.bot import DocsChatbot
from docs_chatbot.config import get_settings
from docs_chatbot.guardrails import MAX_QUESTION_CHARS

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("docs_chatbot.api")
state: dict = {}


@asynccontextmanager
async def lifespan(_: FastAPI):
    try:
        state["chatbot"] = DocsChatbot.from_settings()
    except FileNotFoundError as exc:
        log.warning("Chatbot not loaded: %s", exc)
    yield
    state.clear()


def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    """If AIP_API_KEY is set, /chat needs a matching X-API-Key header.

    Production: SSO in front (Slack / internal portal) + per-user rate limits.
    """
    expected = os.getenv("AIP_API_KEY")
    if expected and not (x_api_key and secrets.compare_digest(x_api_key, expected)):
        raise HTTPException(401, "Invalid or missing X-API-Key")


app = FastAPI(title="Engineering Docs Chatbot", version=__version__, lifespan=lifespan)


class ChatTurn(BaseModel):
    role: str = Field(..., pattern="^(user|assistant)$")
    content: str = Field(..., max_length=4000)


class ChatRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=MAX_QUESTION_CHARS,
                          examples=["How do I roll back a production deploy?"])
    history: list[ChatTurn] = Field(default_factory=list, max_length=20,
                                    description="Prior turns, oldest first. Only the last 6 are used.")


class SourceOut(BaseModel):
    citation: str = Field(..., description="'<file> > <section>'")
    score: float = Field(..., description="Retrieval similarity (0-1).")
    quote: str | None = Field(None, description="Exact text Claude cited from this source.")


class ChatResponse(BaseModel):
    answer: str
    status: Literal["answered", "not_found", "ungrounded", "rejected", "extractive"]
    sources: list[SourceOut]
    grounding: float = Field(..., ge=0, le=1, description="Share of answer text backed by citations.")
    flags: list[str] = Field(..., description="e.g. pii_masked, possible_prompt_injection, low_grounding")
    model: str | None = None


class HealthResponse(BaseModel):
    status: Literal["ok"]
    chatbot_loaded: bool
    llm_enabled: bool
    llm_model: str


@app.get("/health", response_model=HealthResponse)
def health() -> dict:
    return {
        "status": "ok",
        "chatbot_loaded": "chatbot" in state,
        "llm_enabled": llm.llm_enabled(),
        "llm_model": get_settings().model,
    }


@app.post(
    "/chat",
    response_model=ChatResponse,
    dependencies=[Depends(require_api_key)],
    responses={401: {"description": "Missing/invalid X-API-Key (only when AIP_API_KEY is set)"},
               503: {"description": "No documents loaded"}},
)
def chat(req: ChatRequest) -> dict:
    bot: DocsChatbot | None = state.get("chatbot")
    if bot is None:
        raise HTTPException(503, "Chatbot has no documents loaded (check AIP_DOCS_DIR).")
    start = time.perf_counter()
    answer = bot.ask(req.question, [t.model_dump() for t in req.history])
    log.info("chat status=%s grounding=%.2f flags=%s ms=%.1f", answer.status, answer.grounding,
             answer.flags, (time.perf_counter() - start) * 1000)
    return answer.to_dict()
