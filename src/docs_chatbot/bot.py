"""RAG orchestration: guardrails -> retrieve -> gate -> generate with citations -> verify."""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from typing import Literal

import anthropic

from docs_chatbot import llm
from docs_chatbot.guardrails import (
    GuardrailViolation,
    check_question,
    sanitize_history,
    scrub_output,
)
from docs_chatbot.ingest import load_corpus
from docs_chatbot.prompts import NOT_IN_DOCS, SYSTEM_PROMPT, question_block
from docs_chatbot.retriever import Hit, Retriever
from docs_chatbot.config import get_settings

log = logging.getLogger(__name__)

NO_ANSWER = (
    "I couldn't find this in the engineering docs, so I won't guess. "
    "Try rephrasing, or ask in #eng-help and consider adding the answer to the docs."
)

Status = Literal["answered", "not_found", "ungrounded", "rejected", "extractive"]


@dataclass
class Source:
    citation: str
    score: float
    quote: str | None = None


@dataclass
class ChatAnswer:
    answer: str
    status: Status
    sources: list[Source] = field(default_factory=list)
    grounding: float = 0.0  # share of answer characters backed by a citation
    flags: list[str] = field(default_factory=list)
    model: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def _documents(hits: list[Hit]) -> list[dict]:
    return [
        {
            "type": "document",
            "source": {"type": "text", "media_type": "text/plain", "data": h.chunk.text},
            "title": h.chunk.citation,
            "citations": {"enabled": True},
        }
        for h in hits
    ]


class DocsChatbot:
    def __init__(self, retriever: Retriever):
        self._retriever = retriever

    @classmethod
    def from_settings(cls) -> "DocsChatbot":
        return cls(Retriever(load_corpus(get_settings().docs_dir)))

    def ask(self, question: str, history: list[dict[str, str]] | None = None) -> ChatAnswer:
        settings = get_settings()
        try:
            q, flags = check_question(question)
        except GuardrailViolation as exc:
            return ChatAnswer(str(exc), "rejected")

        history = sanitize_history(history)
        # Short follow-ups ("and for staging?") borrow the previous user turn for retrieval;
        # full questions stand alone so an old topic doesn't pollute the search.
        query = q
        if history and len(q.split()) <= 6:
            last_user = next((t["content"] for t in reversed(history) if t["role"] == "user"), "")
            query = f"{q} {last_user}".strip()
        hits = self._retriever.search(query, settings.top_k)

        # Guardrail 1: no evidence -> no generation. The cheapest hallucination is the one never made.
        # The gate looks at the BEST match; once passed, the LLM sees the top-k context
        # (minus near-zero noise) because the answer is often in the 2nd/3rd chunk.
        if not hits or hits[0].score < settings.min_retrieval_score:
            return ChatAnswer(NO_ANSWER, "not_found", flags=flags)
        hits = [h for h in hits if h.score >= settings.min_retrieval_score / 2]

        sources = [Source(h.chunk.citation, round(h.score, 3)) for h in hits]
        if not llm.llm_enabled():
            best = hits[0].chunk
            body = best.text.split("\n", 1)[-1]
            return ChatAnswer(f"(LLM disabled - most relevant passage)\n\n{body}", "extractive",
                              sources, 0.0, flags)

        try:
            return self._generate(q, history, hits, sources, flags)
        except llm.LLMUnavailable as exc:
            log.warning("Generation failed, returning extractive answer: %s", exc)
            body = hits[0].chunk.text.split("\n", 1)[-1]
            return ChatAnswer(f"(Assistant temporarily unavailable - most relevant passage)\n\n{body}",
                              "extractive", sources, 0.0, flags + ["llm_unavailable"])

    def _generate(self, q, history, hits, sources, flags) -> ChatAnswer:
        settings = get_settings()
        request = dict(
            model=settings.model,
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            cache_control={"type": "ephemeral"},  # system prompt is byte-stable -> cache hits
            messages=[{
                "role": "user",
                "content": [*_documents(hits), {"type": "text", "text": question_block(q, history)}],
            }],
        )
        client = llm.get_client()
        try:
            if settings.server_fallbacks:
                # Re-run on a fallback model inside the same call if a safety classifier declines.
                response = client.beta.messages.create(
                    **request, betas=["server-side-fallback-2026-07-01"], fallbacks="default")
            else:
                response = client.messages.create(**request)
        except anthropic.APIError as exc:  # programming errors propagate, API errors degrade
            raise llm.translate_error(exc) from exc

        if response.stop_reason == "refusal":
            return ChatAnswer("I can't help with that request.", "rejected", sources,
                              flags=flags + ["model_refusal"], model=response.model)

        text_parts, cited_chars, quotes = [], 0, {}
        for block in response.content:
            if block.type != "text":
                continue
            text_parts.append(block.text)
            citations = block.citations or []
            if citations:
                cited_chars += len(block.text.strip())
            for c in citations:
                quotes.setdefault(c.document_index, c.cited_text.strip())
        answer = scrub_output("".join(text_parts).strip())

        if answer == NOT_IN_DOCS or answer.startswith(NOT_IN_DOCS):
            return ChatAnswer(NO_ANSWER, "not_found", flags=flags, model=response.model)

        for idx, quote in quotes.items():
            if 0 <= idx < len(sources):
                sources[idx].quote = quote
        cited_sources = [s for s in sources if s.quote] or sources
        grounding = round(cited_chars / max(1, len(answer)), 3)

        if response.stop_reason == "max_tokens":
            flags = flags + ["truncated"]
        # Guardrail 2: an answer that is mostly uncited is treated as a hallucination.
        if not quotes or grounding < settings.min_grounding:
            log.warning("Ungrounded answer suppressed (grounding=%.2f)", grounding)
            return ChatAnswer(NO_ANSWER, "ungrounded", sources, grounding,
                              flags + ["insufficient_citations"], response.model)
        if grounding < 0.6:
            flags = flags + ["low_grounding"]
        return ChatAnswer(answer, "answered", cited_sources, min(grounding, 1.0), flags,
                          response.model)
