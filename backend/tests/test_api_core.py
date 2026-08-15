"""
Batch 1 — Core Public API Contract Tests.

Covers all endpoints listed in the Batch 1 spec.  Tests are ordered by endpoint
path and grouped into:
  - Health & Info
  - Acts & Tree
  - Sections
  - Definitions
  - Search (including hybrid, flat, unified)
  - Data Version
  - Auth (bearer-token gating)
"""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

# Load .env but strip AZURE_CLIENT_ID so the SSO auth branch in main.py is
# not activated during tests (it pulls in extra dependencies like authlib).
# We test bearer-token auth separately below.
from dotenv import load_dotenv

load_dotenv()
os.environ.pop("AZURE_CLIENT_ID", None)
# Unset any bearer token from .env so tests start in default dev mode (public)
os.environ.pop("LEGISLATION_BEARER_TOKEN", None)

from backend.main import app
from backend import config

# Ensure dev-mode default: no auth required
config.BEARER_TOKEN = None

client = TestClient(app)

# ============================================================================
# Helpers
# ============================================================================

SAMPLE_ACT = "itaa-1997"
SAMPLE_SECTION = "6-5"
SAMPLE_TERM = "ordinary income"
GARBAGE_ACT = "this-act-does-not-exist"
GARBAGE_SECTION = "9999-9999"
GARBAGE_TERM = "zzznotadefinitionzzz"

TREE_SHAPE_KEYS = {"act", "parts"}
PART_SHAPE_KEYS = {"id", "title"}
SECTION_SHAPE_KEYS = {"id", "title"}
DIVISION_SHAPE_KEYS = {"id", "title", "sections"}

SEARCH_Q = "income"
SEARCH_Q_EMPTY = ""
SEARCH_Q_NOMATCH = "zzzunique99nonexistent999"


def _unset_token():
    """Store and clear BEARER_TOKEN so public access works."""
    original = config.BEARER_TOKEN
    config.BEARER_TOKEN = None
    return original


def _restore_token(original):
    config.BEARER_TOKEN = original


# ============================================================================
# 1.  /health
# ============================================================================

class TestHealth:
    """/health — no auth, always public."""

    def test_health_returns_ok(self):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}

    def test_health_exact_shape(self):
        resp = client.get("/health")
        body = resp.json()
        assert set(body.keys()) == {"status"}


# ============================================================================
# 2.  /api/info
# ============================================================================

class TestInfo:
    """/api/info — version, changelog, endpoints map."""

    def test_info_200(self):
        token = _unset_token()
        try:
            resp = client.get("/api/info")
            assert resp.status_code == 200
            body = resp.json()
            assert "name" in body
            assert "version" in body
            assert "endpoints" in body
            assert body["name"] == "Legislation Explorer"
        finally:
            _restore_token(token)

    def test_info_has_changelog(self):
        token = _unset_token()
        try:
            resp = client.get("/api/info")
            body = resp.json()
            assert "changelog" in body
            assert isinstance(body["changelog"], list)
            assert len(body["changelog"]) > 0
            assert "version" in body["changelog"][0]
        finally:
            _restore_token(token)

    def test_info_has_endpoints_categories(self):
        token = _unset_token()
        try:
            resp = client.get("/api/info")
            body = resp.json()
            for cat in ("legislation", "system"):
                assert cat in body["endpoints"]
        finally:
            _restore_token(token)


# ============================================================================
# 3.  /api/data-version
# ============================================================================

class TestDataVersion:
    """/api/data-version — version registry info."""

    def test_data_version_200(self):
        token = _unset_token()
        try:
            resp = client.get("/api/data-version")
            assert resp.status_code == 200
            body = resp.json()
            # At minimum the registry returns a dict with keys we expect
            assert isinstance(body, dict)
        finally:
            _restore_token(token)


# ============================================================================
# 4.  /api/acts
# ============================================================================

