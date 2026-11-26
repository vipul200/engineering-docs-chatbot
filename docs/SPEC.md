# Engineering Docs Chatbot — Specification

| | |
|---|---|
| Version | 1.0.0 |
| Status | Implemented (assessment prototype) |
| Related | [README](../README.md) (overview and how to run) · [DESIGN](DESIGN.md) (rationale, prompt design, guardrails) · [openapi.json](openapi.json) (machine-readable API contract) |

This document states **what the system must do**, precisely enough to build, test and review it.
Every requirement has an ID, a check that decides pass or fail, and the test that verifies it (§11).
"MUST" is mandatory; "SHOULD" is a target that isn't enforced automatically.

---

## 1. Purpose and scope

**Purpose:** answer engineers' questions using only the organisation's engineering documentation. Every
answer is traceable to quoted source text, and when the docs don't contain the answer, the bot says so.

**Guiding rule:** *a wrong answer is worse than no answer.* When in doubt, the system abstains.

| In scope | Out of scope (v1) |
|---|---|
| Q&A over markdown/text docs with citations and quotes | Taking actions (running commands, opening tickets) |
| Multi-turn follow-ups (bounded history) | Long-term user memory |
| Input/output guardrails, PII and secret redaction | Per-user document access control (designed, §10) |
| Synchronous HTTP API and CLI | Slack bot front-end, streaming responses |
| Golden-set evaluation | LLM-as-judge faithfulness scoring |
| English | Other languages |

## 2. Glossary

| Term | Meaning |
|---|---|
| **Chunk** | A section of a document (≤ 900 characters) with its provenance: file, document title, section heading |
| **Citation** | `"<file> > <section>"`, e.g. `deployment-runbook.md > Rollback` |
| **Quote** | The exact `cited_text` span Claude's citation API returned for a source |
| **Evidence gate** | The check that blocks generation when the best retrieval score is below `S_min` |
| **Grounding** | Share of answer characters in text blocks that carry at least one citation (0–1) |
| **Sentinel** | The literal string `NOT_IN_DOCS`, which the model is told to output when the docs don't answer |
| `S_min` | Minimum best retrieval score, default **0.12** (`AIP_MIN_RETRIEVAL_SCORE`) |
| `k` | Chunks retrieved, default **4** (`AIP_TOP_K`) |
| `G_min` | Minimum grounding to return an answer, default **0.30** (`AIP_MIN_GROUNDING`) |
| `G_flag` | Grounding below which an answer is flagged `low_grounding`: **0.60** (constant) |

## 3. Answer statuses

Every response has exactly one `status`:

| Status | Meaning | `answer` contains | LLM called? |
|---|---|---|---|
| `answered` | Grounded, cited answer | The answer | yes |
| `not_found` | Docs don't cover it (evidence gate or sentinel) | Standard "couldn't find this" message | maybe |
| `ungrounded` | The model answered but citations were insufficient; suppressed | Standard "couldn't find this" message | yes |
| `rejected` | Invalid input or model refusal | The reason | maybe |
| `extractive` | LLM disabled or unavailable; best passage returned | Labelled passage | no / failed |

The standard message is: *"I couldn't find this in the engineering docs, so I won't guess. Try rephrasing,
or ask in #eng-help and consider adding the answer to the docs."*

---

## 4. Functional requirements

### 4.1 Input handling

| ID | Requirement | Acceptance check |
|---|---|---|
| **CHAT-FR-01** | An empty question MUST give `status="rejected"`. Over 2,000 characters MUST be rejected (HTTP 422 at the API). | Guardrail and API tests |
| **CHAT-FR-02** | PII (emails, URLs, Luhn-valid cards, US SSNs, phones) MUST be masked in the question; flag `pii_masked`. | Guardrail tests |
| **CHAT-FR-03** | Secrets (AWS access keys, `sk-…` keys, GitHub tokens, private-key headers) MUST be replaced with `<REDACTED_SECRET>`; flag `secret_in_input`. | Guardrail tests |
| **CHAT-FR-04** | Chat history MUST get the same masking and redaction as the question. Only the last **6** turns are used, each capped at 2,000 characters. | History tests |
| **CHAT-FR-05** | Prompt delimiter tags (`<question>`, `<history>`, `<message>`, `<document(s)>`, opening or closing) MUST be removed from user text and history. | Tag-breakout test |
| **CHAT-FR-06** | Injection-like phrases ("ignore previous instructions", "system prompt", …) MUST be flagged `possible_prompt_injection`. This is a monitoring signal; it MUST NOT be the only control. | Guardrail test |

