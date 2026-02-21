"""Tests for the DOI metadata resolution tool."""

import json
import logging
from pathlib import Path

import httpx

from flavia.agent.context import AgentContext
from flavia.agent.profile import AgentPermissions
from flavia.tools import list_available_tools
from flavia.tools.research.doi_resolver import (
    AuthorInfo,
    DOIMetadata,
    ResolveDOITool,
    _encode_doi_for_path,
    _generate_bibtex,
    _generate_citation_key,
    _is_valid_doi,
    _normalize_doi,
    _parse_crossref,
    _parse_datacite,
    _strip_jats_tags,
)


def _make_context(base_dir: Path) -> AgentContext:
    return AgentContext(
        agent_id="test",
        name="test",
        current_depth=0,
        max_depth=3,
        parent_id=None,
        base_dir=base_dir,
        available_tools=[],
        subagents={},
        model_id="test-model",
        messages=[],
        permissions=AgentPermissions(),
    )


# ---------------------------------------------------------------------------
# Fake API responses
# ---------------------------------------------------------------------------

_CROSSREF_RESPONSE = {
    "status": "ok",
    "message-type": "work",
    "message": {
        "DOI": "10.48550/arxiv.1706.03762",
        "title": ["Attention Is All You Need"],
        "author": [
            {
                "given": "Ashish",
                "family": "Vaswani",
                "affiliation": [{"name": "Google Brain"}],
                "ORCID": "https://orcid.org/0000-0001-0001-0001",
            },
            {
                "given": "Noam",
                "family": "Shazeer",
                "affiliation": [],
            },
        ],
        "container-title": ["Advances in Neural Information Processing Systems"],
        "volume": "30",
        "issue": "",
        "page": "",
        "published-print": {"date-parts": [[2017]]},
        "publisher": "Curran Associates, Inc.",
        "ISSN": ["1049-5258"],
        "abstract": "<jats:p>We propose a new simple network architecture.</jats:p>",
        "references-count": 42,
        "license": [{"URL": "https://creativecommons.org/licenses/by/4.0/"}],
        "type": "proceedings-article",
    },
}

_DATACITE_RESPONSE = {
    "data": {
        "attributes": {
            "doi": "10.5281/zenodo.1234567",
            "titles": [{"title": "A Dataset on Neural Networks"}],
            "creators": [
                {
                    "name": "Smith, Jane",
                    "givenName": "Jane",
                    "familyName": "Smith",
                    "affiliation": [{"name": "MIT"}],
                    "nameIdentifiers": [
                        {
                            "nameIdentifierScheme": "ORCID",
                            "nameIdentifier": "https://orcid.org/0000-0002-0002-0002",
                        }
                    ],
                }
            ],
            "container": {
                "title": "Zenodo",
                "volume": "",
                "issue": "",
                "firstPage": "1",
                "lastPage": "10",
            },
            "publicationYear": 2023,
            "publisher": "Zenodo",
            "descriptions": [
                {"descriptionType": "Abstract", "description": "A dataset abstract."}
            ],
            "rightsList": [{"rightsUri": "https://creativecommons.org/licenses/by/4.0/"}],
            "types": {"resourceTypeGeneral": "Dataset"},
        }
    }
}

_UNPAYWALL_RESPONSE = {
    "doi": "10.48550/arxiv.1706.03762",
    "is_oa": True,
    "best_oa_location": {
        "url_for_pdf": "https://arxiv.org/pdf/1706.03762",
        "url_for_landing_page": "https://arxiv.org/abs/1706.03762",
    },
}


# ---------------------------------------------------------------------------
# Helper normalization tests
# ---------------------------------------------------------------------------


def test_normalize_doi_from_https_url() -> None:
    assert _normalize_doi("https://doi.org/10.1234/test") == "10.1234/test"


def test_normalize_doi_from_http_url() -> None:
    assert _normalize_doi("http://doi.org/10.1234/test") == "10.1234/test"


def test_normalize_doi_from_dx_url() -> None:
    assert _normalize_doi("https://dx.doi.org/10.1234/test") == "10.1234/test"


def test_normalize_doi_from_doi_prefix() -> None:
    assert _normalize_doi("doi:10.1234/test") == "10.1234/test"
    assert _normalize_doi("DOI:10.1234/test") == "10.1234/test"


