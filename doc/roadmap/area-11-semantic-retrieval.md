# Area 11: Semantic Retrieval & RAG Pipeline

Transform flavIA's current keyword-based catalog search into a full RAG pipeline that embeds converted documents, stores vectors in SQLite, and provides hybrid retrieval (vector + full-text) to the agent.

**Status**: 6 / 8 tasks complete
**Dependencies**: Area 1 complete (all converters done ✓)

---

## Tasks

### 11.1 Chunk Pipeline — `chunker.py` ✓ DONE
**Difficulty**: Medium
**Dependencies**: Area 1 (converters)

Split every `.converted/*.md` file into retrievable fragments (300–800 tokens). Two specialised streams for video:

- **text/ocr/audio/image** — split by heading hierarchy and paragraph blocks; merge short paragraphs, split oversized ones at sentence boundaries.
- **video_transcript** — group timed transcript segments into ~60-second windows; parse `[HH:MM:SS]` or `MM:SS` timecodes.
- **video_frame** — one chunk per frame section, supporting both `## Frame at HH:MM:SS` and converter output `# Visual Frame at HH:MM:SS`.

**Output** (`chunk` dict):
```json
{
  "chunk_id": "<sha1(doc_id:modality:offset)>",
  "doc_id":   "<sha1(base_dir:path:checksum)>",
  "modality": "text|ocr|video_transcript|video_frame|image_caption|audio_transcript",
  "source": {
    "converted_path": ".converted/...",
    "name": "document name",
    "file_type": "pdf|video|audio|image",
    "locator": {
      "page": null,
      "time_start": "00:01:05",
      "time_end":   "00:01:18",
      "line_start": 120,
      "line_end":   170
    }
  },
  "heading_path": ["Section 2", "Method"],
  "text": "..."
}
```

**File**: `src/flavia/content/indexer/chunker.py`
Public entry points: `chunk_document(entry, base_dir)`, `chunk_text_document(...)`, `chunk_video_document(...)`

---

### 11.2 Embedding Index (sqlite-vec) ✓ DONE
**Difficulty**: Medium
**Dependencies**: 11.1

Embed chunks with `hf:nomic-ai/nomic-embed-text-v1.5` (768 dims) via the Synthetic provider client. L2-normalise before storing in a `sqlite-vec` `vec0` virtual table.

**Files**:
- `src/flavia/content/indexer/embedder.py` — `embed_chunks(chunks, client)`, `embed_query(query, client)`, `get_embedding_client(settings)`
- `src/flavia/content/indexer/vector_store.py` — `VectorStore` class: `upsert(chunk_ids, vectors)`, `knn_search(query_vec, k, doc_ids_filter)`

**Embedding call pattern**:
```python
response = client.embeddings.create(
    model="hf:nomic-ai/nomic-embed-text-v1.5",
    input=[f"[doc: {name}] [type: {file_type}] [section: {section}]\n{chunk_text}"]
)
vector = response.data[0].embedding  # list[float], dim=768
```

**SQLite schema** (in `.index/index.db`):
```sql
-- sqlite-vec vector table
CREATE VIRTUAL TABLE chunks_vec USING vec0(
    chunk_id TEXT PRIMARY KEY,
    embedding float[768]
);

-- Metadata for vector results join
CREATE TABLE chunks_meta (
    chunk_id     TEXT PRIMARY KEY,
    doc_id       TEXT,
    modality     TEXT,
    converted_path TEXT,
    locator_json TEXT,
    heading_json TEXT,
    doc_name     TEXT,
    file_type    TEXT,
    indexed_at   TEXT
);
```

**pyproject.toml**: add `sqlite-vec` to optional `[rag]` extras group.

---

### 11.3 FTS Index (SQLite FTS5) ✓ DONE
**Difficulty**: Easy
**Dependencies**: 11.1

Create and maintain a FTS5 virtual table in `index.db` for exact-term matching (numbers, codes, siglas).

**File**: `src/flavia/content/indexer/fts.py` — `FTSIndex` class: `upsert(chunks)`, `search(query, k, doc_ids_filter)`, `get_existing_chunk_ids()`, `delete_chunks()`, `get_stats()`

**Schema**:
```sql
CREATE VIRTUAL TABLE chunks_fts USING fts5(
    chunk_id UNINDEXED,
    doc_id   UNINDEXED,
    modality UNINDEXED,
    text,
    heading_path,
    tokenize = 'porter unicode61'
);
```

BM25 ranking via `bm25(chunks_fts)` in query ordering.

---

### 11.4 Hybrid Retrieval Engine
**Difficulty**: Medium
**Dependencies**: 11.2, 11.3

Core `retrieve(question, filters, top_k)` combining vector and FTS results via Reciprocal Rank Fusion (RRF).

**File**: `src/flavia/content/indexer/retrieval.py`