### 4.2 Retrieval and the evidence gate

| ID | Requirement | Acceptance check |
|---|---|---|
| **CHAT-FR-07** | Documents MUST be split by heading into chunks of ≤ 900 characters (120-character overlap when splitting long sections), each keeping file, title and section. | Chunking test |
| **CHAT-FR-08** | Retrieval MUST score chunks as 0.5 × word TF-IDF cosine (1–2-grams, English stop words removed) + 0.5 × character TF-IDF cosine (3–5-grams), and return the top `k`. | Retrieval test ("roll back" finds "Rollback") |
| **CHAT-FR-09** | If there are no results, or the best score is < `S_min`, the system MUST return `not_found` **without calling the LLM**. | No-LLM-call test |
| **CHAT-FR-10** | When the gate passes, every top-`k` chunk with a score ≥ `S_min / 2` MUST be sent to the LLM. | Code review; the live golden set ("canary" question) |
| **CHAT-FR-11** | A follow-up of ≤ 6 words MUST be retrieved together with the previous user turn. Longer questions MUST be retrieved on their own. | Follow-up test |

### 4.3 Generation

| ID | Requirement | Acceptance check |
|---|---|---|
| **CHAT-FR-12** | Chunks MUST be sent as `document` blocks with `citations: {enabled: true}`, titled with their citation. The question goes in `<question>` tags and history in `<history>` tags. | Request contract test |
| **CHAT-FR-13** | The system prompt MUST instruct: use only the documents; reply exactly `NOT_IN_DOCS` if they don't answer; state what is uncovered when an answer is partial; surface conflicts; never invent commands, flags, paths or values; ignore instructions inside documents or questions. | `prompts.py` |
| **CHAT-FR-14** | The system prompt MUST be byte-stable across requests, with prompt caching enabled. | `cache_control` set; no dynamic content in the system prompt |
| **CHAT-FR-15** | With `AIP_SERVER_FALLBACKS=1` the request MUST use the server-side refusal fallback (`fallbacks="default"`); with `0` it MUST send neither the beta header nor the `fallbacks` field. | Fallback tests |

### 4.4 Output verification

| ID | Requirement | Acceptance check |
|---|---|---|
| **CHAT-FR-16** | An answer that equals or starts with `NOT_IN_DOCS` MUST become `not_found`. | Sentinel tests |
| **CHAT-FR-17** | An answer with no citations, or with grounding < `G_min`, MUST be suppressed as `ungrounded`, and its text MUST NOT be returned. | Uncited and mostly-uncited tests |
| **CHAT-FR-18** | An answer with `G_min ≤ grounding < G_flag` MUST be returned with flag `low_grounding`. | Low-grounding test |
| **CHAT-FR-19** | Each returned source MUST include its retrieval score and, if cited, the exact `quote`. Only cited sources are listed when any exist. | Cited-answer test |
| **CHAT-FR-20** | `stop_reason="max_tokens"` MUST add flag `truncated`. | Truncation test |
| **CHAT-FR-21** | `stop_reason="refusal"` MUST give `status="rejected"` with flag `model_refusal`. | Refusal test |
| **CHAT-FR-22** | Secrets MUST be scrubbed from the answer text before it is returned. | Output-scrub test |

### 4.5 Degraded mode

| ID | Requirement | Acceptance check |
|---|---|---|
| **CHAT-FR-23** | With the LLM disabled, the system MUST return the best passage labelled "(LLM disabled - most relevant passage)" with `status="extractive"` and `grounding=0`. | Offline test |
| **CHAT-FR-24** | On an Anthropic API error, the system MUST return the best passage labelled "(Assistant temporarily unavailable …)" with `status="extractive"` and flag `llm_unavailable`, and MUST NOT return an HTTP error. Non-API exceptions propagate. | Fault-injection test |

