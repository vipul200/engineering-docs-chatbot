"""Lexical retriever (blended word + character TF-IDF cosine).

Chosen for the demo because it needs no external services and is strong on
exact engineering terms (CLI flags, error codes, service names). Production
would use hybrid retrieval: BM25 + dense embeddings in a vector DB
(pgvector / OpenSearch), fused with RRF, then a cross-encoder reranker.
The `Retriever` interface stays the same.
"""

from __future__ import annotations

from dataclasses import dataclass

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import linear_kernel

from docs_chatbot.ingest import Chunk


@dataclass(frozen=True)
class Hit:
    chunk: Chunk
    score: float


class Retriever:
    def __init__(self, chunks: list[Chunk]):
        if not chunks:
            raise ValueError("Retriever needs at least one chunk")
        self._chunks = chunks
        texts = [c.text for c in chunks]
        # Word n-grams for exact terms + char n-grams for morphology ("roll back" ~ "rollback",
        # "prod" ~ "production", typos). Scores are blended.
        self._word = TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True, stop_words="english")
        self._char = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), sublinear_tf=True)
        self._word_m = self._word.fit_transform(texts)
        self._char_m = self._char.fit_transform(texts)

    def search(self, query: str, k: int = 4) -> list[Hit]:
        if not query.strip():
            return []
        word = linear_kernel(self._word.transform([query]), self._word_m)[0]
        char = linear_kernel(self._char.transform([query]), self._char_m)[0]
        scores = 0.5 * word + 0.5 * char
        order = scores.argsort()[::-1][:k]
        return [Hit(self._chunks[i], float(scores[i])) for i in order if scores[i] > 0]
