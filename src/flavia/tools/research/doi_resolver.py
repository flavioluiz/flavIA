"""DOI metadata resolution tool for flavIA.

Resolves DOIs to full bibliographic metadata using the CrossRef and DataCite REST APIs,
with optional Unpaywall integration for finding open access PDF locations.
"""

import logging
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Optional
from urllib.parse import quote, unquote

import httpx

from ..base import BaseTool, ToolParameter, ToolSchema
from ..registry import register_tool

if TYPE_CHECKING:
    from flavia.agent.context import AgentContext

logger = logging.getLogger(__name__)

_CROSSREF_API = "https://api.crossref.org/works"
_DATACITE_API = "https://api.datacite.org/dois"
_UNPAYWALL_API = "https://api.unpaywall.org/v2"

_DOI_URL_PREFIXES = [
    "https://doi.org/",
    "http://doi.org/",
    "https://dx.doi.org/",
    "http://dx.doi.org/",
]

# BibTeX type mapping from CrossRef/DataCite types
_BIBTEX_TYPE_MAP = {
    "journal-article": "article",
    "article": "article",
    "proceedings-article": "inproceedings",
    "inproceedings": "inproceedings",
    "conference-paper": "inproceedings",
    "book-chapter": "incollection",
    "incollection": "incollection",
    "book": "book",
    "dataset": "misc",
    "software": "misc",
    "report": "techreport",
    "dissertation": "phdthesis",
    "thesis": "phdthesis",
    "preprint": "misc",
}

_TITLE_SKIP_WORDS = {
    "a", "an", "the", "on", "of", "for", "in", "to", "and", "with",
    "from", "by", "at", "is", "are", "as", "be", "was", "were",
}


@dataclass
class AuthorInfo:
    """Author with optional affiliation and ORCID."""

    name: str
    affiliation: str = ""
    orcid: str = ""


@dataclass
class DOIMetadata:
    """Full bibliographic metadata resolved from a DOI."""

    doi: str
    title: str
    authors: list[AuthorInfo] = field(default_factory=list)
    venue: str = ""
    volume: str = ""
    issue: str = ""
    pages: str = ""
    year: Optional[int] = None
    publisher: str = ""
    issn: str = ""
    abstract: str = ""
    references_count: Optional[int] = None
    license_url: str = ""
    open_access_url: str = ""
    entry_type: str = "article"
    source: str = ""
    bibtex: str = ""


# ---------------------------------------------------------------------------
# DOI normalization helpers
# ---------------------------------------------------------------------------


def _normalize_doi(raw: str) -> str:
    """Extract bare DOI from a URL, 'doi:' prefix, or bare DOI string."""
    s = raw.strip()
    for prefix in _DOI_URL_PREFIXES:
        if s.lower().startswith(prefix.lower()):
            return s[len(prefix):]
    if s.lower().startswith("doi:"):
        return s[4:].strip()
    return s


def _is_valid_doi(doi: str) -> bool:
    """Return True if doi looks like a valid DOI (starts with 10. and has /)."""
    return bool(doi) and doi.startswith("10.") and "/" in doi


def _encode_doi_for_path(doi: str) -> str:
    """Encode DOI for safe use in URL path, avoiding double-encoding."""
    return quote(unquote(doi), safe="/")


# ---------------------------------------------------------------------------
# Abstract cleaning
# ---------------------------------------------------------------------------


def _strip_jats_tags(text: str) -> str:
    """Remove JATS XML tags from CrossRef abstracts (e.g. <jats:p>)."""
    return re.sub(r"<[^>]+>", "", text).strip()


# ---------------------------------------------------------------------------
# CrossRef response parsing
# ---------------------------------------------------------------------------


def _extract_year_from_crossref(msg: dict) -> Optional[int]:
    """Extract publication year from CrossRef message, trying multiple date fields."""
    for key in ("published-print", "published-online", "issued", "created"):
        parts = msg.get(key, {}).get("date-parts", [[]])
        if parts and parts[0] and parts[0][0]:
            try:
                return int(parts[0][0])
            except (ValueError, TypeError):
                continue
    return None