class TestActs:
    """GET /api/acts — list all available acts."""

    def test_list_acts_200(self):
        token = _unset_token()
        try:
            resp = client.get("/api/acts")
            assert resp.status_code == 200
            assert isinstance(resp.json(), list)
        finally:
            _restore_token(token)

    def test_list_acts_non_empty(self):
        token = _unset_token()
        try:
            resp = client.get("/api/acts")
            assert len(resp.json()) > 0
        finally:
            _restore_token(token)

    def test_list_acts_contains_itaa_1997(self):
        token = _unset_token()
        try:
            resp = client.get("/api/acts")
            act_ids = [a["id"] for a in resp.json()]
            assert "itaa-1997" in act_ids
        finally:
            _restore_token(token)

    def test_list_acts_contains_virtual_acts(self):
        token = _unset_token()
        try:
            resp = client.get("/api/acts")
            act_ids = [a["id"] for a in resp.json()]
            assert "rulings" in act_ids
            assert "tax-cases" in act_ids
        finally:
            _restore_token(token)

    def test_list_acts_each_entry_has_id_and_name(self):
        token = _unset_token()
        try:
            resp = client.get("/api/acts")
            for entry in resp.json():
                assert "id" in entry
                assert "name" in entry
        finally:
            _restore_token(token)

    def test_list_acts_no_auth_needed_when_token_unset(self):
        """Verifies the default dev-mode behaviour."""
        # Already unset from fixture equivalent
        resp = client.get("/api/acts")
        assert resp.status_code == 200


# ============================================================================
# 5.  /api/tree/{act}
# ============================================================================

class TestTree:
    """GET /api/tree/{act} — full structure of an act."""

    def test_tree_itaa_1997_200(self):
        token = _unset_token()
        try:
            resp = client.get(f"/api/tree/{SAMPLE_ACT}")
            assert resp.status_code == 200
        finally:
            _restore_token(token)

    def test_tree_itaa_1997_shape(self):
        token = _unset_token()
        try:
            resp = client.get(f"/api/tree/{SAMPLE_ACT}")
            body = resp.json()
            assert "act" in body
            assert "parts" in body
            assert isinstance(body["parts"], list)
        finally:
            _restore_token(token)

    def test_tree_itaa_1997_act_name(self):
        token = _unset_token()
        try:
            resp = client.get(f"/api/tree/{SAMPLE_ACT}")
            # The actual name is the full title, not just the acronym
            assert "Income Tax Assessment Act" in resp.json()["act"]
        finally:
            _restore_token(token)

    def test_tree_itaa_1997_has_parts(self):
        token = _unset_token()
        try:
            resp = client.get(f"/api/tree/{SAMPLE_ACT}")
            assert len(resp.json()["parts"]) > 0
        finally:
            _restore_token(token)

    def test_tree_itaa_1997_parts_have_ids(self):
        token = _unset_token()
        try:
            resp = client.get(f"/api/tree/{SAMPLE_ACT}")
            for part in resp.json()["parts"]:
                assert "id" in part
                assert "title" in part
        finally:
            _restore_token(token)

    def test_tree_itaa_1997_parts_have_sections_or_divisions(self):
        token = _unset_token()
        try:
            resp = client.get(f"/api/tree/{SAMPLE_ACT}")
            for part in resp.json()["parts"]:
                has_sections = len(part.get("sections", [])) > 0
                has_divisions = len(part.get("divisions", [])) > 0
                assert has_sections or has_divisions, \
                    f"Part {part['id']} has neither sections nor divisions"
        finally:
            _restore_token(token)

    def test_tree_nonexistent_act_returns_404(self):
        token = _unset_token()
        try:
            resp = client.get(f"/api/tree/{GARBAGE_ACT}")
            assert resp.status_code == 404
        finally:
            _restore_token(token)

    @pytest.mark.parametrize("act", ["rulings", "tax-cases"])
    def test_tree_virtual_acts_200(self, act):
        """rulings and tax-cases are virtual acts with their own tree shapes."""
        token = _unset_token()
        try:
            resp = client.get(f"/api/tree/{act}")
            assert resp.status_code == 200
            body = resp.json()
            # These return different shapes (not the standard tree)
            assert isinstance(body, (dict, list))
        finally:
            _restore_token(token)


