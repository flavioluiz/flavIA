# RAG Hardening Plan (Generic)

This plan defines incremental improvements to increase retrieval reliability, coverage, and observability without overfitting to a specific domain.

## Scope

- Improve grounding behavior when users reference explicit files with `@...`
- Increase lexical recall in hybrid retrieval
- Improve checklist-style extraction coverage
- Keep debug observability useful without polluting model context
- Strengthen output consistency for structured extraction tasks

## Implementation status (2026-02-17)

- Phase 1: in progress (1.1, 1.2, 1.3 implemented)
- Phase 2: in progress (2.1, 2.2, 2.3 implemented)
- Phase 3: in progress (3.1, 3.2 partially implemented via comparative two-stage + citation enforcement)
- Phase 4: in progress (4.1 implemented, 4.2 partially implemented via turn-scoped trace inspection)

## Phase 1 — Grounding Reliability

### 1.1 Mandatory grounding for `@mentions`
- Detect user prompts that include `@file` references.
- Require at least one successful `search_chunks` call before final answer.
- If grounding is repeatedly skipped, return explicit grounding error.

### 1.2 Canonical error propagation for missing targets
- If `search_chunks` returns unresolved/unindexed `@file` errors, return that result directly.
- Avoid fallback responses that bypass retrieval when explicit file scope was requested.

### 1.3 Turn-level retrieval mode propagation
- When prompt intent indicates exhaustive extraction (itemized/checklist queries), propagate `retrieval_mode=exhaustive` automatically to all `search_chunks` calls in that turn unless explicitly overridden.

## Phase 2 — Retrieval Quality

### 2.1 Lexical fallback strategy
- For multi-term FTS queries, try broader lexical variants (token OR, token AND), then strict phrase fallback.
- Preserve exact-token behavior for single-term/code-like queries.

### 2.2 Adaptive diversity for scoped extraction
- If effective retrieval scope is one document, increase per-document chunk cap to avoid under-coverage.
- Keep cross-document diversity behavior unchanged for broader scopes.

### 2.3 Exhaustive profile
- Add/maintain explicit retrieval profile for high-coverage extraction tasks.
- Use higher candidate budgets (`top_k`, vector/fts pools) in exhaustive mode.

## Phase 3 — Structured Output Consistency

### 3.1 Strict compact format for “list-only” requests
- Detect “no description” / list-only intent and switch to compact structured output.

### 3.2 Evidence-first extraction
- Require per-line citations (source + locator) for extracted fields in structured outputs.

### 3.3 Canonical schema checks
- Validate extracted item/subitem structures against expected template when available.
- Flag missing/duplicate/conflicting keys before final rendering.

## Phase 4 — Observability and Debug UX

### 4.1 Signal quality in hints
- Suppress router-quality warnings when caller already scoped retrieval explicitly.

### 4.2 Turn-scoped diagnostics
- Add command to inspect traces generated in the current turn (or since reset).
- Explicitly report when no retrieval trace exists for the turn.

## Test Strategy

- Unit tests:
  - grounding enforcement and canonical error propagation
  - FTS query fallback behavior
  - adaptive diversity behavior in single-doc scopes
  - exhaustive mode propagation
  - debug hint suppression under explicit scope
- Integration tests:
  - checklist extraction tasks with coverage assertions
  - explicit-mention tasks with deterministic tool-call expectations

## Rollout Strategy

1. Ship Phase 1 first (safety + correctness).
2. Ship Phase 2 next (recall + coverage).
3. Ship Phase 3 with strict formatting flags and schema checks.
4. Ship Phase 4 to improve diagnostics usability for tuning loops.

## Non-goals

- Hardcoding domain-specific labels, taxonomies, or grading systems.
- Embedding fixed assumptions about one document family.
- Coupling retrieval behavior to one evaluation workflow.

---

**[← Back to Roadmap](../../roadmap.md)** | **[CHANGELOG](../../CHANGELOG.md)**
