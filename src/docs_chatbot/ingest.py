"""Load markdown docs and split them into section-aware chunks with provenance."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    source: str   # file name, used in citations
    title: str    # document title (H1)
    section: str  # nearest heading
    text: str

    @property
    def citation(self) -> str:
        return f"{self.source} > {self.section}"


def _split_long(text: str, max_chars: int, overlap: int) -> list[str]:
    if len(text) <= max_chars:
        return [text]
    parts, start = [], 0
    while start < len(text):
        end = min(len(text), start + max_chars)
        # prefer to cut on a sentence/line boundary
        cut = max(text.rfind(". ", start, end), text.rfind("\n", start, end))
        if end < len(text) and cut > start + max_chars // 2:
            end = cut + 1
        parts.append(text[start:end].strip())
        if end >= len(text):
            break
        start = max(end - overlap, start + 1)
    return parts


def chunk_markdown(path: Path, max_chars: int = 900, overlap: int = 120) -> list[Chunk]:
    lines = path.read_text(encoding="utf-8").splitlines()
    title, section, buf = path.stem, path.stem, []
    sections: list[tuple[str, str]] = []

    def flush() -> None:
        body = "\n".join(buf).strip()
        if body:
            sections.append((section, body))
        buf.clear()

    for line in lines:
        m = _HEADING.match(line)
        if m:
            flush()
            if len(m.group(1)) == 1:
                title = m.group(2).strip()
            section = m.group(2).strip()
        else:
            buf.append(line)
    flush()

    chunks = []
    for sec, body in sections:
        for piece in _split_long(body, max_chars, overlap):
            digest = hashlib.sha1(f"{path.name}:{sec}:{piece}".encode()).hexdigest()[:10]
            # Prefix the heading so retrieval can match on section names too.
            chunks.append(Chunk(digest, path.name, title, sec, f"{title} - {sec}\n{piece}"))
    return chunks


def load_corpus(docs_dir: Path) -> list[Chunk]:
    files = sorted(p for p in docs_dir.rglob("*") if p.suffix.lower() in {".md", ".txt"})
    if not files:
        raise FileNotFoundError(f"No .md/.txt documents found in {docs_dir}")
    return [c for f in files for c in chunk_markdown(f)]