def test_normalize_doi_bare_passthrough() -> None:
    assert _normalize_doi("10.1234/test") == "10.1234/test"


def test_normalize_doi_strips_whitespace() -> None:
    assert _normalize_doi("  10.1234/test  ") == "10.1234/test"


def test_is_valid_doi_accepts_valid() -> None:
    assert _is_valid_doi("10.1234/test") is True
    assert _is_valid_doi("10.48550/arxiv.1706.03762") is True


def test_is_valid_doi_rejects_invalid() -> None:
    assert _is_valid_doi("") is False
    assert _is_valid_doi("not-a-doi") is False
    assert _is_valid_doi("10.") is False
    assert _is_valid_doi("10.1234") is False  # missing slash


def test_encode_doi_for_path_encodes_reserved_chars() -> None:
    assert _encode_doi_for_path("10.1234/test?query#frag") == "10.1234/test%3Fquery%23frag"


def test_encode_doi_for_path_avoids_double_encoding() -> None:
    assert _encode_doi_for_path("10.1234/test%3Fquery") == "10.1234/test%3Fquery"


def test_strip_jats_tags_removes_xml() -> None:
    text = "<jats:p>Hello <jats:bold>world</jats:bold>.</jats:p>"
    assert _strip_jats_tags(text) == "Hello world."


def test_strip_jats_tags_passthrough_plain() -> None:
    text = "No tags here."
    assert _strip_jats_tags(text) == "No tags here."


# ---------------------------------------------------------------------------
# Citation key and BibTeX tests
# ---------------------------------------------------------------------------


def _make_meta(**kwargs) -> DOIMetadata:
    defaults = dict(
        doi="10.1234/test",
        title="Neural Network Attention Mechanisms",
        authors=[AuthorInfo(name="Vaswani Ashish")],
        year=2017,
        venue="NeurIPS",
        entry_type="article",
        source="crossref",
    )
    defaults.update(kwargs)
    return DOIMetadata(**defaults)


def test_generate_citation_key_standard() -> None:
    meta = _make_meta()
    key = _generate_citation_key(meta)
    assert key == "ashish2017neural"


def test_generate_citation_key_family_comma_given() -> None:
    meta = _make_meta(authors=[AuthorInfo(name="Vaswani, Ashish")])
    key = _generate_citation_key(meta)
    assert key == "vaswani2017neural"


def test_generate_citation_key_no_author() -> None:
    meta = _make_meta(authors=[])
    key = _generate_citation_key(meta)
    assert key.startswith("unknown2017")


def test_generate_citation_key_no_year() -> None:
    meta = _make_meta(year=None)
    key = _generate_citation_key(meta)
    assert "nd" in key


def test_generate_bibtex_article() -> None:
    meta = _make_meta(
        authors=[AuthorInfo(name="Vaswani, Ashish"), AuthorInfo(name="Shazeer, Noam")],
    )
    bibtex = _generate_bibtex(meta)
    assert "@article{" in bibtex
    assert "title={Neural Network Attention Mechanisms}" in bibtex
    assert "author={Vaswani, Ashish and Shazeer, Noam}" in bibtex
    assert "journal={NeurIPS}" in bibtex
    assert "year={2017}" in bibtex
    assert "doi={10.1234/test}" in bibtex


def test_generate_bibtex_inproceedings() -> None:
    meta = _make_meta(entry_type="inproceedings", venue="NeurIPS 2017")
    bibtex = _generate_bibtex(meta)
    assert "@inproceedings{" in bibtex
    assert "booktitle={NeurIPS 2017}" in bibtex


def test_generate_bibtex_misc_for_unknown_type() -> None:
    meta = _make_meta(entry_type="misc")
    bibtex = _generate_bibtex(meta)
    assert "@misc{" in bibtex


def test_generate_bibtex_escapes_fields_and_normalizes_whitespace() -> None:
    meta = _make_meta(
        title="Neural {Network}\nAttention",
        authors=[AuthorInfo(name="Doe, Jane {Lab}\nTeam")],
        venue="Journal {X}",
        publisher="Pub\\House {Y}",
    )
    bibtex = _generate_bibtex(meta)
    assert r"title={Neural \{Network\} Attention}" in bibtex
    assert r"author={Doe, Jane \{Lab\} Team}" in bibtex
    assert r"journal={Journal \{X\}}" in bibtex
    assert r"publisher={Pub\\House \{Y\}}" in bibtex


