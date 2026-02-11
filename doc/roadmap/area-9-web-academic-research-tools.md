# Area 9: Web & Academic Research Tools

flavIA is designed as an academic research assistant, but currently has no ability to search the web or access academic databases. This area introduces a comprehensive suite of tools for web search, academic literature discovery, article retrieval, and reference management -- the foundational capabilities needed for literature reviews, deep research, and producing scientifically rigorous work with correct citations.

The general architecture follows the existing tool pattern: each tool is a `BaseTool` subclass registered in `ToolRegistry`, organized under a new `tools/research/` category. Web-fetched content integrates with the existing content system (`content/converters/`, `.converted/`) with additional metadata for provenance tracking and lifecycle management.

**Design principle**: Search tools return structured results (titles, links, snippets, metadata). The agent decides which results are relevant, then uses separate tools to fetch full content (via Task 1.5's webpage converter) or download articles (via Task 9.5). This separation keeps each tool focused and composable.

---

### Task 9.1 -- Web Search Engine

**Difficulty**: Medium | **Dependencies**: None (enhanced by Task 1.5 for content extraction)

Create `tools/research/web_search.py` implementing a general-purpose web search tool. The tool queries a search engine API and returns structured results (title, URL, snippet, position) without accessing the pages themselves. The agent can then use the webpage converter (Task 1.5) or `read_url` tool to extract full content from selected results.

**Search providers to evaluate** (decision deferred to implementation time):

| Provider | Pros | Cons |
|----------|------|------|
| **Google Custom Search API** | Most comprehensive index, high-quality results | 100 free queries/day, $5/1000 after; requires Google Cloud project + Custom Search Engine setup |
| **Brave Search API** | Good quality, privacy-focused, generous free tier (2000 queries/month) | Smaller index than Google, newer API |
| **SerpAPI** | Unified wrapper for Google/Bing/Yahoo/Scholar/etc., structured JSON output | Paid service ($50+/month), adds dependency on third-party proxy |
| **DuckDuckGo** | Free, no API key required (via `duckduckgo-search` library) | No official API, relies on scraping; rate-limited; less comprehensive |
| **Bing Web Search API** | Good quality, Microsoft-backed | Paid after free tier (1000/month) |

**Recommended approach**: Support multiple providers via a `SearchProvider` abstraction, similar to the existing LLM provider system. Configure the active provider in `.flavia/services.yaml`:

```yaml
services:
  web_search:
    provider: "brave"        # or "google", "duckduckgo", "serpapi", "bing"
    api_key: "${BRAVE_SEARCH_API_KEY}"
    max_results: 10
    # Provider-specific settings
    google:
      cx: "${GOOGLE_SEARCH_CX}"   # Custom Search Engine ID
      api_key: "${GOOGLE_SEARCH_API_KEY}"
    brave:
      api_key: "${BRAVE_SEARCH_API_KEY}"
    duckduckgo: {}  # No API key needed
```

**Tool interface**:

| Tool | Description |
|------|-------------|
| `web_search` | Search the web. Parameters: `query` (string), `num_results` (int, default 10), `region` (string, optional), `time_range` (string: "day"/"week"/"month"/"year", optional). Returns: list of `{title, url, snippet, position}`. |

**Output format** (returned to the agent):
```
## Web Search Results for "transformer attention mechanisms survey"

1. **Attention Is All You Need** (2017)
   URL: https://arxiv.org/abs/1706.03762
   "We propose a new simple network architecture, the Transformer, based solely on attention mechanisms..."

2. **A Survey of Transformers** (2022)
   URL: https://arxiv.org/abs/2106.04554
   "Transformers have achieved great success in many AI fields..."

[10 results total]
```

The agent can then decide which URLs to read in full using the webpage converter (Task 1.5) or other content extraction tools.

**Key files to modify/create**:
- `tools/research/__init__.py` (new)
- `tools/research/web_search.py` (new)
- `tools/research/search_providers/` (new directory)
- `tools/research/search_providers/base.py` (new -- `BaseSearchProvider` ABC)
- `tools/research/search_providers/brave.py` (new)
- `tools/research/search_providers/google.py` (new)
- `tools/research/search_providers/duckduckgo.py` (new)
- `tools/__init__.py` (add `research` submodule import)
- `config/settings.py` (load `services.yaml` web_search config)

**New dependencies** (optional extras): `duckduckgo-search` (for DuckDuckGo); API-based providers use `httpx` (already a dependency).

---

### Task 9.2 -- Academic Database Search

**Difficulty**: Medium | **Dependencies**: None (enhanced by Task 9.5 for article download)

Create `tools/research/academic_search.py` with tools for searching open academic databases. These databases provide free APIs with rich metadata (titles, authors, abstracts, citations, DOIs, publication venues).

**Databases to integrate**:

| Database | API | Coverage | Notes |
|----------|-----|----------|-------|
| **OpenAlex** | REST API, free, no key required | 250M+ works, fully open | Successor to Microsoft Academic Graph. Best coverage, fully open, well-documented API. **Primary recommendation.** |
| **Semantic Scholar** | REST API, free (API key for higher limits) | 200M+ papers | Allen AI project. Good CS/biomedical coverage. Includes citation graphs, influential citations, TLDR summaries. |
| **Google Scholar** | No official API (scraping via `scholarly` library) | Broadest academic index | No official API; `scholarly` library scrapes results. Fragile, rate-limited, against ToS. Use as fallback only. |
| **CrossRef** | REST API, free (Polite Pool with email) | 150M+ DOIs, metadata only | Primary DOI registration agency. Excellent metadata but no full-text. Used mainly for DOI resolution (Task 9.3). |
| **CORE** | REST API, free with API key | 300M+ metadata, 36M+ full-text OA | Aggregates open access content from repositories worldwide. Good for finding OA versions. |
| **Unpaywall** | REST API, free | OA location data for 30M+ DOIs | Given a DOI, finds legal open access copies. Essential for article download (Task 9.5). |

**Tools to implement**:

| Tool | Description |
|------|-------------|
| `search_papers` | Search academic databases. Parameters: `query` (string), `databases` (list, default `["openalex"]`), `num_results` (int, default 10), `year_range` (tuple, optional), `fields` (list: "cs", "medicine", etc., optional), `sort_by` ("relevance"/"date"/"citations", default "relevance"). Returns structured results with title, authors, year, venue, DOI, abstract snippet, citation count, open access status. |
| `get_paper_details` | Get full metadata for a specific paper. Parameters: `paper_id` (string -- DOI, OpenAlex ID, Semantic Scholar ID, or URL). Returns: full abstract, all authors with affiliations, references, citation count, related papers, available PDF URLs. |
| `get_citations` | Get papers that cite a given paper. Parameters: `paper_id`, `num_results`, `sort_by`. |
| `get_references` | Get papers referenced by a given paper. Parameters: `paper_id`, `num_results`. |
| `find_similar_papers` | Find papers similar to a given paper. Parameters: `paper_id`, `num_results`. Uses Semantic Scholar's recommendations API or OpenAlex related works. |

**Output format** (for `search_papers`):
```
## Academic Search Results for "attention mechanisms in transformers"
Database: OpenAlex | Results: 10 of 15,234

1. **Attention Is All You Need** (2017)
   Authors: Vaswani, A.; Shazeer, N.; Parmar, N.; et al.
   Venue: NeurIPS 2017 | Citations: 120,000+ | DOI: 10.48550/arXiv.1706.03762
   Open Access: [checkmark] (arXiv)
   "We propose a new simple network architecture, the Transformer..."

2. **BERT: Pre-training of Deep Bidirectional Transformers** (2019)
   Authors: Devlin, J.; Chang, M.; Lee, K.; Toutanova, K.
   Venue: NAACL 2019 | Citations: 85,000+ | DOI: 10.18653/v1/N19-1423
   Open Access: [checkmark] (arXiv)
   "We introduce a new language representation model called BERT..."

[...]
```

**Configuration** in `.flavia/services.yaml`:
```yaml
services:
  academic_search:
    default_databases: ["openalex", "semantic_scholar"]
    semantic_scholar:
      api_key: "${SEMANTIC_SCHOLAR_API_KEY}"  # optional, for higher rate limits
    core:
      api_key: "${CORE_API_KEY}"  # required for CORE API
    openalex:
      email: "${OPENALEX_EMAIL}"  # for polite pool (higher rate limits)
```

**Key files to modify/create**:
- `tools/research/academic_search.py` (new)
- `tools/research/academic_providers/` (new directory)
- `tools/research/academic_providers/base.py` (new -- `BaseAcademicProvider` ABC)
- `tools/research/academic_providers/openalex.py` (new)
- `tools/research/academic_providers/semantic_scholar.py` (new)
- `tools/research/academic_providers/google_scholar.py` (new -- via `scholarly` library)
- `tools/research/academic_providers/core.py` (new)
- `tools/research/academic_providers/unpaywall.py` (new)
- `tools/research/__init__.py` (register tools)

**New dependencies** (optional extras): `scholarly` (for Google Scholar, use cautiously); all other APIs use `httpx`.

---

### Task 9.3 -- DOI Metadata Resolution

**Difficulty**: Easy | **Dependencies**: None

Create `tools/research/doi_resolver.py` with a tool for resolving DOIs to full bibliographic metadata using the CrossRef and DataCite REST APIs. This is a foundational tool used by Tasks 9.5 and 9.7 for generating citations and BibTeX entries.

**Tool interface**:

| Tool | Description |
|------|-------------|
| `resolve_doi` | Resolve a DOI to full metadata. Parameters: `doi` (string -- e.g., "10.1145/3474085.3475688" or full URL "https://doi.org/..."). Returns: title, authors (with affiliations and ORCID when available), journal/venue, volume, issue, pages, year, publisher, ISSN, abstract, references count, license, open access URL (via Unpaywall), BibTeX entry. |

**Implementation**:
- Primary: CrossRef API (`https://api.crossref.org/works/{doi}`) -- covers most DOIs, returns rich metadata including references and license info
- Fallback: DataCite API (`https://api.datacite.org/dois/{doi}`) -- covers DOIs not in CrossRef (datasets, software, etc.)
- Enhancement: Query Unpaywall (`https://api.unpaywall.org/v2/{doi}?email=...`) to find open access PDF locations
- The tool automatically generates a BibTeX entry from the metadata (used by Task 9.7)

**Output format**:
```
## DOI: 10.48550/arXiv.1706.03762

**Title**: Attention Is All You Need
**Authors**: Ashish Vaswani, Noam Shazeer, Niki Parmar, Jakub Uszkoreit, Llion Jones, Aidan N. Gomez, Lukasz Kaiser, Illia Polosukhin
**Venue**: Advances in Neural Information Processing Systems (NeurIPS), 2017
**Publisher**: Curran Associates, Inc.
**DOI**: https://doi.org/10.48550/arXiv.1706.03762
**Open Access**: https://arxiv.org/pdf/1706.03762

### BibTeX
@inproceedings{vaswani2017attention,
  title={Attention is all you need},
  author={Vaswani, Ashish and Shazeer, Noam and Parmar, Niki and ...},
  booktitle={Advances in Neural Information Processing Systems},
  volume={30},
  year={2017}
}
```

No API key required for CrossRef (use "polite pool" by including an email in the `User-Agent` or `mailto` parameter). No API key for DataCite. Unpaywall requires an email address only.

**Key files to modify/create**:
- `tools/research/doi_resolver.py` (new)
- `tools/research/__init__.py` (register tool)

**New dependencies**: None (uses `httpx`, already a dependency).

---

### Task 9.4 -- Scopus Integration

**Difficulty**: Medium | **Dependencies**: None (enhanced by Task 9.3 for DOI cross-referencing)

Create `tools/research/scopus_search.py` with tools for accessing the Scopus database via the Elsevier API. Scopus is available via institutional networks (CAPES, university VPNs) and provides journal metrics (SJR, CiteScore, percentiles), author profiles (h-index, publications), and comprehensive citation data.

**Two implementation approaches** (to be evaluated at implementation time):

**Approach A -- Native tools (recommended for full integration)**:
Implement Scopus API calls directly using `httpx`, following the existing `BaseTool` pattern. This provides full control over error handling, caching, and integration with other research tools.

**Approach B -- MCP server integration**:
The environment already has MCP servers for Scopus search (`scopus-search_buscar_journal_percentile`, `scopus-search_buscar_autores`, etc.). If flavIA gains MCP client support in the future, these existing servers could be leveraged directly. The roadmap should document this option but not depend on it for the initial implementation.

**Tools to implement** (Approach A):

| Tool | Description |
|------|-------------|
| `scopus_search_papers` | Search Scopus for papers. Parameters: `query`, `num_results`, `year_range`, `subject_area`, `sort_by`. Returns: titles, authors, DOIs, citations, source, EID. |
| `scopus_journal_metrics` | Get journal metrics. Parameters: `journal_name` or `issn`. Returns: SJR, CiteScore, SNIP, highest percentile, subject categories, H-index. |
| `scopus_author_profile` | Get author profile. Parameters: `author_name`, `affiliation` (optional), `orcid` (optional), `scopus_id` (optional). Returns: h-index, total citations, document count, affiliation history, subject areas, co-authors. |
| `scopus_citations` | Get citation details for a paper. Parameters: `doi` or `scopus_eid`. Returns: list of citing papers with metadata. |

**Configuration** in `.flavia/services.yaml`:
```yaml
services:
  scopus:
    api_key: "${SCOPUS_API_KEY}"  # Elsevier Developer API key
    institutional_token: "${SCOPUS_INST_TOKEN}"  # optional, for higher limits
    # Note: many Scopus API features require access from an institutional IP
    # (university network, CAPES VPN, etc.)
```

**Important notes**:
- The Scopus API requires an API key (free registration at dev.elsevier.com) BUT many endpoints also require access from an institutional IP address
- When accessed from outside an institutional network, the API may return limited results or 403 errors
- The tool should gracefully handle access restrictions, informing the user when institutional access is needed
- Consider caching results locally (in `.flavia/cache/scopus/`) to reduce API calls and enable offline access to previously fetched data

**Key files to modify/create**:
- `tools/research/scopus_search.py` (new)
- `tools/research/__init__.py` (register tools)
- `config/settings.py` (load Scopus config from `services.yaml`)

**New dependencies**: None (uses `httpx`). Optional: `pybliometrics` library for a higher-level Scopus API wrapper (but adds a significant dependency).

---

### Task 9.5 -- Article Download & Content Integration

**Difficulty**: Hard | **Dependencies**: Task 9.2 (academic search provides DOIs/URLs), Task 9.3 (DOI resolution provides OA URLs), Task 1.5 (webpage converter for HTML articles)

Create `tools/research/article_download.py` with tools for downloading academic articles (PDFs) and integrating them into the flavIA content system. Downloaded articles are tracked with provenance metadata and support a temporary/permanent lifecycle.

**Tools to implement**:

| Tool | Description |
|------|-------------|
| `download_article` | Download an article PDF. Parameters: `doi` (string, optional), `url` (string, optional -- direct PDF URL), `search_id` (string, optional -- associates with a research session from Task 9.8). Attempts to find and download a PDF using, in order: (1) Unpaywall OA URL, (2) direct URL if provided, (3) publisher URL with institutional access. Returns: success/failure, local file path, metadata. |
| `list_downloads` | List downloaded articles. Parameters: `search_id` (optional -- filter by research session), `status` (optional -- "temporary"/"permanent"/"all"). Returns: list of articles with metadata, paths, and status. |
| `manage_download` | Change download status. Parameters: `article_id` or `search_id`, `action` ("make_permanent"/"delete"/"delete_session"). |

**Content system integration**:

Downloaded articles integrate with the existing content system (`content/converters/`, `.converted/`, `ContentCatalog`) with additional metadata:

```python
# Extended FileEntry metadata for downloaded articles
{
    "source": "web_research",       # distinguishes from local files
    "search_id": "search_abc123",   # links to research session (Task 9.8)
    "doi": "10.1145/...",
    "download_url": "https://...",
    "download_date": "2025-02-10T14:30:00",
    "status": "temporary",          # "temporary" | "permanent"
    "bibtex_key": "vaswani2017attention",
    "metadata": {
        "title": "...",
        "authors": [...],
        "year": 2017,
        "venue": "..."
    }
}
```

**Lifecycle management**:
- **Temporary** (default): Downloaded articles start as temporary. They are stored in `.flavia/research_downloads/` (separate from the project's main files). They appear in the content catalog with a `[temp]` marker. They can be deleted individually or by search session.
- **Permanent**: When the user marks an article as permanent (via `manage_download`), the PDF is moved to the project's file tree (configurable destination, e.g., `references/` or `papers/`), the content catalog entry is updated, and the article becomes a regular part of the project content.
- **Cleanup**: A `/research-cleanup` command (or option in `manage_download`) deletes all temporary downloads older than a configurable threshold (default: 30 days).

**Download sources** (tried in order):
1. **Unpaywall**: Query Unpaywall API with DOI to find legal OA copies (green or gold OA)
2. **Direct URL**: If a direct PDF URL was provided (e.g., from arXiv, PMC, or institutional repository)
3. **Publisher site**: If accessed from an institutional network (see Task 9.6), attempt to download from the publisher
4. **Preprint servers**: Check arXiv, bioRxiv, medRxiv for preprint versions matching the DOI/title

The tool should inform the agent (and thus the user) about the source and legal status of each download.

**Key files to modify/create**:
- `tools/research/article_download.py` (new)
- `content/catalog.py` (extend `FileEntry` with research metadata fields)
- `content/scanner.py` (extend to scan `.flavia/research_downloads/`)
- `tools/research/__init__.py` (register tools)

**New dependencies**: None (uses `httpx` for downloads, existing PDF converter for processing).

---

### Task 9.6 -- CAPES/Academic Network Publisher Access

**Difficulty**: Hard | **Dependencies**: Task 9.5 (article download infrastructure), Task 9.4 (Scopus already handles one institutional-access service)

Enable access to licensed academic content when flavIA is running on an institutional network (university, CAPES VPN, etc.). This task involves detecting institutional network access, configuring proxy settings, and maintaining a list of publishers accessible via Brazilian academic networks through the CAPES portal.

**Publishers available via CAPES** (Portal de Periodicos da CAPES):

| Publisher / Database | Coverage | Access Method |
|---------------------|----------|---------------|
| **Elsevier (ScienceDirect)** | ~2,500 journals, 40,000+ books | IP-based + CAFe authentication |
| **Springer Nature** | ~3,000 journals, books, protocols | IP-based |
| **Wiley** | ~1,500 journals | IP-based |
| **IEEE Xplore** | ~200+ journals, conference proceedings | IP-based |
| **ACM Digital Library** | CS journals and conference proceedings | IP-based |
| **Taylor & Francis** | ~2,200 journals | IP-based |
| **SAGE** | ~1,000 journals | IP-based |
| **Oxford University Press** | ~400 journals | IP-based |
| **Cambridge University Press** | ~400 journals | IP-based |
| **ACS (American Chemical Society)** | ~80 journals | IP-based |
| **APS (American Physical Society)** | ~15 journals | IP-based |
| **RSC (Royal Society of Chemistry)** | ~40 journals | IP-based |
| **Web of Science / Clarivate** | Citation index, JCR | IP-based + CAFe |
| **Scopus / Elsevier** | Citation index, metrics | IP-based (covered by Task 9.4) |
| **JSTOR** | Multidisciplinary archive | IP-based |
| **ProQuest** | Dissertations, theses | IP-based + CAFe |
| **EBSCO** | Multidisciplinary databases | IP-based |

**Note**: This list should be maintained as a configuration file (not hardcoded) since CAPES contracts change periodically. A `publishers.yaml` configuration file in the defaults directory would allow easy updates.

**Implementation**:

1. **Network detection tool**:
   - `check_institutional_access`: Detect whether the current network provides institutional access by testing known publisher endpoints. Parameters: none. Returns: list of accessible publishers, network type (direct IP, VPN, CAFe proxy), and access status.
   - Implementation: make HEAD requests to known publisher test URLs (e.g., ScienceDirect API, IEEE API) and check for 200 vs 403 responses.

2. **Publisher access configuration** in `.flavia/services.yaml`:
   ```yaml
   services:
     institutional_access:
       mode: "auto"  # "auto" (detect), "direct" (institutional IP), "proxy", "none"
       proxy:
         http: "${INSTITUTIONAL_PROXY_HTTP}"  # for proxy-based access
         https: "${INSTITUTIONAL_PROXY_HTTPS}"
       cafe:  # CAFe (Comunidade Academica Federada) authentication
         institution: "ITA"
         username: "${CAFE_USERNAME}"
         password: "${CAFE_PASSWORD}"
   ```

3. **Publisher registry** (`src/flavia/defaults/publishers.yaml`):
   ```yaml
   publishers:
     elsevier:
       name: "Elsevier / ScienceDirect"
       base_url: "https://api.elsevier.com"
       pdf_pattern: "https://www.sciencedirect.com/science/article/pii/{pii}/pdfft"
       test_url: "https://api.elsevier.com/authenticate"
       doi_prefix: ["10.1016"]
     springer:
       name: "Springer Nature"
       base_url: "https://link.springer.com"
       pdf_pattern: "https://link.springer.com/content/pdf/{doi}.pdf"
       test_url: "https://link.springer.com"
       doi_prefix: ["10.1007", "10.1038"]
     ieee:
       name: "IEEE Xplore"
       base_url: "https://ieeexplore.ieee.org"
       pdf_pattern: "https://ieeexplore.ieee.org/stamp/stamp.jsp?arnumber={id}"
       test_url: "https://ieeexplore.ieee.org/xpl/apiGateway"
       doi_prefix: ["10.1109"]
     # ... additional publishers
   ```

4. **Enhanced article download flow** (extends Task 9.5):
   When `download_article` is called and the article is behind a paywall:
   - Check if the DOI prefix matches a known publisher
   - Test if the publisher is accessible from the current network
   - If accessible, attempt download using the publisher's PDF URL pattern
   - If not accessible, inform the user and suggest: (a) connecting to institutional VPN, (b) checking Unpaywall for OA copies, (c) requesting via interlibrary loan

**Key files to modify/create**:
- `tools/research/institutional_access.py` (new)
- `src/flavia/defaults/publishers.yaml` (new)
- `tools/research/article_download.py` (extend download flow)
- `config/settings.py` (load institutional access config)
- `tools/research/__init__.py` (register tools)

**New dependencies**: None (uses `httpx` for HTTP requests).

---

### Task 9.7 -- BibTeX Reference Management

**Difficulty**: Medium | **Dependencies**: Task 9.3 (DOI resolution provides BibTeX entries), Task 9.2 (academic search provides paper metadata), Task 5.1 (write tools for .bib file modification)

Create `tools/research/bibtex_manager.py` with tools for automatically generating, maintaining, and managing BibTeX reference files (`.bib`). The BibTeX manager ensures that all cited works have correct, complete, and consistently formatted entries.

**Tools to implement**:

| Tool | Description |
|------|-------------|
| `add_reference` | Add a BibTeX entry to a .bib file. Parameters: `doi` (string, optional -- auto-generates entry via Task 9.3), `bibtex` (string, optional -- raw BibTeX entry), `bib_file` (string, default "references.bib"), `key` (string, optional -- custom citation key, auto-generated if omitted). Validates the entry, deduplicates, and appends to the file. |
| `search_references` | Search within a .bib file. Parameters: `bib_file`, `query` (searches across all fields), `field` (optional -- search specific field: "author", "title", "year", etc.). Returns matching entries. |
| `list_references` | List all entries in a .bib file with summary info. Parameters: `bib_file`, `sort_by` ("key"/"year"/"author", default "key"). |
| `remove_reference` | Remove an entry from a .bib file. Parameters: `bib_file`, `key`. |
| `validate_references` | Validate a .bib file: check for missing required fields, duplicate keys, DOIs that can be resolved for additional metadata. Parameters: `bib_file`. Returns: list of warnings and suggestions. |
| `export_citations` | Export references in various formats. Parameters: `bib_file`, `keys` (list, optional -- specific entries; all if omitted), `format` ("bibtex"/"apa"/"ieee"/"acm"/"chicago"/"abnt", default "bibtex"). Returns formatted citations. |

**Citation key generation**:
Auto-generated keys follow the pattern `{first_author_lastname}{year}{first_title_word}`, e.g., `vaswani2017attention`, `devlin2019bert`. Duplicate keys are disambiguated with a letter suffix: `smith2020neural`, `smith2020neurala`.

**Integration with other tools**:
- When `download_article` (Task 9.5) successfully downloads a paper, it automatically calls `add_reference` to add the BibTeX entry to the project's default `.bib` file
- When `resolve_doi` (Task 9.3) is called, it returns a BibTeX entry that can be piped to `add_reference`
- The `search_papers` tool (Task 9.2) includes a `save_to_bib` parameter that automatically adds selected results to the `.bib` file

**Configuration** in `.flavia/services.yaml`:
```yaml
services:
  bibtex:
    default_file: "references.bib"  # relative to project root
    citation_style: "bibtex"         # default export format
    auto_add_on_download: true       # auto-add BibTeX when downloading articles
    key_format: "{author}{year}{title_word}"  # citation key pattern
```

**Key files to modify/create**:
- `tools/research/bibtex_manager.py` (new)
- `tools/research/__init__.py` (register tools)

**New dependencies** (optional): `bibtexparser` (for robust BibTeX parsing). Alternative: implement a lightweight parser using regex for basic operations.

---

### Task 9.8 -- Research Session Management

**Difficulty**: Medium | **Dependencies**: Task 9.1 (web search), Task 9.2 (academic search), Task 9.5 (article download)

Create `tools/research/session_manager.py` with tools for organizing and managing research activities. Each research session groups related searches, results, and downloads under a unique ID, enabling the user to review, export, or clean up the results of a specific research effort.

**Concept**:
A **research session** is a logical grouping of search queries, results, and downloaded articles related to a specific research topic or task (e.g., "literature review on attention mechanisms", "finding datasets for sentiment analysis"). Sessions provide:
- Traceability: know which searches produced which results
- Lifecycle management: delete all temporary results from a specific research session
- Export: generate a summary or report of a research session's findings
- Continuity: resume a previous research session in a new conversation

**Tools to implement**:

| Tool | Description |
|------|-------------|
| `create_research_session` | Create a new research session. Parameters: `name` (string), `description` (string, optional), `topic` (string, optional). Returns: `session_id`. |
| `list_research_sessions` | List all research sessions. Parameters: `status` ("active"/"archived"/"all", default "active"). Returns: sessions with stats (num queries, num results, num downloads). |
| `get_session_details` | Get full details of a research session. Parameters: `session_id`. Returns: all queries performed, results found, articles downloaded, BibTeX entries generated. |
| `archive_session` | Archive a research session (mark as complete, keep data). Parameters: `session_id`. |
| `delete_session` | Delete a research session and all its temporary downloads. Parameters: `session_id`, `keep_permanent` (bool, default true -- keep articles marked as permanent). |
| `export_session` | Export a session summary. Parameters: `session_id`, `format` ("markdown"/"bibtex"/"json", default "markdown"). Returns: formatted summary including queries, key findings, and references. |

**Storage**:
Research sessions are stored in `.flavia/research_sessions/` as YAML files:

```yaml
# .flavia/research_sessions/session_abc123.yaml
id: "session_abc123"
name: "Attention Mechanisms Survey"
description: "Literature review on attention mechanisms in transformers"
created: "2025-02-10T14:30:00"
status: "active"  # active | archived
queries:
  - id: "q1"
    type: "academic_search"
    query: "attention mechanisms transformers survey"
    database: "openalex"
    timestamp: "2025-02-10T14:31:00"
    num_results: 10
  - id: "q2"
    type: "web_search"
    query: "transformer attention visualization tools"
    provider: "brave"
    timestamp: "2025-02-10T14:45:00"
    num_results: 8
results:
  - query_id: "q1"
    doi: "10.48550/arXiv.1706.03762"
    title: "Attention Is All You Need"
    status: "downloaded"
    download_path: ".flavia/research_downloads/vaswani2017attention.pdf"
    bibtex_key: "vaswani2017attention"
    lifecycle: "permanent"
  - query_id: "q1"
    doi: "10.48550/arXiv.2106.04554"
    title: "A Survey of Transformers"
    status: "metadata_only"
    lifecycle: "temporary"
```

**Slash commands** (CLI and Telegram):
- `/research` -- list active research sessions
- `/research <session_id>` -- show session details
- `/research-new <name>` -- create a new session
- `/research-cleanup` -- delete all temporary downloads older than threshold

**Integration with search tools**:
When `web_search` or `search_papers` is called with a `session_id` parameter, the query and results are automatically logged in the session. If no session is active, results are still returned but not tracked.

**Key files to modify/create**:
- `tools/research/session_manager.py` (new)
- `interfaces/cli_interface.py` (add `/research` slash commands)
- `interfaces/telegram_interface.py` (add `/research` command handler)
- `tools/research/__init__.py` (register tools)

---

**[← Back to Roadmap](../roadmap.md)**