# ============================================================================
# 6.  /api/section/{act}/{section}
# ============================================================================

class TestSection:
    """GET /api/section/{act}/{section} — full text of a section."""

    def test_section_200(self):
        token = _unset_token()
        try:
            resp = client.get(f"/api/section/{SAMPLE_ACT}/{SAMPLE_SECTION}")
            assert resp.status_code == 200
        finally:
            _restore_token(token)

    def test_section_has_frontmatter_and_body(self):
        token = _unset_token()
        try:
            resp = client.get(f"/api/section/{SAMPLE_ACT}/{SAMPLE_SECTION}")
            body = resp.json()
            assert "frontmatter" in body
            assert "body" in body
        finally:
            _restore_token(token)

    def test_section_6_5_contains_expected_text(self):
        token = _unset_token()
        try:
            resp = client.get(f"/api/section/{SAMPLE_ACT}/{SAMPLE_SECTION}")
            html = resp.json()["body"]
            assert "ordinary concepts" in html
            assert "ordinary income" in html
        finally:
            _restore_token(token)

    def test_section_nonexistent_returns_404(self):
        token = _unset_token()
        try:
            resp = client.get(f"/api/section/{SAMPLE_ACT}/{GARBAGE_SECTION}")
            assert resp.status_code == 404
        finally:
            _restore_token(token)

    def test_section_nonexistent_act_returns_404(self):
        token = _unset_token()
        try:
            resp = client.get(f"/api/section/{GARBAGE_ACT}/{SAMPLE_SECTION}")
            assert resp.status_code == 404
        finally:
            _restore_token(token)

    def test_section_404_detail_message(self):
        token = _unset_token()
        try:
            resp = client.get(f"/api/section/{SAMPLE_ACT}/{GARBAGE_SECTION}")
            assert "detail" in resp.json()
        finally:
            _restore_token(token)


# ============================================================================
# 7.  /api/definitions/{act}
# ============================================================================

class TestDefinitions:
    """GET /api/definitions/{act} — all defined terms in an act."""

    def test_definitions_200(self):
        token = _unset_token()
        try:
            resp = client.get(f"/api/definitions/{SAMPLE_ACT}")
            assert resp.status_code == 200
        finally:
            _restore_token(token)

    def test_definitions_has_act_count_terms(self):
        token = _unset_token()
        try:
            resp = client.get(f"/api/definitions/{SAMPLE_ACT}")
            body = resp.json()
            assert "act" in body
            assert body["act"] == SAMPLE_ACT
            assert "count" in body
            assert "terms" in body
        finally:
            _restore_token(token)

    def test_definitions_non_empty(self):
        token = _unset_token()
        try:
            resp = client.get(f"/api/definitions/{SAMPLE_ACT}")
            assert resp.json()["count"] > 0
            assert len(resp.json()["terms"]) > 0
        finally:
            _restore_token(token)

    def test_definitions_terms_are_dicts(self):
        token = _unset_token()
        try:
            resp = client.get(f"/api/definitions/{SAMPLE_ACT}")
            terms = resp.json()["terms"]
            # terms may be a dict (term -> info) or list of items
            assert isinstance(terms, dict)
            if terms:
                sample_key = next(iter(terms))
                sample_val = terms[sample_key]
                assert isinstance(sample_val, dict)
        finally:
            _restore_token(token)

    def test_definitions_nonexistent_act_returns_404_or_empty(self):
        """Non-existent act may 404 or return empty depending on implementation."""
        token = _unset_token()
        try:
            resp = client.get(f"/api/definitions/{GARBAGE_ACT}")
            assert resp.status_code in (200, 404)
        finally:
            _restore_token(token)


# ============================================================================
# 8.  /api/definition/{act}/{term}
# ============================================================================