# ---------------------------------------------------------------------------
# CrossRef parsing tests
# ---------------------------------------------------------------------------


def test_parse_crossref_extracts_key_fields() -> None:
    meta = _parse_crossref(_CROSSREF_RESPONSE)
    assert meta.title == "Attention Is All You Need"
    assert len(meta.authors) == 2
    assert meta.authors[0].name == "Ashish Vaswani"
    assert meta.authors[0].affiliation == "Google Brain"
    assert meta.authors[0].orcid == "0000-0001-0001-0001"
    assert meta.venue == "Advances in Neural Information Processing Systems"
    assert meta.year == 2017
    assert meta.publisher == "Curran Associates, Inc."
    assert meta.issn == "1049-5258"
    assert meta.references_count == 42
    assert meta.license_url == "https://creativecommons.org/licenses/by/4.0/"
    assert meta.source == "crossref"
    assert meta.entry_type == "inproceedings"


def test_parse_crossref_strips_jats_from_abstract() -> None:
    meta = _parse_crossref(_CROSSREF_RESPONSE)
    assert "<jats:p>" not in meta.abstract
    assert "We propose a new simple network architecture." in meta.abstract


# ---------------------------------------------------------------------------
# DataCite parsing tests
# ---------------------------------------------------------------------------


def test_parse_datacite_extracts_key_fields() -> None:
    meta = _parse_datacite(_DATACITE_RESPONSE)
    assert meta.title == "A Dataset on Neural Networks"
    assert len(meta.authors) == 1
    assert meta.authors[0].name == "Smith, Jane"
    assert meta.authors[0].affiliation == "MIT"
    assert meta.authors[0].orcid == "0000-0002-0002-0002"
    assert meta.year == 2023
    assert meta.publisher == "Zenodo"
    assert meta.abstract == "A dataset abstract."
    assert meta.entry_type == "misc"
    assert meta.source == "datacite"
    assert meta.pages == "1-10"


def test_parse_datacite_uses_last_page_when_first_missing() -> None:
    data = json.loads(json.dumps(_DATACITE_RESPONSE))
    data["data"]["attributes"]["container"]["firstPage"] = ""
    data["data"]["attributes"]["container"]["lastPage"] = "88"
    meta = _parse_datacite(data)
    assert meta.pages == "88"


# ---------------------------------------------------------------------------
# Tool registration test
# ---------------------------------------------------------------------------


def test_resolve_doi_registered() -> None:
    tools = list_available_tools()
    assert "resolve_doi" in tools


# ---------------------------------------------------------------------------
# Execute method tests
# ---------------------------------------------------------------------------


def test_resolve_doi_empty_doi_returns_error(tmp_path: Path) -> None:
    tool = ResolveDOITool()
    ctx = _make_context(tmp_path)
    output = tool.execute({"doi": ""}, ctx)
    assert "Error" in output
    assert "required" in output.lower()


def test_resolve_doi_missing_doi_returns_error(tmp_path: Path) -> None:
    tool = ResolveDOITool()
    ctx = _make_context(tmp_path)
    output = tool.execute({}, ctx)
    assert "Error" in output
    assert "required" in output.lower()


def test_resolve_doi_invalid_doi_returns_error(tmp_path: Path) -> None:
    tool = ResolveDOITool()
    ctx = _make_context(tmp_path)
    output = tool.execute({"doi": "not-a-doi"}, ctx)
    assert "Error" in output
    assert "invalid" in output.lower()


def test_resolve_doi_crossref_success(tmp_path: Path, monkeypatch) -> None:
    tool = ResolveDOITool()
    ctx = _make_context(tmp_path)

    call_log: list[str] = []

    def _fake_get(url, **kwargs):
        call_log.append(url)
        req = httpx.Request("GET", url)
        if "crossref" in url:
            return httpx.Response(
                200,
                json=_CROSSREF_RESPONSE,
                request=req,
            )
        raise AssertionError(f"Unexpected URL: {url}")

    monkeypatch.setattr("flavia.tools.research.doi_resolver.httpx.get", _fake_get)

    output = tool.execute({"doi": "10.48550/arxiv.1706.03762"}, ctx)

    assert "Attention Is All You Need" in output
    assert "Ashish Vaswani" in output
    assert "https://doi.org/10.48550/arxiv.1706.03762" in output
    assert "BibTeX" in output
    assert "@inproceedings{" in output
    # Unpaywall not called (no email configured)
    assert not any("unpaywall" in u for u in call_log)