### 4.6 API

| ID | Requirement | Acceptance check |
|---|---|---|
| **CHAT-FR-25** | `POST /chat` MUST accept and return the schemas in §6. History roles other than `user`/`assistant` give HTTP 422. | API tests |
| **CHAT-FR-26** | If no documents are found at startup, the service MUST still start; `/health` reports `chatbot_loaded=false` and `/chat` returns 503. | Startup test |
| **CHAT-FR-27** | If `AIP_API_KEY` is set, `/chat` MUST require a matching `X-API-Key` header (constant-time comparison), otherwise 401. | API-key test |
| **CHAT-FR-28** | The committed `docs/openapi.json` MUST equal the schema generated from the running code. | Contract test |

---

## 5. Non-functional requirements

| ID | Category | Requirement | Status |
|---|---|---|---|
| **CHAT-NFR-01** | Accuracy | Golden set: correct cited answers ≥ 90% | MUST before release (verified: 14/14) |
| **CHAT-NFR-02** | Safety | Golden set: correct refusals on unanswerable questions = 100% | MUST (verified: 5/5) |
| **CHAT-NFR-03** | Retrieval | Golden set: hit@4 ≥ 90% | MUST (verified: 14/14) |
| **CHAT-NFR-04** | Latency | p95 < 15 s for an answered question; a `not_found` from the evidence gate < 100 ms | SHOULD |
| **CHAT-NFR-05** | Availability | An LLM outage MUST NOT cause HTTP errors (CHAT-FR-24) | MUST, tested |
| **CHAT-NFR-06** | Privacy | Logs contain status, grounding, flags and latency only, never question or answer text | MUST |
| **CHAT-NFR-07** | Security | User text and documents are untrusted data in the prompt (CHAT-FR-05, 12, 13) | MUST, tested |
| **CHAT-NFR-08** | Cost | Off-topic questions cost $0 (evidence gate); the system prompt is cacheable | MUST |
| **CHAT-NFR-09** | Testability | The full test suite MUST run offline, with no network or API key | MUST (all 28 tests) |
| **CHAT-NFR-10** | Scalability | Stateless; the index is built in memory at startup; scales horizontally | SHOULD |

---

## 6. API contract

Machine-readable version: [openapi.json](openapi.json). Interactive docs: `http://localhost:8001/docs`.

### `POST /chat`

**Request**

| Field | Type | Rules |
|---|---|---|
| `question` | string | Required, 1–2,000 characters |
| `history` | list of `{role, content}` | Optional, ≤ 20 items. `role` ∈ `user` \| `assistant`; `content` ≤ 4,000 characters. Only the last 6 are used |

**Response 200**

| Field | Type | Description |
|---|---|---|
| `answer` | string | Answer text, or the standard message (§3) |
| `status` | enum (§3) | Outcome |
| `sources` | list of `{citation, score, quote}` | `quote` is the exact cited text, or null |
| `grounding` | float 0–1 | Cited share of the answer |
| `flags` | list of string | Any of: `pii_masked`, `secret_in_input`, `possible_prompt_injection`, `low_grounding`, `insufficient_citations`, `truncated`, `model_refusal`, `llm_unavailable` |
| `model` | string \| null | Model that produced the answer |

**Errors:** `401` invalid or missing API key (only when configured) · `422` invalid body · `503` no documents loaded.

**Example**

```http
POST /chat
{"question": "How do I roll back a production deploy?"}

200 OK
{
  "answer": "To roll back, run `deployer rollback <service> --env prod`. This redeploys the previous image tag in under 2 minutes. ...",
  "status": "answered",
  "sources": [{"citation": "deployment-runbook.md > Rollback", "score": 0.174,
               "quote": "Run `deployer rollback <service> --env prod`."}],
  "grounding": 0.551,
  "flags": ["low_grounding"],
  "model": "claude-opus-5-5"
}
```

### `GET /health`

Returns `{status: "ok", chatbot_loaded, llm_enabled, llm_model}`.

---

## 7. Processing pipeline (normative)