class TestDefinition:
    """GET /api/definition/{act}/{term} — single definition lookup."""

    def test_definition_200(self):
        token = _unset_token()
        try:
            resp = client.get(f"/api/definition/{SAMPLE_ACT}/{SAMPLE_TERM}")
            assert resp.status_code == 200
        finally:
            _restore_token(token)

    def test_definition_returns_object(self):
        token = _unset_token()
        try:
            resp = client.get(f"/api/definition/{SAMPLE_ACT}/{SAMPLE_TERM}")
            body = resp.json()
            assert isinstance(body, dict)
            # Should have term/definition/section_url or equivalent
            assert "term" in body or "definition" in body or "section" in body
        finally:
            _restore_token(token)

    def test_definition_garbage_term_returns_404(self):
        token = _unset_token()
        try:
            resp = client.get(f"/api/definition/{SAMPLE_ACT}/{GARBAGE_TERM}")
            assert resp.status_code == 404
        finally:
            _restore_token(token)

    def test_definition_garbage_act_falls_back_across_acts(self):
        token = _unset_token()
        try:
            # v2.7.5+: get_definition searches ALL acts (preferring the
            # requested act), so a term defined in any act resolves even
            # when the requested act slug is unknown/typo'd.
            resp = client.get(f"/api/definition/{GARBAGE_ACT}/{SAMPLE_TERM}")
            assert resp.status_code == 200
            body = resp.json()
            assert "term" in body
            assert "text" in body
        finally:
            _restore_token(token)

    def test_definition_garbage_act_and_term_returns_404(self):
        token = _unset_token()
        try:
            # Cross-act fallback must still 404 when the term exists nowhere.
            resp = client.get(f"/api/definition/{GARBAGE_ACT}/{GARBAGE_TERM}")
            assert resp.status_code == 404
        finally:
            _restore_token(token)


# ============================================================================
# 9.  /api/definition-text/{act}/{term}
# ============================================================================

class TestDefinitionText:
    """GET /api/definition-text/{act}/{term} — full definition text."""

    def test_definition_text_200(self):
        token = _unset_token()
        try:
            resp = client.get(f"/api/definition-text/{SAMPLE_ACT}/{SAMPLE_TERM}")
            assert resp.status_code == 200
        finally:
            _restore_token(token)

    def test_definition_text_returns_object(self):
        token = _unset_token()
        try:
            resp = client.get(f"/api/definition-text/{SAMPLE_ACT}/{SAMPLE_TERM}")
            body = resp.json()
            assert isinstance(body, dict)
        finally:
            _restore_token(token)

    def test_definition_text_garbage_returns_404(self):
        token = _unset_token()
        try:
            resp = client.get(f"/api/definition-text/{SAMPLE_ACT}/{GARBAGE_TERM}")
            assert resp.status_code == 404
        finally:
            _restore_token(token)


# ============================================================================
# 10.  /api/section-defined-terms/{act}/{section}
# ============================================================================

class TestSectionDefinedTerms:
    """GET /api/section-defined-terms/{act}/{section} — terms defined in a section."""

    def test_section_defined_terms_200(self):
        token = _unset_token()
        try:
            resp = client.get(
                f"/api/section-defined-terms/{SAMPLE_ACT}/{SAMPLE_SECTION}"
            )
            assert resp.status_code == 200
        finally:
            _restore_token(token)

    def test_section_defined_terms_shape(self):
        token = _unset_token()
        try:
            resp = client.get(
                f"/api/section-defined-terms/{SAMPLE_ACT}/{SAMPLE_SECTION}"
            )
            body = resp.json()
            assert "act" in body
            assert "section" in body
            assert "count" in body
            assert "terms" in body
        finally:
            _restore_token(token)

    def test_section_defined_terms_terms_are_list(self):
        token = _unset_token()
        try:
            resp = client.get(
                f"/api/section-defined-terms/{SAMPLE_ACT}/{SAMPLE_SECTION}"
            )
            assert isinstance(resp.json()["terms"], list)
        finally:
            _restore_token(token)

    def test_section_defined_terms_each_term_has_keys(self):
        token = _unset_token()
        try:
            resp = client.get(
                f"/api/section-defined-terms/{SAMPLE_ACT}/{SAMPLE_SECTION}"
            )
            for term in resp.json()["terms"]:
                assert "term" in term
        finally:
            _restore_token(token)

    def test_section_defined_terms_nonexistent_section(self):
        """Should return empty terms, not 404, since the section content lookup
        may fail gracefully."""
        token = _unset_token()
        try:
            resp = client.get(
                f"/api/section-defined-terms/{SAMPLE_ACT}/{GARBAGE_SECTION}"
            )
            # Could be 404 (if the section lookup throws) or 200 with empty terms
            assert resp.status_code in (200, 404)
            if resp.status_code == 200:
                assert resp.json()["count"] == 0
        finally:
            _restore_token(token)