def test_resolve_doi_normalizes_url_format(tmp_path: Path, monkeypatch) -> None:
    tool = ResolveDOITool()
    ctx = _make_context(tmp_path)

    captured_url: list[str] = []

    def _fake_get(url, **kwargs):
        captured_url.append(url)
        req = httpx.Request("GET", url)
        return httpx.Response(200, json=_CROSSREF_RESPONSE, request=req)

    monkeypatch.setattr("flavia.tools.research.doi_resolver.httpx.get", _fake_get)

    tool.execute({"doi": "https://doi.org/10.48550/arxiv.1706.03762"}, ctx)

    # Should call CrossRef with bare DOI, not full URL
    assert any("10.48550" in u for u in captured_url)
    assert not any("https://doi.org" in u for u in captured_url)


def test_resolve_doi_encodes_reserved_chars_in_api_path(
    tmp_path: Path, monkeypatch
) -> None:
    tool = ResolveDOITool()
    ctx = _make_context(tmp_path)

    captured_url: list[str] = []

    def _fake_get(url, **kwargs):
        captured_url.append(url)
        req = httpx.Request("GET", url)
        return httpx.Response(200, json=_CROSSREF_RESPONSE, request=req)

    monkeypatch.setattr("flavia.tools.research.doi_resolver.httpx.get", _fake_get)

    tool.execute({"doi": "10.1234/test?query#frag"}, ctx)

    crossref_urls = [u for u in captured_url if "crossref" in u]
    assert crossref_urls
    assert "10.1234/test%3Fquery%23frag" in crossref_urls[0]
    assert "10.1234/test?query#frag" not in crossref_urls[0]


def test_resolve_doi_crossref_404_falls_back_to_datacite(
    tmp_path: Path, monkeypatch
) -> None:
    tool = ResolveDOITool()
    ctx = _make_context(tmp_path)

    def _fake_get(url, **kwargs):
        req = httpx.Request("GET", url)
        if "crossref" in url:
            resp = httpx.Response(404, request=req)
            raise httpx.HTTPStatusError("404 Not Found", request=req, response=resp)
        if "datacite" in url:
            return httpx.Response(200, json=_DATACITE_RESPONSE, request=req)
        raise AssertionError(f"Unexpected URL: {url}")

    monkeypatch.setattr("flavia.tools.research.doi_resolver.httpx.get", _fake_get)

    output = tool.execute({"doi": "10.5281/zenodo.1234567"}, ctx)

    assert "A Dataset on Neural Networks" in output
    assert "Datacite" in output or "datacite" in output.lower()


def test_resolve_doi_both_apis_fail_returns_error(
    tmp_path: Path, monkeypatch
) -> None:
    tool = ResolveDOITool()
    ctx = _make_context(tmp_path)

    def _fake_get(url, **kwargs):
        req = httpx.Request("GET", url)
        resp = httpx.Response(503, request=req)
        raise httpx.HTTPStatusError("503 Service Unavailable", request=req, response=resp)

    monkeypatch.setattr("flavia.tools.research.doi_resolver.httpx.get", _fake_get)

    output = tool.execute({"doi": "10.1234/missing"}, ctx)

    assert "Error" in output
    assert "CrossRef" in output
    assert "DataCite" in output