def _parse_crossref(data: dict) -> DOIMetadata:
    """Parse a CrossRef API response into DOIMetadata."""
    msg = data.get("message", {})

    # Title
    titles = msg.get("title") or []
    title = titles[0] if titles else ""

    # Authors
    authors: list[AuthorInfo] = []
    for a in msg.get("author") or []:
        given = a.get("given", "")
        family = a.get("family", "")
        if family and given:
            name = f"{given} {family}"
        elif family:
            name = family
        elif given:
            name = given
        else:
            name = a.get("name", "")
        if not name:
            continue

        affils = a.get("affiliation") or []
        affiliation = affils[0].get("name", "") if affils else ""

        orcid_raw = a.get("ORCID", "")
        orcid = (
            orcid_raw.replace("http://orcid.org/", "").replace("https://orcid.org/", "")
            if orcid_raw
            else ""
        )

        authors.append(AuthorInfo(name=name, affiliation=affiliation, orcid=orcid))

    # Venue
    container_titles = msg.get("container-title") or []
    venue = container_titles[0] if container_titles else ""

    # ISSN
    issns = msg.get("ISSN") or []
    issn = issns[0] if issns else ""

    # License
    licenses = msg.get("license") or []
    license_url = licenses[0].get("URL", "") if licenses else ""

    # Abstract (may contain JATS XML)
    abstract_raw = msg.get("abstract", "") or ""
    abstract = _strip_jats_tags(abstract_raw)

    # Entry type
    cr_type = msg.get("type", "")
    entry_type = _BIBTEX_TYPE_MAP.get(cr_type, "misc")

    return DOIMetadata(
        doi=msg.get("DOI", ""),
        title=title,
        authors=authors,
        venue=venue,
        volume=str(msg.get("volume", "") or ""),
        issue=str(msg.get("issue", "") or ""),
        pages=str(msg.get("page", "") or ""),
        year=_extract_year_from_crossref(msg),
        publisher=msg.get("publisher", "") or "",
        issn=issn,
        abstract=abstract,
        references_count=msg.get("references-count"),
        license_url=license_url,
        entry_type=entry_type,
        source="crossref",
    )


# ---------------------------------------------------------------------------
# DataCite response parsing
# ---------------------------------------------------------------------------


def _parse_datacite(data: dict) -> DOIMetadata:
    """Parse a DataCite API response into DOIMetadata."""
    attrs = data.get("data", {}).get("attributes", {})

    # Title
    titles = attrs.get("titles") or []
    title = titles[0].get("title", "") if titles else ""

    # Authors (creators)
    authors: list[AuthorInfo] = []
    for c in attrs.get("creators") or []:
        name = c.get("name", "")
        if not name:
            given = c.get("givenName", "")
            family = c.get("familyName", "")
            if family and given:
                name = f"{given} {family}"
            elif family:
                name = family
            else:
                name = given
        if not name:
            continue

        affils = c.get("affiliation") or []
        if affils:
            affiliation = (
                affils[0].get("name", "") if isinstance(affils[0], dict) else str(affils[0])
            )
        else:
            affiliation = ""

        orcid = ""
        for nid in c.get("nameIdentifiers") or []:
            scheme = nid.get("nameIdentifierScheme", "").lower()
            if scheme == "orcid":
                orcid_raw = nid.get("nameIdentifier", "")
                orcid = orcid_raw.replace("https://orcid.org/", "").replace("http://orcid.org/", "")
                break

        authors.append(AuthorInfo(name=name, affiliation=affiliation, orcid=orcid))

    # Venue / container
    container = attrs.get("container") or {}
    venue = container.get("title", "") or ""
    volume = str(container.get("volume", "") or "")
    issue = str(container.get("issue", "") or "")
    first_page = str(container.get("firstPage", "") or "")
    last_page = str(container.get("lastPage", "") or "")
    if first_page and last_page:
        pages = f"{first_page}-{last_page}"
    elif first_page:
        pages = first_page
    else:
        pages = last_page

    # Abstract
    abstract = ""
    for desc in attrs.get("descriptions") or []:
        if desc.get("descriptionType", "").lower() in ("abstract", ""):
            abstract = _strip_jats_tags(desc.get("description", "") or "")
            break

    # License
    rights_list = attrs.get("rightsList") or []
    license_url = rights_list[0].get("rightsUri", "") if rights_list else ""

    # Publisher
    publisher = attrs.get("publisher", "") or ""

    # Year
    pub_year = attrs.get("publicationYear")
    year: Optional[int] = None
    if pub_year:
        try:
            year = int(pub_year)
        except (ValueError, TypeError):
            pass

    # Entry type
    types = attrs.get("types") or {}
    resource_type = types.get("resourceTypeGeneral", "")
    dc_type_map = {
        "Dataset": "misc",
        "Software": "misc",
        "Text": "article",
        "JournalArticle": "article",
        "ConferencePaper": "inproceedings",
        "BookChapter": "incollection",
        "Book": "book",
        "Dissertation": "phdthesis",
        "Preprint": "misc",
        "Report": "techreport",
    }
    entry_type = dc_type_map.get(resource_type, "misc")

    doi_val = attrs.get("doi", "")

    return DOIMetadata(
        doi=doi_val,
        title=title,
        authors=authors,
        venue=venue,
        volume=volume,
        issue=issue,
        pages=pages,
        year=year,
        publisher=publisher,
        abstract=abstract,
        license_url=license_url,
        entry_type=entry_type,
        source="datacite",
    )