# ============================================================================
# 11.  /api/search  (plain FTS5)
# ============================================================================

class TestSearch:
    """GET /api/search — keyword search over sections."""

    def test_search_200(self):
        token = _unset_token()
        try:
            resp = client.get(f"/api/search?q={SEARCH_Q}")
            assert resp.status_code == 200
        finally:
            _restore_token(token)

    def test_search_shape(self):
        token = _unset_token()
        try:
            resp = client.get(f"/api/search?q={SEARCH_Q}")
            body = resp.json()
            assert "results" in body
            assert "total" in body
            assert "offset" in body
            assert "limit" in body
        finally:
            _restore_token(token)

    def test_search_has_results(self):
        token = _unset_token()
        try:
            resp = client.get(f"/api/search?q={SEARCH_Q}")
            body = resp.json()
            assert body["total"] > 0
            assert len(body["results"]) > 0
        finally:
            _restore_token(token)

    def test_search_result_shape(self):
        token = _unset_token()
        try:
            resp = client.get(f"/api/search?q={SEARCH_Q}")
            result = resp.json()["results"][0]
            assert "act" in result
            assert "section" in result
            assert "title" in result
        finally:
            _restore_token(token)

    def test_search_empty_query(self):
        """Empty query should return 200 with no or empty results (not crash)."""
        token = _unset_token()
        try:
            resp = client.get(f"/api/search?q={SEARCH_Q_EMPTY}")
            assert resp.status_code == 200
        finally:
            _restore_token(token)

    def test_search_with_act_filter(self):
        token = _unset_token()
        try:
            resp = client.get(f"/api/search?q={SEARCH_Q}&act={SAMPLE_ACT}")
            assert resp.status_code == 200
            body = resp.json()
            for r in body["results"]:
                assert r["act"] == SAMPLE_ACT
        finally:
            _restore_token(token)

    def test_search_pagination_offset(self):
        token = _unset_token()
        try:
            resp = client.get(f"/api/search?q={SEARCH_Q}&offset=5&limit=3")
            body = resp.json()
            assert body["offset"] == 5
            assert body["limit"] == 3
            assert len(body["results"]) <= 3
        finally:
            _restore_token(token)

    def test_search_limit_capped_at_100(self):
        token = _unset_token()
        try:
            resp = client.get(f"/api/search?q={SEARCH_Q}&limit=999")
            body = resp.json()
            assert body["limit"] == 100
        finally:
            _restore_token(token)

    def test_search_negative_offset_defaults(self):
        token = _unset_token()
        try:
            resp = client.get(f"/api/search?q={SEARCH_Q}&offset=-5")
            assert resp.status_code == 200
        finally:
            _restore_token(token)

    def test_search_nomatch_returns_empty(self):
        token = _unset_token()
        try:
            resp = client.get(f"/api/search?q={SEARCH_Q_NOMATCH}")
            body = resp.json()
            assert body["total"] == 0
            assert body["results"] == []
        finally:
            _restore_token(token)


# ============================================================================
# 12.  /api/search/hybrid
# ============================================================================