**Mandatory filter semantics alignment (future implementation requirement)**:
- `doc_ids_filter=None` means no doc_id restriction.
- `doc_ids_filter=[]` means explicit empty scope and must return no results.
- Behavior must be consistent between `VectorStore.knn_search()` and `FTSIndex.search()`.

**Retrieval flow**:
```
User question
    ↓
Stage A — Catalog router (fast)
    FTS on catalog summaries + metadata → shortlist 10–20 doc_ids
    ↓
Stage B — Hybrid chunk search
    Vector: cosine kNN filtered by doc_ids → top-15
    FTS:    BM25 on chunks filtered by doc_ids → top-15
    Merge:  Reciprocal Rank Fusion (k=60)
    Diversity: max 3 chunks per doc
    → top_k chunks (default 10)
```

**RRF formula**: `score(d) = Σ 1/(k + rank_i(d))` where `k=60`.

---

### 11.5 Video Temporal Expansion
**Difficulty**: Medium
**Dependencies**: 11.4, video converter (done)

When any retrieved chunk has `modality in (video_transcript, video_frame)`, expand a time window around the anchor timecode and return a chronological evidence bundle.

**File**: `src/flavia/content/indexer/video_retrieval.py`

**Expansion rules**:
- `video_transcript`: anchor ± 15 seconds
- `video_frame`: anchor ± 10 seconds

**Output format** (used by `search_chunks` tool):
```
00:01:05–00:01:18 (Audio): "The convolution layer applies..."
00:01:12 (Screen): "Diagram showing 3×3 kernel sliding over input feature map"
```

---

### 11.6 `search_chunks` Tool ~~DONE~~ ✓
**Difficulty**: Easy
**Dependencies**: 11.4

Agent-accessible tool that calls `retrieve()` and formats results as annotated context blocks with citations.

**File**: `src/flavia/tools/content/search_chunks.py`

**Parameters**:
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `query` | string | required | Semantic search query |
| `top_k` | integer | 10 | Number of chunks to return |
| `file_type_filter` | string | — | Restrict to file type (pdf, video, audio, …) |
| `doc_name_filter` | string | — | Restrict to docs matching this name substring |

**Output format**:
```
[1] my_paper.pdf — Section 2 > Method (lines 120–170)
    "The proposed architecture uses a transformer backbone..."

[2] lecture.mp4 — video transcript
    00:01:05–00:01:18 (Audio): "We then apply batch normalisation..."
    00:01:12 (Screen): "Slide: BatchNorm formula"
```

**Registration**: add `SearchChunksTool` to `src/flavia/tools/content/__init__.py`.

---

### 11.7 Index CLI Commands (`/index`)
**Difficulty**: Easy
**Dependencies**: 11.1, 11.2, 11.3

Three sub-commands registered in `src/flavia/interfaces/commands.py`:

| Command | Action |
|---------|--------|
| `/index build` | Full rebuild: rechunk + re-embed all converted docs |
| `/index update` | Incremental: only new/modified docs (detected by checksum) |
| `/index stats` | Show chunk count, vector count, index DB size, last updated |

---

### 11.8 Agent Guidance Update ~~DONE~~ ✓
**Difficulty**: Easy
**Dependencies**: 11.6

Update `_build_catalog_first_guidance()` in `src/flavia/agent/context.py`:

- Add rule: use `search_chunks` for **content/semantic** questions.
- Keep `query_catalog` for **metadata/file-discovery** questions.
- Guidance text:
  > "Use search_chunks when answering questions about document content (what, how, why). Use query_catalog to discover which files exist or filter by type/name."

---

## Acceptance Metrics (Definition of Done)

These metrics define when each task is considered complete in a production-ready way.

### Shared evaluation protocol

- **Eval corpus**: at least 200 converted documents, including at least 20 videos with transcript + frame descriptions.
- **Query set**: at least 120 labeled queries (metadata-discovery, semantic content, exact-term lookup, and video temporal questions).
- **Execution cadence**: run on every PR that touches `src/flavia/content/indexer/*`, `src/flavia/tools/content/*`, or `/index` commands.

### 11.1 Chunk Pipeline

| Metric | Target | Verification |
|--------|--------|--------------|
| Chunk coverage | 100% of valid `converted_to` files generate >=1 chunk | Integration test over catalog fixtures |
| Chunk size quality | >=90% of text chunks in 300-800 token band (char proxy) | Offline chunk stats report |
| Determinism | Same input -> identical `chunk_id` set and order | Snapshot test (double run) |
| Video parsing support | 100% parse for `[start-end]`, `[start]`, and `# Visual Frame at` formats | Unit tests |
| Path safety | 0 reads outside vault base dir | Security regression tests |

### 11.2 Embedding Index (sqlite-vec)

| Metric | Target | Verification |
|--------|--------|--------------|
| Vector coverage | 100% of chunks in `chunks_meta` have vector row | DB consistency check |
| Dimensionality | 100% vectors with dim=768 | DB validator |
| Normalization quality | L2 norm in [0.99, 1.01] for >=99.9% vectors | Offline audit script |
| Incremental idempotency | Re-run with unchanged corpus inserts 0 new vectors | `/index update` dry run/check |
| Partial failure handling | Index job continues and reports failed chunk IDs | Integration test with injected failures |