```
ask(question, history):
    q, flags = check_question(question)            # FR-01..03, 05, 06   → rejected on violation
    history  = sanitize_history(history)           # FR-04, 05
    query    = q + last_user_turn if history and words(q) <= 6 else q   # FR-11
    hits     = retrieve(query, k)                  # FR-08
    if not hits or hits[0].score < S_min:
        return not_found                           # FR-09: no LLM call
    hits     = [h for h in hits if h.score >= S_min / 2]                 # FR-10
    if LLM disabled:   return extractive(hits[0]), grounding=0           # FR-23
    try:     resp = Claude(system, documents(hits) + question_block(q, history))   # FR-12..15
    except APIError:   return extractive(hits[0]) + llm_unavailable      # FR-24
    if resp.refusal:                        return rejected + model_refusal       # FR-21
    answer = scrub_secrets(text(resp))                                            # FR-22
    if answer starts with NOT_IN_DOCS:      return not_found                      # FR-16
    if no citations or grounding < G_min:   return ungrounded (text withheld)     # FR-17
    if grounding < G_flag: flags += low_grounding                                 # FR-18
    if resp.max_tokens:    flags += truncated                                     # FR-20
    return answered, cited sources with quotes                                    # FR-19
```

### Hallucination controls

| Layer | Control | Catches | Requirement |
|---|---|---|---|
| 1 | Evidence gate | Questions with no relevant docs ("office wifi password") | FR-09 |
| 2 | Grounding-only system prompt | Use of outside knowledge | FR-13 |
| 3 | `NOT_IN_DOCS` sentinel | Topics retrieval let through by lexical overlap ("parental leave") | FR-16 |
| 4 | Citation presence | Answers with no source | FR-17 |
| 5 | Grounding ratio | Answers padded with uncited claims | FR-17, 18 |
| + | Quotes shown to the user | Lets a human verify in one glance | FR-19 |

---

## 8. Data contracts

### Knowledge base (`AIP_DOCS_DIR`, default `data/docs/`)
* `.md` and `.txt` files, including subfolders, read as UTF-8.
* The H1 heading is the document title, and every heading starts a new section. Text before the first heading uses the file name.
* At least one file is required (otherwise the service starts in the CHAT-FR-26 state).

### Golden evaluation set (`data/chatbot_eval.jsonl`), one JSON object per line

| Field | Type | Meaning |
|---|---|---|
| `question` | string | The question |
| `answerable` | bool | Whether the docs contain the answer |
| `source` | string \| null | File expected in the top-`k` results (answerable questions only) |
| `must_contain` | list of string | Case-insensitive substrings the answer must contain |

Scoring (`python -m docs_chatbot.cli chat-eval`):

| Metric | Pass condition |
|---|---|
| Retrieval hit@k | `source` is among the files of the top-`k` retrieved chunks |
| Answer correctness | `status="answered"` and every `must_contain` string is present |
| Correct refusal | Unanswerable question → `not_found`, `ungrounded` or `rejected` |

Current set: 14 answerable + 5 unanswerable (out-of-scope ×3, partially covered fact ×1, prompt injection ×1).

---

## 9. Configuration

| Variable | Default | Affects |
|---|---|---|
| `ANTHROPIC_API_KEY` / `ANTHROPIC_AUTH_TOKEN` | — | LLM enabled if either is set |
| `CLAUDE_MODEL` | `claude-opus-5-5` | Generation model |
| `AIP_OFFLINE` | `0` | `1` disables the LLM (CHAT-FR-23) |
| `AIP_SERVER_FALLBACKS` | `1` | CHAT-FR-15; set `0` on Bedrock/Vertex/gateways |
| `AIP_MIN_RETRIEVAL_SCORE` | `0.12` | `S_min` |
| `AIP_TOP_K` | `4` | `k` |
| `AIP_MIN_GROUNDING` | `0.30` | `G_min` |
| `AIP_DOCS_DIR` | `data/docs` | Knowledge base |
| `AIP_DATA_DIR` | `data` | Golden set location |
| `AIP_API_KEY` | — | Enables the API-key check |

---

## 10. Production extensions (designed, not built)

