# Scenario 2 — Engineering Docs Chatbot (RAG)

**Goal:** engineers ask questions in natural language ("how do I roll back prod?") and get a
correct, **cited** answer drawn from internal docs. When the docs don't cover a question, the bot says so instead
of guessing.

## 1. End-to-end architecture

```
                         ┌──────────────────── INGESTION (offline / on doc change) ─────────────────────┐
  Confluence, GitHub     │  loaders ─► clean ─► section-aware chunking (heading path kept, ~900 chars,  │
  READMEs, runbooks,  ──►│  120 overlap) ─► index (word+char TF-IDF here; BM25 + embeddings in prod)    │
  ADRs, API specs        │  metadata: source, section, owner, last_updated, ACL group                    │
                         └───────────────────────────────────────────────────────────────────────────────┘
                                                        │
  ┌────────────────────────────────────────── QUERY (online) ──────────────────────────────────────────────┐
  │ Slack / web UI ─► POST /chat                                                                         │
  │   1. Input guardrails: length, empty, PII mask, secret redaction, prompt-injection flag              │
  │   2. Retrieve top-k (query + last user turn, so follow-ups work)                                      │
  │   3. EVIDENCE GATE: best score < threshold ─► "not in docs" (no LLM call at all)                      │
  │   4. Claude: system prompt + chunks as `document` blocks with citations enabled                       │
  │   5. Output guardrails: NOT_IN_DOCS sentinel ─► refuse; zero citations ─► suppress as ungrounded;      │
  │      grounding ratio; secret scrubbing; refusal / max_tokens handling                                 │
  │   6. Return {answer, status, sources[citation, score, quote], grounding, flags}                       │
  └────────────────────────────────────────────────────────────────────────────────────────────────────────┘
                                                        │
                    logs/metrics: status, grounding, flags, latency, 👍/👎 feedback ─► eval set growth
```

Code map: `ingest.py` (chunking) → `retriever.py` (search) → `guardrails.py` →
`prompts.py` → `bot.py` (orchestration) → `api.py` (`POST /chat`) / `cli.py chat`.

**Production choices beyond this demo:**
* **Hybrid retrieval:** BM25 plus dense embeddings (pgvector or OpenSearch), fused with reciprocal-rank fusion, then a
  cross-encoder reranker. Lexical matching stays important because engineers search for exact flags, error
  codes and service names.
* **Access control at retrieval time:** filter chunks by the user's groups (SSO), so the bot never
  quotes a doc the user couldn't open.
* **Freshness:** re-index on doc webhooks; show `last_updated`; prefer newer docs when they conflict.
* **Serving:** stateless FastAPI behind the gateway, a Slack bot front-end, prompt caching on the static
  system prompt, streaming responses for the UI.

## 2. Prompt design (`src/docs_chatbot/prompts.py`)

| Technique | Why |
|---|---|
| Role and scope: "answer using ONLY the documents provided" | Restricts the knowledge source |
| Explicit abstain token: reply exactly `NOT_IN_DOCS` | Makes "I don't know" machine-detectable and deterministic |
| Partial-answer and conflict rules | Avoids filling gaps with invented details; surfaces contradictions |
| "Never invent flags, paths or values" | Engineers copy-paste commands, so a wrong flag is worse than no answer |
| Docs sent as **`document` blocks with `citations: enabled`** | The API returns exact quoted spans for each claim, which can be checked in code |
| Untrusted-data framing for docs and question (`<question>`, `<history>` tags) | Defends against prompt injection |
| Byte-stable system prompt plus `cache_control` | Prompt-cache hits cut cost and latency |
| Bounded history (last 6 turns) | Follow-ups work without unbounded context growth |

## 3. Guardrails against hallucination (defence in depth)

1. **Evidence gate before generation.** If the best retrieval score is below `AIP_MIN_RETRIEVAL_SCORE`,
   the bot answers "not found" without calling the LLM. Example: "office wifi password".
2. **Grounding-only prompt** with an explicit abstain sentinel. This catches questions that retrieval let through,
   such as "parental leave policy" (it matched the on-call doc lexically) or "exact on-call allowance in
   euros" (the doc mentions an allowance but gives no amount).
3. **Citation verification.** `grounding` is the share of answer text that the API backs with a
   citation. An answer with no citations, or with grounding below `AIP_MIN_GROUNDING` (0.30), is
   **suppressed** (`status=ungrounded`). Below 0.6 it is returned but flagged `low_grounding`.
4. **Quotes returned to the user.** Every source carries the exact `cited_text`, so engineers can
   verify an answer in one glance.
5. **Input guardrails.** These apply to the question **and every history turn**: length limits, PII masking, secret
   redaction (AWS/GitHub/API keys), removal of the prompt delimiter tags so user text can't break out of
   `<question>`/`<history>`, and a prompt-injection flag (logged as a monitoring signal, not relied on as a control).
6. **Output scrubbing.** Secrets are never echoed back.
7. **Safe failure.** A model refusal maps to `rejected`. On LLM outage the bot shows the most relevant passage,
   clearly labelled, instead of crashing. On the first-party API, server-side refusal fallbacks are enabled
   (`AIP_SERVER_FALLBACKS=1`); switch them off for Bedrock or gateways that don't support the beta.

## 4. Evaluation

`python -m docs_chatbot.cli chat-eval` runs the golden set `data/chatbot_eval.jsonl`: 14 answerable questions
with expected source and key facts, and 5 unanswerable ones (out-of-scope, a partially covered fact, a prompt injection).

| Metric | Result (claude-opus-5-5) |
|---|---|
| Retrieval hit@4 (expected doc retrieved) | **14/14** |
| Answer correctness (answered + key fact present + cited) | **14/14** |
| Correct refusals on unanswerable questions | **5/5** |

The first run scored 13/14. The evidence filter dropped the chunk that held the answer ("canary 15 min").
I changed the gate to look at the **best** score only and pass the full top-k context to Claude.
That is the regression the golden set exists to catch.

**Production eval plan:** grow the golden set from real questions and 👎 feedback; add an LLM-as-judge
that scores faithfulness (every claim supported by its cited quote) and answer relevance; track the abstain
rate (too high means a retrieval or doc gap, which is useful doc-team signal); run in CI on every prompt or
retriever change.

## 5. Limitations (honest)

* The corpus is 6 small synthetic docs, and both the golden set and the retrieval thresholds were tuned against it.
  Real corpora need re-tuning and a held-out question set.
* TF-IDF retrieval doesn't understand synonyms ("deploy freeze" vs "Friday deploys"). The embedding
  and reranker upgrade path is described above.
* Citation presence does not prove the cited span *supports* the claim. Production needs an NLI or
  LLM-judge faithfulness check.