### 11.3 FTS Index (SQLite FTS5)

| Metric | Target | Verification |
|--------|--------|--------------|
| FTS coverage | 100% of chunks present in `chunks_fts` | DB consistency check |
| Exact-term recall@10 | >=0.95 on exact-term subset (codes, IDs, acronyms) | Eval query set |
| Incremental sync | No stale/deleted chunk IDs after update | Rebuild-vs-update parity check |
| Query latency | p95 <= 200 ms on 50k chunks (local benchmark) | Benchmark job |

### 11.4 Hybrid Retrieval Engine

| Metric | Target | Verification |
|--------|--------|--------------|
| Ranking quality | nDCG@10 >= max(vector-only, fts-only) + 10% | Eval benchmark |
| Retrieval latency | p95 <= 1.5 s for `top_k=10` on 50k chunks | Benchmark job |
| Diversity policy | 100% responses enforce max 3 chunks/doc | Unit + integration tests |
| Filter correctness | 100% respect `file_type_filter` and `doc_name_filter` | Tool-level tests |
| Filter semantics consistency | `doc_ids_filter=None` vs `doc_ids_filter=[]` handled identically in vector+FTS contracts (`None`=unfiltered, `[]`=empty result) | Unit tests for `VectorStore` + `FTSIndex` |

### 11.5 Video Temporal Expansion

| Metric | Target | Verification |
|--------|--------|--------------|
| Window correctness | Transcript anchor ±15s, frame anchor ±10s (bounded by media edges) | Deterministic unit tests |
| Chronological order | 100% output sorted by time | Unit tests |
| Evidence completeness | Anchor chunk always included in expanded bundle | Integration test |
| Temporal recall@5 | >=0.90 on labeled video temporal queries | Eval subset |

### 11.6 `search_chunks` Tool

| Metric | Target | Verification |
|--------|--------|--------------|
| Citation completeness | 100% results include doc name + locator (line/time) | Schema/format tests |
| Output validity | 100% tool responses pass JSON/schema validation | Tool contract tests |
| Tool latency | p95 <= 2.0 s for `top_k=10` on benchmark corpus | End-to-end benchmark |
| Empty-result behavior | 100% return explicit "no results" structure (no crash) | Negative tests |

### 11.7 Index CLI Commands (`/index`)

| Metric | Target | Verification |
|--------|--------|--------------|
| Command coverage | `/index build`, `/index update`, `/index stats` all smoke-tested | CLI integration tests |
| Update efficiency | Unchanged corpus update <= 5% of full build runtime | Benchmark comparison |
| Stats accuracy | Reported counts match DB counts exactly | Consistency test |
| Rebuild reproducibility | Two full builds on same corpus produce identical IDs/counts | Snapshot parity test |

### 11.8 Agent Guidance Update

| Metric | Target | Verification |
|--------|--------|--------------|
| Prompt completeness | Guidance explicitly differentiates `search_chunks` vs `query_catalog` | Prompt unit test |
| Routing behavior | >=90% correct tool choice on labeled routing prompts | Behavior test with fixed stubs |
| Regression guard | Existing metadata/file-discovery flows remain unchanged | Agent prompt regression tests |

---

## Data layout (`.index/` inside vault)

```
vault/
  .flavia/
    content_catalog.json
  .index/
    chunks.jsonl     # append-only canonical chunk store
    index.db         # SQLite: FTS5 + sqlite-vec tables
```

`.index/` sits next to `.flavia/` so it is naturally excluded from the regular catalog scan.

---

## Dependency graph

```
11.1 Chunker
  ├── 11.2 Embedder + VectorStore ──┐
  └── 11.3 FTS Index ───────────────┴── 11.4 Hybrid Retrieval
                                              ├── 11.5 Video Expansion
                                              └── 11.6 search_chunks tool
                                                        └── 11.8 Agent Guidance

11.1 + 11.2 + 11.3 ── 11.7 Index CLI
```

---

## Implementation notes

- **sqlite-vec** is loaded as a SQLite extension (`connection.load_extension(...)`). It must be installed via `pip install sqlite-vec` (optional `[rag]` extra).
- Python's built-in `sqlite3` supports `load_extension` when the CPython build includes `SQLITE_ENABLE_LOAD_EXTENSION`. On macOS system Python this may be disabled; a workaround is `pysqlite3-binary` as a fallback.
- The `chunks.jsonl` file is the source of truth; `index.db` is a derived index and can be rebuilt from it.
- Embeddings are only generated for chunks not already present in `chunks_meta` (incremental mode uses `chunk_id` as idempotency key).
- For the initial implementation, video temporal expansion (11.5) can be deferred — `search_chunks` will still return the anchor chunk with its timecode.