def test_resolve_doi_unpaywall_enhancement(tmp_path: Path, monkeypatch) -> None:
    tool = ResolveDOITool()
    ctx = _make_context(tmp_path)

    class _StubSettings:
        openalex_email = "test@example.com"

    monkeypatch.setattr(
        "flavia.tools.research.doi_resolver.ResolveDOITool._get_email",
        lambda self: "test@example.com",
    )

    call_log: list[str] = []

    def _fake_get(url, **kwargs):
        call_log.append(url)
        req = httpx.Request("GET", url)
        if "crossref" in url:
            # Return response without OA URL
            data = json.loads(json.dumps(_CROSSREF_RESPONSE))
            return httpx.Response(200, json=data, request=req)
        if "unpaywall" in url:
            return httpx.Response(200, json=_UNPAYWALL_RESPONSE, request=req)
        raise AssertionError(f"Unexpected URL: {url}")

    monkeypatch.setattr("flavia.tools.research.doi_resolver.httpx.get", _fake_get)

    output = tool.execute({"doi": "10.48550/arxiv.1706.03762"}, ctx)

    assert "https://arxiv.org/pdf/1706.03762" in output
    assert any("unpaywall" in u for u in call_log)


def test_resolve_doi_unpaywall_failure_does_not_break(
    tmp_path: Path, monkeypatch
) -> None:
    tool = ResolveDOITool()
    ctx = _make_context(tmp_path)

    monkeypatch.setattr(
        "flavia.tools.research.doi_resolver.ResolveDOITool._get_email",
        lambda self: "test@example.com",
    )

    def _fake_get(url, **kwargs):
        req = httpx.Request("GET", url)
        if "crossref" in url:
            return httpx.Response(200, json=_CROSSREF_RESPONSE, request=req)
        if "unpaywall" in url:
            raise httpx.ConnectError("Network error", request=req)
        raise AssertionError(f"Unexpected URL: {url}")

    monkeypatch.setattr("flavia.tools.research.doi_resolver.httpx.get", _fake_get)

    output = tool.execute({"doi": "10.48550/arxiv.1706.03762"}, ctx)

    # Tool should still succeed despite Unpaywall failure
    assert "Attention Is All You Need" in output
    assert "Error" not in output


def test_resolve_doi_network_error_returns_error(tmp_path: Path, monkeypatch) -> None:
    tool = ResolveDOITool()
    ctx = _make_context(tmp_path)

    def _fake_get(url, **kwargs):
        req = httpx.Request("GET", url)
        raise httpx.ConnectError("dns failure", request=req)

    monkeypatch.setattr("flavia.tools.research.doi_resolver.httpx.get", _fake_get)

    output = tool.execute({"doi": "10.1234/test"}, ctx)

    assert "Error" in output
    assert "network" in output.lower() or "ConnectError" in output


def test_resolve_doi_sends_email_as_mailto_param(
    tmp_path: Path, monkeypatch
) -> None:
    tool = ResolveDOITool()
    ctx = _make_context(tmp_path)

    monkeypatch.setattr(
        "flavia.tools.research.doi_resolver.ResolveDOITool._get_email",
        lambda self: "researcher@university.edu",
    )

    captured_params: list[dict] = []

    def _fake_get(url, params=None, **kwargs):
        if params:
            captured_params.append(dict(params))
        req = httpx.Request("GET", url)
        if "crossref" in url:
            return httpx.Response(200, json=_CROSSREF_RESPONSE, request=req)
        if "unpaywall" in url:
            return httpx.Response(200, json=_UNPAYWALL_RESPONSE, request=req)
        raise AssertionError(f"Unexpected URL: {url}")

    monkeypatch.setattr("flavia.tools.research.doi_resolver.httpx.get", _fake_get)

    tool.execute({"doi": "10.48550/arxiv.1706.03762"}, ctx)

    crossref_params = [p for p in captured_params if "mailto" in p]
    assert crossref_params, "CrossRef request should include mailto param"
    assert crossref_params[0]["mailto"] == "researcher@university.edu"


def test_resolve_doi_http_error_logs_warning(
    tmp_path: Path, monkeypatch, caplog
) -> None:
    tool = ResolveDOITool()
    ctx = _make_context(tmp_path)

    def _fake_get(url, **kwargs):
        req = httpx.Request("GET", url)
        resp = httpx.Response(429, request=req)
        raise httpx.HTTPStatusError("429 Too Many Requests", request=req, response=resp)

    monkeypatch.setattr("flavia.tools.research.doi_resolver.httpx.get", _fake_get)

    caplog.set_level(logging.WARNING, logger="flavia.tools.research.doi_resolver")

    tool.execute({"doi": "10.1234/test"}, ctx)

    messages = [r.getMessage() for r in caplog.records]
    assert any("HTTP error" in m for m in messages)