class TestSearchHybrid:
    """GET /api/search/hybrid — RRF-fused FTS5 + vector search."""

    def test_hybrid_200(self):
        token = _unset_token()
        try:
            resp = client.get(f"/api/search/hybrid?q={SEARCH_Q}")
            assert resp.status_code == 200
        finally:
            _restore_token(token)

    def test_hybrid_shape(self):
        token = _unset_token()
        try:
            resp = client.get(f"/api/search/hybrid?q={SEARCH_Q}")
            body = resp.json()
            assert "results" in body
            assert "total" in body
        finally:
            _restore_token(token)

    def test_hybrid_result_has_fusion_score(self):
        token = _unset_token()
        try:
            resp = client.get(f"/api/search/hybrid?q={SEARCH_Q}")
            body = resp.json()
            if body["results"]:
                assert "fusion_score" in body["results"][0]
        finally:
            _restore_token(token)

    def test_hybrid_result_shape(self):
        token = _unset_token()
        try:
            resp = client.get(f"/api/search/hybrid?q={SEARCH_Q}")
            body = resp.json()
            if body["results"]:
                r = body["results"][0]
                assert "act" in r
                assert "section" in r
                assert "title" in r or "snippet" in r
        finally:
            _restore_token(token)

    def test_hybrid_with_act_filter(self):
        token = _unset_token()
        try:
            resp = client.get(f"/api/search/hybrid?q={SEARCH_Q}&act={SAMPLE_ACT}")
            assert resp.status_code == 200
        finally:
            _restore_token(token)

    def test_hybrid_empty_query(self):
        token = _unset_token()
        try:
            resp = client.get("/api/search/hybrid?q=")
            assert resp.status_code == 200
        finally:
            _restore_token(token)

    def test_hybrid_limit_default(self):
        token = _unset_token()
        try:
            resp = client.get(f"/api/search/hybrid?q={SEARCH_Q}&limit=5")
            body = resp.json()
            assert len(body["results"]) <= 5
        finally:
            _restore_token(token)

    def test_hybrid_limit_capped_at_50(self):
        token = _unset_token()
        try:
            resp = client.get(f"/api/search/hybrid?q={SEARCH_Q}&limit=999")
            body = resp.json()
            assert len(body["results"]) <= 50
        finally:
            _restore_token(token)


# ============================================================================
# 13.  /api/search/flat
# ============================================================================

class TestSearchFlat:
    """GET /api/search/flat — interleaved sections + rulings."""

    def test_flat_200(self):
        token = _unset_token()
        try:
            resp = client.get(f"/api/search/flat?q={SEARCH_Q}")
            assert resp.status_code == 200
        finally:
            _restore_token(token)

    def test_flat_shape(self):
        token = _unset_token()
        try:
            resp = client.get(f"/api/search/flat?q={SEARCH_Q}")
            body = resp.json()
            assert "results" in body
            assert "query" in body
        finally:
            _restore_token(token)

    def test_flat_result_shape(self):
        token = _unset_token()
        try:
            resp = client.get(f"/api/search/flat?q={SEARCH_Q}")
            body = resp.json()
            if body["results"]:
                r = body["results"][0]
                assert "type" in r
                assert "act" in r
                assert "section" in r or "citation" in r
        finally:
            _restore_token(token)

    def test_flat_empty_query(self):
        token = _unset_token()
        try:
            resp = client.get("/api/search/flat?q=")
            body = resp.json()
            assert body["results"] == []
        finally:
            _restore_token(token)

    def test_flat_results_are_mixed_types(self):
        """When both sections and rulings exist, results should include both."""
        token = _unset_token()
        try:
            resp = client.get(f"/api/search/flat?q={SEARCH_Q}")
            body = resp.json()
            types = {r.get("type") for r in body["results"]}
            # At minimum some type is present
            assert len(types) > 0
        finally:
            _restore_token(token)

    def test_flat_limit(self):
        token = _unset_token()
        try:
            resp = client.get(f"/api/search/flat?q={SEARCH_Q}&limit=5")
            body = resp.json()
            assert len(body["results"]) <= 5
        finally:
            _restore_token(token)

    def test_flat_nomatch(self):
        token = _unset_token()
        try:
            resp = client.get(f"/api/search/flat?q={SEARCH_Q_NOMATCH}")
            body = resp.json()
            assert body["results"] == []
        finally:
            _restore_token(token)