| Extension | Requirement it would add |
|---|---|
| Hybrid retrieval: BM25 + embeddings (pgvector/OpenSearch), RRF fusion, cross-encoder reranker | Replaces CHAT-FR-08; same `Retriever.search` interface |
| Access control | Chunks filtered by the user's SSO groups *before* retrieval scoring |
| Freshness | Re-index on doc-change webhooks; return `last_updated` per source |
| Faithfulness evaluation | LLM-judge or NLI check that each quote supports its claim; gate in CI |
| Feedback loop | 👍/👎 per answer; 👎 and `not_found` questions feed the golden set and the doc-gap report |

---

## 11. Traceability: requirements → tests

| Requirement | Verified by |
|---|---|
| CHAT-FR-01, 03, 06 | `test_chatbot.py::test_guardrails_reject_empty_and_flag_injection_and_secrets`, `test_api.py::test_overlong_question_is_422` |
| CHAT-FR-04 | `test_security.py::test_history_is_masked_and_redacted_before_llm`, `test_spec.py::test_chat_fr_04_history_limited_to_last_six_turns` |
| CHAT-FR-05 | `test_security.py::test_closing_tags_cannot_break_out_of_prompt_delimiters` |
| CHAT-FR-07 | `test_chatbot.py::test_chunks_keep_provenance` |
| CHAT-FR-08 | `test_chatbot.py::test_retrieval_finds_rollback_section` |
| CHAT-FR-09 | `test_chatbot.py::test_off_topic_question_is_refused_without_llm_call` |
| CHAT-FR-11 | `test_security.py::test_follow_up_borrows_previous_turn_but_new_topic_does_not` |
| CHAT-FR-12, 19 | `test_chatbot.py::test_cited_answer_is_returned_with_quotes` |
| CHAT-FR-15 | `test_chatbot.py::test_fallbacks_on_by_default`, `test_fallbacks_can_be_disabled_for_bedrock_gateways` |
| CHAT-FR-16 | `test_chatbot.py::test_not_in_docs_sentinel_maps_to_no_answer`, `test_spec.py::test_chat_fr_16_sentinel_prefix_maps_to_not_found` |
| CHAT-FR-17 | `test_chatbot.py::test_uncited_answer_is_suppressed`, `test_security.py::test_mostly_uncited_answer_is_suppressed` |
| CHAT-FR-18 | `test_spec.py::test_chat_fr_18_partially_cited_answer_is_flagged_low_grounding` |
| CHAT-FR-20 | `test_spec.py::test_chat_fr_20_truncated_answer_is_flagged` |
| CHAT-FR-21 | `test_chatbot.py::test_model_refusal_is_handled` |
| CHAT-FR-22 | `test_spec.py::test_chat_fr_22_secrets_never_echoed_in_answer` |
| CHAT-FR-23 | `test_chatbot.py::test_offline_mode_returns_extractive_passage`, `test_api.py::test_chat_endpoint_offline_returns_extractive` |
| CHAT-FR-24 | `test_spec.py::test_chat_fr_24_llm_error_degrades_to_extractive` |
| CHAT-FR-25 | `test_api.py::test_chat_validates_history_roles`, `test_api.py::test_health` |
| CHAT-FR-26 | `test_spec.py::test_chat_fr_26_service_starts_without_docs_and_returns_503` |
| CHAT-FR-27 | `test_api.py::test_api_key_required_when_configured` |
| CHAT-FR-28 | `test_contract.py::test_openapi_spec_is_up_to_date` |
| CHAT-FR-02 | `test_security.py::test_history_is_masked_and_redacted_before_llm` (masking path shared with the question) |
| CHAT-FR-10, 13, 14 | Code review + live golden set |
| CHAT-NFR-01..03 | Live: `python -m docs_chatbot.cli chat-eval` |

---

## 12. Assumptions, constraints and open items

**Assumptions**
* The docs are mostly accurate and current; the bot is only as correct as its sources.
* Users are authenticated upstream (SSO) in production.

**Known gaps (backlog)**
* The golden set (19 questions) and thresholds were tuned on the same 6-doc corpus. A real corpus needs re-tuning on held-out questions.
* Citation presence ≠ entailment. Faithfulness scoring is in §10.
* CHAT-FR-10, 13 and 14 are verified by code review and live eval only.
