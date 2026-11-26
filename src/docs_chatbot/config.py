"""Configuration, read from environment variables at call time."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Settings:
    model: str
    offline: bool
    data_dir: Path
    docs_dir: Path
    # Minimum best-match retrieval score for the question to reach the LLM at all.
    min_retrieval_score: float
    top_k: int
    # Minimum share of answer text backed by citations, else the answer is suppressed.
    min_grounding: float
    # Server-side refusal fallbacks (first-party Claude API only; off for Bedrock/Vertex/gateways).
    server_fallbacks: bool


def get_settings() -> Settings:
    data_dir = Path(os.getenv("AIP_DATA_DIR", PROJECT_ROOT / "data"))
    return Settings(
        model=os.getenv("CLAUDE_MODEL", "claude-opus-5-5"),
        offline=os.getenv("AIP_OFFLINE", "0") == "1",
        data_dir=data_dir,
        docs_dir=Path(os.getenv("AIP_DOCS_DIR", data_dir / "docs")),
        min_retrieval_score=float(os.getenv("AIP_MIN_RETRIEVAL_SCORE", "0.12")),
        top_k=int(os.getenv("AIP_TOP_K", "4")),
        min_grounding=float(os.getenv("AIP_MIN_GROUNDING", "0.30")),
        server_fallbacks=os.getenv("AIP_SERVER_FALLBACKS", "1") == "1",
    )