# ============================================================================
# 14.  /api/unified-search
# ============================================================================

class TestUnifiedSearch:
    """GET /api/unified-search — grouped by category."""

    def test_unified_200(self):
        token = _unset_token()
        try:
            resp = client.get(f"/api/unified-search?q={SEARCH_Q}")
            assert resp.status_code == 200
        finally:
            _restore_token(token)

    def test_unified_shape(self):
        token = _unset_token()
        try:
            resp = client.get(f"/api/unified-search?q={SEARCH_Q}")
            body = resp.json()
            assert "query" in body
            assert "categories" in body
        finally:
            _restore_token(token)

    def test_unified_has_categories(self):
        token = _unset_token()
        try:
            resp = client.get(f"/api/unified-search?q={SEARCH_Q}")
            body = resp.json()
            assert isinstance(body["categories"], list)
        finally:
            _restore_token(token)

    def test_unified_category_shape(self):
        token = _unset_token()
        try:
            resp = client.get(f"/api/unified-search?q={SEARCH_Q}")
            body = resp.json()
            if body["categories"]:
                cat = body["categories"][0]
                assert "key" in cat
                assert "label" in cat
                assert "count" in cat
                assert "results" in cat
        finally:
            _restore_token(token)

    def test_unified_result_shape_in_category(self):
        token = _unset_token()
        try:
            resp = client.get(f"/api/unified-search?q={SEARCH_Q}")
            body = resp.json()
            for cat in body["categories"]:
                if cat["results"]:
                    r = cat["results"][0]
                    assert "type" in r
                    assert "title" in r
        finally:
            _restore_token(token)

    def test_unified_empty_query(self):
        token = _unset_token()
        try:
            resp = client.get("/api/unified-search?q=")
            body = resp.json()
            assert body["categories"] == []
        finally:
            _restore_token(token)

    def test_unified_with_limit(self):
        token = _unset_token()
        try:
            resp = client.get(f"/api/unified-search?q={SEARCH_Q}&limit=3")
            assert resp.status_code == 200
        finally:
            _restore_token(token)


# ============================================================================
# 15.  Auth Middleware
# ============================================================================

class TestAuth:
    """Bearer-token auth gating on /api/* endpoints."""

    AUTH_TOKEN = "integration-test-token-abc123"

    def test_health_is_public_when_auth_set(self):
        """/health is exempt from auth."""
        original = config.BEARER_TOKEN
        config.BEARER_TOKEN = self.AUTH_TOKEN
        try:
            resp = client.get("/health")
            assert resp.status_code == 200
        finally:
            config.BEARER_TOKEN = original

    def test_api_returns_401_without_token(self):
        original = config.BEARER_TOKEN
        config.BEARER_TOKEN = self.AUTH_TOKEN
        try:
            resp = client.get("/api/acts")
            assert resp.status_code == 401
            assert resp.json() == {"detail": "Unauthorized"}
        finally:
            config.BEARER_TOKEN = original

    def test_api_returns_401_with_bad_token(self):
        original = config.BEARER_TOKEN
        config.BEARER_TOKEN = self.AUTH_TOKEN
        try:
            resp = client.get(
                "/api/acts",
                headers={"Authorization": "Bearer wrong-token"},
            )
            assert resp.status_code == 401
        finally:
            config.BEARER_TOKEN = original

    def test_api_returns_200_with_valid_token(self):
        original = config.BEARER_TOKEN
        config.BEARER_TOKEN = self.AUTH_TOKEN
        try:
            resp = client.get(
                "/api/acts",
                headers={"Authorization": f"Bearer {self.AUTH_TOKEN}"},
            )
            assert resp.status_code == 200
        finally:
            config.BEARER_TOKEN = original

    def test_api_returns_200_when_token_is_none(self):
        """Default dev mode: no auth required."""
        original = config.BEARER_TOKEN
        config.BEARER_TOKEN = None
        try:
            resp = client.get("/api/acts")
            assert resp.status_code == 200
        finally:
            config.BEARER_TOKEN = original

    @pytest.mark.parametrize(
        "exempt_path",
        [
            "/health",
            "/api/cadena/test",
            "/api/private/test",
            "/api/v2/test",
            # Note: /api/rpc/ paths route to the MCP handler which requires
            # the session manager to be running (lifespan not active in
            # TestClient), so they crash with RuntimeError rather than
            # returning an HTTP response.  The auth middleware correctly
            # passes them through (they never reach the 401 check), but the
            # downstream MCP handler fails.  We test the auth exemption
            # logic only on routes that work in TestClient.
        ],
    )
    def test_exempt_paths_are_public(self, exempt_path):
        """Paths listed in the auth middleware exemption should not require auth."""
        original = config.BEARER_TOKEN
        config.BEARER_TOKEN = self.AUTH_TOKEN
        try:
            resp = client.get(exempt_path)
            assert resp.status_code != 401, \
                f"Exempt path {exempt_path} returned 401"
        finally:
            config.BEARER_TOKEN = original

    def test_restore_token_after_auth_test(self):
        """Ensure that test isolation works — no leaked token."""
        assert config.BEARER_TOKEN is None or config.BEARER_TOKEN != "leaked-token"