# ---------------------------------------------------------------------------
# Unpaywall
# ---------------------------------------------------------------------------


def _fetch_unpaywall_url(doi: str, email: str) -> str:
    """Query Unpaywall for an open access URL. Returns empty string on failure."""
    if not email:
        return ""
    try:
        doi_path = _encode_doi_for_path(doi)
        resp = httpx.get(
            f"{_UNPAYWALL_API}/{doi_path}",
            params={"email": email},
            headers={"User-Agent": "flavIA/1.0"},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        best = data.get("best_oa_location") or {}
        return best.get("url_for_pdf") or best.get("url_for_landing_page") or ""
    except Exception as exc:
        logger.debug("Unpaywall lookup failed for doi=%r: %s", doi, exc)
        return ""


# ---------------------------------------------------------------------------
# BibTeX generation
# ---------------------------------------------------------------------------


def _generate_citation_key(meta: DOIMetadata) -> str:
    """Generate a citation key like 'vaswani2017attention'."""
    author_part = "unknown"
    if meta.authors:
        name = meta.authors[0].name
        if "," in name:
            author_part = name.split(",")[0].strip()
        else:
            parts = name.strip().split()
            author_part = parts[-1] if parts else "unknown"
    author_part = re.sub(r"[^a-zA-Z]", "", author_part).lower() or "unknown"

    year_part = str(meta.year) if meta.year else "nd"

    title_part = ""
    for word in (meta.title or "").split():
        clean = re.sub(r"[^a-zA-Z]", "", word).lower()
        if clean and clean not in _TITLE_SKIP_WORDS:
            title_part = clean
            break

    return f"{author_part}{year_part}{title_part}"


def _generate_bibtex(meta: DOIMetadata) -> str:
    """Generate a BibTeX entry from DOIMetadata."""
    def _escape_bibtex_value(value: str) -> str:
        # Keep values on one line and escape characters that can break
        # brace-delimited BibTeX fields.
        clean = re.sub(r"\s+", " ", value).strip()
        return (
            clean.replace("\\", "\\\\")
            .replace("{", "\\{")
            .replace("}", "\\}")
        )

    bibtex_type_map = {
        "article": "article",
        "inproceedings": "inproceedings",
        "incollection": "incollection",
        "book": "book",
        "techreport": "techreport",
        "phdthesis": "phdthesis",
        "misc": "misc",
    }
    btype = bibtex_type_map.get(meta.entry_type, "misc")
    key = _generate_citation_key(meta)

    author_str = " and ".join(a.name for a in meta.authors) if meta.authors else ""

    venue_field_name = "booktitle" if btype == "inproceedings" else "journal"

    lines = [f"@{btype}{{{key},"]
    if meta.title:
        lines.append(f"  title={{{_escape_bibtex_value(meta.title)}}},")
    if author_str:
        lines.append(f"  author={{{_escape_bibtex_value(author_str)}}},")
    if meta.venue:
        lines.append(f"  {venue_field_name}={{{_escape_bibtex_value(meta.venue)}}},")
    if meta.volume:
        lines.append(f"  volume={{{_escape_bibtex_value(meta.volume)}}},")
    if meta.issue:
        lines.append(f"  number={{{_escape_bibtex_value(meta.issue)}}},")
    if meta.pages:
        lines.append(f"  pages={{{_escape_bibtex_value(meta.pages)}}},")
    if meta.year:
        lines.append(f"  year={{{meta.year}}},")
    if meta.publisher:
        lines.append(f"  publisher={{{_escape_bibtex_value(meta.publisher)}}},")
    if meta.doi:
        lines.append(f"  doi={{{_escape_bibtex_value(meta.doi)}}},")
    lines.append("}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Output formatting
# ---------------------------------------------------------------------------


def _format_metadata(meta: DOIMetadata) -> str:
    """Format DOIMetadata as a markdown string for the agent."""
    lines: list[str] = [f"## DOI: {meta.doi}", ""]

    lines.append(f"**Title**: {meta.title}")

    if meta.authors:
        author_parts = []
        for a in meta.authors:
            author_str = a.name
            extras: list[str] = []
            if a.affiliation:
                extras.append(a.affiliation)
            if a.orcid:
                extras.append(f"ORCID: {a.orcid}")
            if extras:
                author_str += f" ({'; '.join(extras)})"
            author_parts.append(author_str)
        lines.append(f"**Authors**: {', '.join(author_parts)}")

    venue_parts: list[str] = []
    if meta.venue:
        venue_parts.append(meta.venue)
    if meta.year:
        venue_parts.append(str(meta.year))
    if venue_parts:
        lines.append(f"**Venue**: {', '.join(venue_parts)}")

    if meta.volume:
        lines.append(f"**Volume**: {meta.volume}")
    if meta.issue:
        lines.append(f"**Issue**: {meta.issue}")
    if meta.pages:
        lines.append(f"**Pages**: {meta.pages}")
    if not meta.venue and meta.year:
        lines.append(f"**Year**: {meta.year}")

    if meta.publisher:
        lines.append(f"**Publisher**: {meta.publisher}")
    if meta.issn:
        lines.append(f"**ISSN**: {meta.issn}")

    lines.append(f"**DOI**: https://doi.org/{meta.doi}")

    if meta.references_count is not None:
        lines.append(f"**References**: {meta.references_count}")
    if meta.license_url:
        lines.append(f"**License**: {meta.license_url}")
    if meta.open_access_url:
        lines.append(f"**Open Access**: {meta.open_access_url}")

    lines.append(f"**Source**: {meta.source.title()}")

    if meta.abstract:
        lines.append("")
        lines.append("**Abstract**:")
        lines.append(meta.abstract)

    if meta.bibtex:
        lines.append("")
        lines.append("### BibTeX")
        lines.append("```bibtex")
        lines.append(meta.bibtex)
        lines.append("```")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool class
# ---------------------------------------------------------------------------


class ResolveDOITool(BaseTool):
    """Tool for resolving a DOI to full bibliographic metadata."""

    name = "resolve_doi"
    description = (
        "Resolve a DOI to full bibliographic metadata. "
        "Returns title, authors (with affiliations and ORCID), journal/venue, "
        "volume, issue, pages, year, publisher, abstract, license, "
        "open access URL, and a BibTeX entry. "
        "Uses CrossRef as primary source with DataCite as fallback."
    )
    category = "research"

    def get_schema(self, **context: Any) -> ToolSchema:
        return ToolSchema(
            name=self.name,
            description=self.description,
            parameters=[
                ToolParameter(
                    name="doi",
                    type="string",
                    description=(
                        'DOI to resolve, e.g. "10.1145/3474085.3475688" '
                        'or "https://doi.org/10.1145/3474085.3475688".'
                    ),
                    required=True,
                ),
            ],
        )

    def execute(self, args: dict[str, Any], agent_context: "AgentContext") -> str:
        raw_doi = self._normalize_arg(args.get("doi"))
        if not raw_doi:
            return "Error: doi parameter is required."

        doi = _normalize_doi(raw_doi)
        if not _is_valid_doi(doi):
            return f"Error: invalid DOI format: {raw_doi!r}"

        email = self._get_email()
        attempts: list[str] = []

        # Primary: CrossRef
        metadata = self._try_crossref(doi, email, attempts)

        # Fallback: DataCite
        if metadata is None:
            metadata = self._try_datacite(doi, attempts)

        if metadata is None:
            lines = [f"Error: could not resolve DOI: {doi}", "", "Attempts:"]
            for a in attempts:
                lines.append(f"- {a}")
            return "\n".join(lines)

        # Enhancement: Unpaywall OA URL (non-blocking)
        if email and not metadata.open_access_url:
            oa_url = _fetch_unpaywall_url(doi, email)
            if oa_url:
                metadata.open_access_url = oa_url

        metadata.bibtex = _generate_bibtex(metadata)

        return _format_metadata(metadata)

    def _normalize_arg(self, value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            return value.strip()
        return str(value).strip()

    def _get_email(self) -> str:
        try:
            from flavia.config import get_settings
            return get_settings().openalex_email
        except Exception:
            return ""

    def _try_crossref(
        self, doi: str, email: str, attempts: list[str]
    ) -> Optional[DOIMetadata]:
        params: dict[str, str] = {}
        if email:
            params["mailto"] = email

        headers = {"User-Agent": "flavIA/1.0", "Accept": "application/json"}
        doi_path = _encode_doi_for_path(doi)

        try:
            resp = httpx.get(
                f"{_CROSSREF_API}/{doi_path}",
                params=params,
                headers=headers,
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code if exc.response is not None else "unknown"
            logger.warning("CrossRef HTTP error status=%s doi=%r", status, doi)
            attempts.append(f"CrossRef: HTTP {status} error.")
            return None
        except httpx.RequestError as exc:
            logger.warning(
                "CrossRef network error type=%s doi=%r detail=%r",
                type(exc).__name__,
                doi,
                str(exc)[:200],
            )
            attempts.append(f"CrossRef: network error ({type(exc).__name__}).")
            return None
        except Exception as exc:
            logger.warning(
                "CrossRef unexpected error type=%s doi=%r detail=%r",
                type(exc).__name__,
                doi,
                str(exc)[:200],
            )
            attempts.append(f"CrossRef: unexpected error ({type(exc).__name__}).")
            return None

        try:
            return _parse_crossref(data)
        except Exception as exc:
            logger.warning("CrossRef parse error doi=%r detail=%r", doi, str(exc)[:200])
            attempts.append("CrossRef: failed to parse response.")
            return None

    def _try_datacite(self, doi: str, attempts: list[str]) -> Optional[DOIMetadata]:
        headers = {"Accept": "application/vnd.api+json", "User-Agent": "flavIA/1.0"}
        doi_path = _encode_doi_for_path(doi)

        try:
            resp = httpx.get(
                f"{_DATACITE_API}/{doi_path}",
                headers=headers,
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code if exc.response is not None else "unknown"
            logger.warning("DataCite HTTP error status=%s doi=%r", status, doi)
            attempts.append(f"DataCite: HTTP {status} error.")
            return None
        except httpx.RequestError as exc:
            logger.warning(
                "DataCite network error type=%s doi=%r detail=%r",
                type(exc).__name__,
                doi,
                str(exc)[:200],
            )
            attempts.append(f"DataCite: network error ({type(exc).__name__}).")
            return None
        except Exception as exc:
            logger.warning(
                "DataCite unexpected error type=%s doi=%r detail=%r",
                type(exc).__name__,
                doi,
                str(exc)[:200],
            )
            attempts.append(f"DataCite: unexpected error ({type(exc).__name__}).")
            return None

        try:
            return _parse_datacite(data)
        except Exception as exc:
            logger.warning("DataCite parse error doi=%r detail=%r", doi, str(exc)[:200])
            attempts.append("DataCite: failed to parse response.")
            return None


register_tool(ResolveDOITool())