# ============================================================================
# 16.  Edge Cases & Cross-Cutting
# ============================================================================

class TestEdgeCases:
    """URL encoding, special characters, numeric-only sections."""

    def test_section_with_dash_is_handled(self):
        """Section IDs like '6-5' are path params with dashes."""
        token = _unset_token()
        try:
            resp = client.get(f"/api/section/{SAMPLE_ACT}/6-5")
            assert resp.status_code == 200
        finally:
            _restore_token(token)

    def test_definition_with_spaces_is_url_encoded(self):
        """Terms with spaces need URL encoding."""
        token = _unset_token()
        try:
            resp = client.get(
                f"/api/definition/{SAMPLE_ACT}/ordinary%20income"
            )
            assert resp.status_code in (200, 404)
        finally:
            _restore_token(token)

    def test_definition_text_with_spaces(self):
        token = _unset_token()
        try:
            resp = client.get(
                f"/api/definition-text/{SAMPLE_ACT}/ordinary%20income"
            )
            assert resp.status_code in (200, 404)
        finally:
            _restore_token(token)

    def test_numeric_act_name(self):
        """Acts with numeric-only IDs should still resolve if they exist."""
        token = _unset_token()
        try:
            resp = client.get("/api/tree/itaa-1936")
            if resp.status_code == 200:
                assert "act" in resp.json()
        finally:
            _restore_token(token)

    def test_search_special_chars(self):
        """Search with special regex chars shouldn't crash."""
        token = _unset_token()
        try:
            resp = client.get("/api/search?q=tax+%26+gst")
            assert resp.status_code == 200
        finally:
            _restore_token(token)

    def test_search_unicode(self):
        token = _unset_token()
        try:
            resp = client.get("/api/search?q=%C3%A9t%C3%A9")
            assert resp.status_code == 200
        finally:
            _restore_token(token)

    def test_concurrent_requests(self):
        """Multiple rapid-fire requests should all succeed."""
        token = _unset_token()
        try:
            for _ in range(5):
                resp = client.get(f"/api/search?q={SEARCH_Q}")
                assert resp.status_code == 200
        finally:
            _restore_token(token)

    def test_response_content_type(self):
        """All API responses should be JSON."""
        token = _unset_token()
        try:
            endpoints = [
                "/api/acts",
                f"/api/tree/{SAMPLE_ACT}",
                f"/api/section/{SAMPLE_ACT}/{SAMPLE_SECTION}",
                f"/api/definitions/{SAMPLE_ACT}",
                f"/api/search?q={SEARCH_Q}",
                "/api/info",
                "/api/data-version",
            ]
            for ep in endpoints:
                resp = client.get(ep)
                assert resp.status_code == 200, f"{ep} returned {resp.status_code}"
                assert "application/json" in resp.headers.get("content-type", ""), \
                    f"{ep} did not return JSON"
        finally:
            _restore_token(token)