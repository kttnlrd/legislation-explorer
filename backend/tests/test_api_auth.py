"""Layer 1 — API Contract Tests for Batch 3 (Auth + MCP + Admin) endpoints.

Auth mechanism (backend/main.py lines 112-124):
  - When config.BEARER_TOKEN is None → all /api/ routes are public
  - When config.BEARER_TOKEN is set → requires Authorization: Bearer <token>

SSO (Azure AD) is not configured in tests (no AZURE_CLIENT_ID),
so routes that call _get_user() / _require_user() / _require_admin()
will always return 401 from the route handler.

Endpoint auth classification:
  PublicRead — bearer middleware applies, route has NO SSO check
  SSOOnly   — bearer middleware applies AND route checks SSO session
"""

import os
import pytest
from fastapi.testclient import TestClient
from dotenv import load_dotenv

load_dotenv()

# .env has AZURE_CLIENT_ID set, which would cause main.py to
# import SSO auth modules (authlib, etc.) that may not be installed.
# We must clear these BEFORE importing backend.main.
os.environ.pop("AZURE_CLIENT_ID", None)
os.environ.pop("AZURE_TENANT_ID", None)
os.environ.pop("AZURE_CLIENT_SECRET", None)

from backend.main import app
from backend import config

client = TestClient(app)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def token_disabled():
    """Temporarily disable bearer token auth."""
    original = config.BEARER_TOKEN
    config.BEARER_TOKEN = None
    yield
    config.BEARER_TOKEN = original


@pytest.fixture
def token_enabled():
    """Enable bearer token auth with a test token."""
    original = config.BEARER_TOKEN
    config.BEARER_TOKEN = "testtoken123"
    yield
    config.BEARER_TOKEN = original


# =============================================================================
# GET /api/comments/{act}/{section} — PublicRead
# =============================================================================

class TestListComments:

    def test_public_without_auth(self, token_disabled):
        """Access comments publicly when no bearer token is configured."""
        response = client.get("/api/comments/itaa-1997/6-5")
        assert response.status_code == 200
        data = response.json()
        assert "act" in data
        assert "section" in data
        assert "count" in data
        assert "comments" in data

    def test_no_token_returns_401(self, token_enabled):
        """Returns 401 when BEARER_TOKEN is set but no Authorization header."""
        response = client.get("/api/comments/itaa-1997/6-5")
        assert response.status_code == 401
        assert response.json() == {"detail": "Unauthorized"}

    def test_with_valid_token(self, token_enabled):
        """Returns 200 with valid bearer token."""
        response = client.get(
            "/api/comments/itaa-1997/6-5",
            headers={"Authorization": "Bearer testtoken123"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "comments" in data

    def test_with_invalid_token(self, token_enabled):
        """Returns 401 with invalid bearer token."""
        response = client.get(
            "/api/comments/itaa-1997/6-5",
            headers={"Authorization": "Bearer wrongtoken"},
        )
        assert response.status_code == 401
        assert response.json() == {"detail": "Unauthorized"}

    def test_malformed_auth_header(self, token_enabled):
        """Returns 401 with malformed Authorization header."""
        response = client.get(
            "/api/comments/itaa-1997/6-5",
            headers={"Authorization": "NotBearer testtoken123"},
        )
        assert response.status_code == 401

    def test_empty_act_section(self, token_disabled):
        """Returns 200 with empty lists for non-existent act/section."""
        response = client.get("/api/comments/nonexistent/nonexistent")
        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 0


# =============================================================================
# POST /api/comments — SSOOnly (no SSO → always 401 in tests)
# =============================================================================

class TestCreateComment:

    VALID_PAYLOAD = {"act": "itaa-1997", "section": "6-5", "text": "Test comment text"}

    def test_no_auth_public_mode(self, token_disabled):
        """Returns 401 from route handler (no SSO session) even in public mode."""
        response = client.post("/api/comments", json=self.VALID_PAYLOAD)
        assert response.status_code == 401
        assert "Login required" in response.json().get("detail", "")

    def test_no_token_returns_401(self, token_enabled):
        """Returns 401 when BEARER_TOKEN is set but no Authorization header."""
        response = client.post("/api/comments", json=self.VALID_PAYLOAD)
        assert response.status_code == 401

    def test_with_valid_token_still_401(self, token_enabled):
        """Returns 401 even with valid bearer token (no SSO session)."""
        response = client.post(
            "/api/comments",
            json=self.VALID_PAYLOAD,
            headers={"Authorization": "Bearer testtoken123"},
        )
        assert response.status_code == 401
        assert "Login required" in response.json().get("detail", "")

    def test_invalid_payload(self, token_disabled):
        """Returns 422 for invalid payload (missing required fields)."""
        response = client.post("/api/comments", json={})
        assert response.status_code == 422

    def test_empty_text(self, token_disabled):
        """Returns 422 for missing text field."""
        response = client.post("/api/comments", json={"act": "itaa-1997", "section": "6-5"})
        assert response.status_code == 422


# =============================================================================
# POST /api/comments/resolve — SSOOnly (no SSO → always 401 in tests)
# =============================================================================

class TestResolveComment:

    def test_no_auth_public_mode(self, token_disabled):
        """Returns 401 from route handler (no SSO session)."""
        response = client.post("/api/comments/resolve", json={"comment_id": 1})
        assert response.status_code == 401
        assert "Login required" in response.json().get("detail", "")

    def test_no_token_returns_401(self, token_enabled):
        """Returns 401 when BEARER_TOKEN is set but no Authorization header."""
        response = client.post("/api/comments/resolve", json={"comment_id": 1})
        assert response.status_code == 401

    def test_with_valid_token_still_401(self, token_enabled):
        """Returns 401 even with valid bearer token (no SSO session)."""
        response = client.post(
            "/api/comments/resolve",
            json={"comment_id": 1},
            headers={"Authorization": "Bearer testtoken123"},
        )
        assert response.status_code == 401
        assert "Login required" in response.json().get("detail", "")


# =============================================================================
# GET /api/issues — PublicRead (no SSO check in route handler)
# =============================================================================

class TestListIssues:

    def test_public_without_auth(self, token_disabled):
        """Access issues publicly when no bearer token is configured."""
        response = client.get("/api/issues")
        assert response.status_code == 200
        data = response.json()
        assert "issues" in data
        assert "total" in data
        assert isinstance(data["issues"], list)

    def test_no_token_returns_401(self, token_enabled):
        """Returns 401 when BEARER_TOKEN is set but no Authorization header."""
        response = client.get("/api/issues")
        assert response.status_code == 401
        assert response.json() == {"detail": "Unauthorized"}

    def test_with_valid_token(self, token_enabled):
        """Returns 200 with valid bearer token."""
        response = client.get(
            "/api/issues",
            headers={"Authorization": "Bearer testtoken123"},
        )
        assert response.status_code == 200
        assert "issues" in response.json()

    def test_filter_by_status(self, token_disabled):
        """Can filter issues by status query param."""
        response = client.get("/api/issues?status=open")
        assert response.status_code == 200
        data = response.json()
        assert "issues" in data

    def test_invalid_status(self, token_disabled):
        """Invalid status still returns a list (no server-side validation)."""
        response = client.get("/api/issues?status=nonexistent")
        assert response.status_code == 200
        assert isinstance(response.json()["issues"], list)


# =============================================================================
# POST /api/issues — PublicRead (no SSO check in route handler)
# =============================================================================

class TestCreateIssue:

    @pytest.fixture(autouse=True)
    def _no_live_db_writes(self, monkeypatch):
        """Keep auth-contract tests from writing real tickets to the live DB.

        Previously every test-suite run inserted "Test issue" / "Auth test issue"
        rows into cadena_knowledge.issues, polluting the bug queue (CDN-0105–0113
        etc). These tests verify auth + response shape only, so stub the route's
        DB helpers: no INSERT ever reaches the database.
        """
        import backend.routes.issues as issues_route

        def fake_dict(columns, query):
            if "MAX(id)" in query:
                return [{"next_id": 900000}]
            return []

        monkeypatch.setattr(issues_route, "_sql_write", lambda sql: True)
        monkeypatch.setattr(issues_route, "_sql_dict", fake_dict)

    def test_public_without_auth(self, token_disabled):
        """Create issue publicly when no bearer token is configured."""
        response = client.post(
            "/api/issues",
            json={"category": "bug", "tool": "test-tool", "note": "Test issue"},
        )
        # Returns 200 with ticket info — DB may not be available in test,
        # but the route code handles failures gracefully.
        assert response.status_code == 200
        data = response.json()
        assert "ticket" in data
        assert "status" in data

    def test_no_token_returns_401(self, token_enabled):
        """Returns 401 when BEARER_TOKEN is set but no Authorization header."""
        response = client.post(
            "/api/issues",
            json={"category": "bug", "note": "Test"},
        )
        assert response.status_code == 401

    def test_with_valid_token(self, token_enabled):
        """Returns 200 with valid bearer token."""
        response = client.post(
            "/api/issues",
            json={"category": "bug", "tool": "test-tool", "note": "Auth test issue"},
            headers={"Authorization": "Bearer testtoken123"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "ticket" in data


# =============================================================================
# GET /api/user/prefs — SSOOnly (no SSO → always 401 in tests)
# =============================================================================

class TestGetUserPrefs:

    def test_no_auth_public_mode(self, token_disabled):
        """Returns 401 from route handler (no SSO session)."""
        response = client.get("/api/user/prefs")
        assert response.status_code == 401
        assert "Login required" in response.json().get("error", "")

    def test_no_token_returns_401(self, token_enabled):
        """Returns 401 when BEARER_TOKEN is set but no Authorization header."""
        response = client.get("/api/user/prefs")
        assert response.status_code == 401

    def test_with_valid_token_still_401(self, token_enabled):
        """Returns 401 even with valid bearer token (no SSO session)."""
        response = client.get(
            "/api/user/prefs",
            headers={"Authorization": "Bearer testtoken123"},
        )
        assert response.status_code == 401
        assert "Login required" in response.json().get("error", "")


# =============================================================================
# PUT /api/user/prefs — SSOOnly (no SSO → always 401 in tests)
# =============================================================================

class TestUpdateUserPrefs:

    VALID_PAYLOAD = {"theme": "light", "default_act": "gst"}

    def test_no_auth_public_mode(self, token_disabled):
        """Returns 401 from route handler (no SSO session)."""
        response = client.put("/api/user/prefs", json=self.VALID_PAYLOAD)
        assert response.status_code == 401
        assert "Login required" in response.json().get("error", "")

    def test_no_token_returns_401(self, token_enabled):
        """Returns 401 when BEARER_TOKEN is set but no Authorization header."""
        response = client.put("/api/user/prefs", json=self.VALID_PAYLOAD)
        assert response.status_code == 401

    def test_with_valid_token_still_401(self, token_enabled):
        """Returns 401 even with valid bearer token (no SSO session)."""
        response = client.put(
            "/api/user/prefs",
            json=self.VALID_PAYLOAD,
            headers={"Authorization": "Bearer testtoken123"},
        )
        assert response.status_code == 401
        assert "Login required" in response.json().get("error", "")

    def test_invalid_payload_validation(self, token_disabled):
        """Returns 401 (not validation error) because auth check runs first."""
        response = client.put("/api/user/prefs", json={"invalid_field": "value"})
        assert response.status_code == 401


# =============================================================================
# POST /api/user/prefs/reset — SSOOnly (no SSO → always 401 in tests)
# =============================================================================

class TestResetUserPrefs:

    def test_no_auth_public_mode(self, token_disabled):
        """Returns 401 from route handler (no SSO session)."""
        response = client.post("/api/user/prefs/reset")
        assert response.status_code == 401
        assert "Login required" in response.json().get("error", "")

    def test_no_token_returns_401(self, token_enabled):
        """Returns 401 when BEARER_TOKEN is set but no Authorization header."""
        response = client.post("/api/user/prefs/reset")
        assert response.status_code == 401

    def test_with_valid_token_still_401(self, token_enabled):
        """Returns 401 even with valid bearer token (no SSO session)."""
        response = client.post(
            "/api/user/prefs/reset",
            headers={"Authorization": "Bearer testtoken123"},
        )
        assert response.status_code == 401
        assert "Login required" in response.json().get("error", "")


# =============================================================================
# GET /api/admin/tokens — SSOOnly (_require_admin, no SSO → always 401)
# =============================================================================

class TestAdminListTokens:

    def test_no_auth_public_mode(self, token_disabled):
        """Returns 401 from route handler (no SSO session)."""
        response = client.get("/api/admin/tokens")
        assert response.status_code == 401
        assert "Login required" in response.json().get("detail", "")

    def test_no_token_returns_401(self, token_enabled):
        """Returns 401 when BEARER_TOKEN is set but no Authorization header."""
        response = client.get("/api/admin/tokens")
        assert response.status_code == 401

    def test_with_valid_token_still_401(self, token_enabled):
        """Returns 401 even with valid bearer token (no SSO session)."""
        response = client.get(
            "/api/admin/tokens",
            headers={"Authorization": "Bearer testtoken123"},
        )
        assert response.status_code == 401
        assert "Login required" in response.json().get("detail", "")


# =============================================================================
# POST /api/admin/tokens/{token_id}/revoke — SSOOnly
# =============================================================================

class TestAdminRevokeToken:

    def test_no_auth_public_mode(self, token_disabled):
        """Returns 401 from route handler (no SSO session)."""
        response = client.post("/api/admin/tokens/1/revoke")
        assert response.status_code == 401

    def test_no_token_returns_401(self, token_enabled):
        """Returns 401 when BEARER_TOKEN is set but no Authorization header."""
        response = client.post("/api/admin/tokens/1/revoke")
        assert response.status_code == 401

    def test_with_valid_token_still_401(self, token_enabled):
        """Returns 401 even with valid bearer token (no SSO session)."""
        response = client.post(
            "/api/admin/tokens/1/revoke",
            headers={"Authorization": "Bearer testtoken123"},
        )
        assert response.status_code == 401

    def test_non_existent_token(self, token_disabled):
        """Returns 401 (auth check runs before token lookup)."""
        response = client.post("/api/admin/tokens/99999/revoke")
        assert response.status_code == 401


# =============================================================================
# GET /api/admin/health — SSOOnly
# =============================================================================

class TestAdminHealth:

    def test_no_auth_public_mode(self, token_disabled):
        """Returns 401 from route handler (no SSO session)."""
        response = client.get("/api/admin/health")
        assert response.status_code == 401

    def test_no_token_returns_401(self, token_enabled):
        """Returns 401 when BEARER_TOKEN is set but no Authorization header."""
        response = client.get("/api/admin/health")
        assert response.status_code == 401

    def test_with_valid_token_still_401(self, token_enabled):
        """Returns 401 even with valid bearer token (no SSO session)."""
        response = client.get(
            "/api/admin/health",
            headers={"Authorization": "Bearer testtoken123"},
        )
        assert response.status_code == 401


# =============================================================================
# POST /api/admin/reindex — SSOOnly
# =============================================================================

class TestAdminReindex:

    def test_no_auth_public_mode(self, token_disabled):
        """Returns 401 from route handler (no SSO session)."""
        response = client.post("/api/admin/reindex")
        assert response.status_code == 401

    def test_no_token_returns_401(self, token_enabled):
        """Returns 401 when BEARER_TOKEN is set but no Authorization header."""
        response = client.post("/api/admin/reindex")
        assert response.status_code == 401

    def test_with_valid_token_still_401(self, token_enabled):
        """Returns 401 even with valid bearer token (no SSO session)."""
        response = client.post(
            "/api/admin/reindex",
            headers={"Authorization": "Bearer testtoken123"},
        )
        assert response.status_code == 401


# =============================================================================
# GET /api/admin/logs — SSOOnly
# =============================================================================

class TestAdminLogs:

    def test_no_auth_public_mode(self, token_disabled):
        """Returns 401 from route handler (no SSO session)."""
        response = client.get("/api/admin/logs")
        assert response.status_code == 401

    def test_no_token_returns_401(self, token_enabled):
        """Returns 401 when BEARER_TOKEN is set but no Authorization header."""
        response = client.get("/api/admin/logs")
        assert response.status_code == 401

    def test_with_valid_token_still_401(self, token_enabled):
        """Returns 401 even with valid bearer token (no SSO session)."""
        response = client.get(
            "/api/admin/logs?lines=20&level=INFO",
            headers={"Authorization": "Bearer testtoken123"},
        )
        assert response.status_code == 401


# =============================================================================
# GET /api/admin/users — SSOOnly
# =============================================================================

class TestAdminUsers:

    def test_no_auth_public_mode(self, token_disabled):
        """Returns 401 from route handler (no SSO session)."""
        response = client.get("/api/admin/users")
        assert response.status_code == 401

    def test_no_token_returns_401(self, token_enabled):
        """Returns 401 when BEARER_TOKEN is set but no Authorization header."""
        response = client.get("/api/admin/users")
        assert response.status_code == 401

    def test_with_valid_token_still_401(self, token_enabled):
        """Returns 401 even with valid bearer token (no SSO session)."""
        response = client.get(
            "/api/admin/users",
            headers={"Authorization": "Bearer testtoken123"},
        )
        assert response.status_code == 401


# =============================================================================
# POST /api/mcp-token — SSOOnly (_get_user, no SSO → always 401)
# =============================================================================

class TestCreateMcpToken:

    def test_no_auth_public_mode(self, token_disabled):
        """Returns 401 from route handler (no SSO session)."""
        response = client.post("/api/mcp-token", json={"name": "test-token"})
        assert response.status_code == 401
        assert "Login required" in response.json().get("error", "")

    def test_no_token_returns_401(self, token_enabled):
        """Returns 401 when BEARER_TOKEN is set but no Authorization header."""
        response = client.post("/api/mcp-token", json={"name": "test-token"})
        assert response.status_code == 401

    def test_with_valid_token_still_401(self, token_enabled):
        """Returns 401 even with valid bearer token (no SSO session)."""
        response = client.post(
            "/api/mcp-token",
            json={"name": "test-token"},
            headers={"Authorization": "Bearer testtoken123"},
        )
        assert response.status_code == 401
        assert "Login required" in response.json().get("error", "")

    def test_empty_name(self, token_disabled):
        """Returns 401 (auth check runs before field validation matters)."""
        response = client.post("/api/mcp-token", json={"name": ""})
        assert response.status_code == 401

    def test_missing_name_field(self, token_disabled):
        """Returns 401 (auth check runs first, then empty name is allowed)."""
        response = client.post("/api/mcp-token", json={})
        assert response.status_code == 401


# =============================================================================
# GET /api/mcp-tokens — SSOOnly (_get_user, no SSO → always 401)
# =============================================================================

class TestListMcpTokens:

    def test_no_auth_public_mode(self, token_disabled):
        """Returns 401 from route handler (no SSO session)."""
        response = client.get("/api/mcp-tokens")
        assert response.status_code == 401
        assert "Login required" in response.json().get("error", "")

    def test_no_token_returns_401(self, token_enabled):
        """Returns 401 when BEARER_TOKEN is set but no Authorization header."""
        response = client.get("/api/mcp-tokens")
        assert response.status_code == 401

    def test_with_valid_token_still_401(self, token_enabled):
        """Returns 401 even with valid bearer token (no SSO session)."""
        response = client.get(
            "/api/mcp-tokens",
            headers={"Authorization": "Bearer testtoken123"},
        )
        assert response.status_code == 401
        assert "Login required" in response.json().get("error", "")


# =============================================================================
# POST /api/mcp-tokens/{token_id}/revoke — SSOOnly
# =============================================================================

class TestRevokeMcpToken:

    def test_no_auth_public_mode(self, token_disabled):
        """Returns 401 from route handler (no SSO session)."""
        response = client.post("/api/mcp-tokens/test123/revoke")
        assert response.status_code == 401
        assert "Login required" in response.json().get("error", "")

    def test_no_token_returns_401(self, token_enabled):
        """Returns 401 when BEARER_TOKEN is set but no Authorization header."""
        response = client.post("/api/mcp-tokens/test123/revoke")
        assert response.status_code == 401

    def test_with_valid_token_still_401(self, token_enabled):
        """Returns 401 even with valid bearer token (no SSO session)."""
        response = client.post(
            "/api/mcp-tokens/test123/revoke",
            headers={"Authorization": "Bearer testtoken123"},
        )
        assert response.status_code == 401
        assert "Login required" in response.json().get("error", "")

    def test_non_existent_token_id(self, token_disabled):
        """Returns 401 (auth check runs before token lookup)."""
        response = client.post("/api/mcp-tokens/nonexistent/revoke")
        assert response.status_code == 401


# =============================================================================
# POST /api/mcp-tokens/{token_id}/rename — SSOOnly
# =============================================================================

class TestRenameMcpToken:

    def test_no_auth_public_mode(self, token_disabled):
        """Returns 401 from route handler (no SSO session)."""
        response = client.post(
            "/api/mcp-tokens/test123/rename",
            json={"name": "new-name"},
        )
        assert response.status_code == 401
        assert "Login required" in response.json().get("error", "")

    def test_no_token_returns_401(self, token_enabled):
        """Returns 401 when BEARER_TOKEN is set but no Authorization header."""
        response = client.post(
            "/api/mcp-tokens/test123/rename",
            json={"name": "new-name"},
        )
        assert response.status_code == 401

    def test_with_valid_token_still_401(self, token_enabled):
        """Returns 401 even with valid bearer token (no SSO session)."""
        response = client.post(
            "/api/mcp-tokens/test123/rename",
            json={"name": "new-name"},
            headers={"Authorization": "Bearer testtoken123"},
        )
        assert response.status_code == 401
        assert "Login required" in response.json().get("error", "")

    def test_missing_name_in_body(self, token_disabled):
        """Returns 422 when name field is missing (Pydantic validation runs before auth)."""
        response = client.post(
            "/api/mcp-tokens/test123/rename",
            json={},
        )
        assert response.status_code == 422  # Pydantic validation catches missing field first

    def test_empty_name(self, token_disabled):
        """Returns 401 (auth check runs before field validation)."""
        response = client.post(
            "/api/mcp-tokens/test123/rename",
            json={"name": ""},
        )
        assert response.status_code == 401


# =============================================================================
# GET /api/mcp-hall-of-fame — PublicRead (no auth check in route handler)
# =============================================================================

class TestMcpHallOfFame:

    def test_public_without_auth(self, token_disabled):
        """Hall of fame is accessible publicly."""
        response = client.get("/api/mcp-hall-of-fame")
        assert response.status_code == 200
        data = response.json()
        assert "all_time" in data
        assert "monthly" in data
        assert "weekly" in data
        assert "daily" in data

    def test_no_token_returns_401(self, token_enabled):
        """Returns 401 when BEARER_TOKEN is set but no Authorization header."""
        response = client.get("/api/mcp-hall-of-fame")
        assert response.status_code == 401

    def test_with_valid_token(self, token_enabled):
        """Returns 200 with valid bearer token."""
        response = client.get(
            "/api/mcp-hall-of-fame",
            headers={"Authorization": "Bearer testtoken123"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "all_time" in data

    def test_returns_leaderboard_structure(self, token_disabled):
        """Verify hall of fame data structure."""
        response = client.get("/api/mcp-hall-of-fame")
        assert response.status_code == 200
        data = response.json()
        for period in ("all_time", "monthly", "weekly", "daily"):
            assert isinstance(data[period], list)


# =============================================================================
# POST /api/comments — Edge case: empty text validation (SSO gate first)
# =============================================================================

class TestCreateCommentEdgeCases:

    def test_empty_json_body(self, token_disabled):
        """Returns 422 for empty JSON object (missing required fields)."""
        response = client.post("/api/comments", json={})
        assert response.status_code == 422

    def test_missing_act_field(self, token_disabled):
        """Returns 422 when act field is missing."""
        response = client.post(
            "/api/comments", json={"section": "6-5", "text": "test"}
        )
        assert response.status_code == 422

    def test_missing_section_field(self, token_disabled):
        """Returns 422 when section field is missing."""
        response = client.post(
            "/api/comments", json={"act": "itaa-1997", "text": "test"}
        )
        assert response.status_code == 422


# =============================================================================
# Exempt paths — verify middleware does NOT enforce auth on these
# =============================================================================

class TestExemptPaths:

    def test_health_endpoint(self, token_enabled):
        """Health endpoint is exempt from auth."""
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

    def test_info_endpoint(self, token_enabled):
        """Info endpoint is exempt from auth."""
        # Note: /api/info is NOT in exempt list, so it requires auth
        response = client.get("/api/info")
        assert response.status_code == 401

        response = client.get(
            "/api/info",
            headers={"Authorization": "Bearer testtoken123"},
        )
        assert response.status_code == 200
        assert "version" in response.json()

    def test_api_info_without_auth_public_mode(self, token_disabled):
        """Info endpoint is accessible in public mode."""
        response = client.get("/api/info")
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Legislation Explorer"
        assert "version" in data
        assert "endpoints" in data


# =============================================================================
# Auth header edge cases
# =============================================================================

class TestAuthHeaderEdgeCases:

    def test_empty_authorization_header(self, token_enabled):
        """Empty Authorization header should fail."""
        response = client.get(
            "/api/issues",
            headers={"Authorization": ""},
        )
        assert response.status_code == 401

    def test_bearer_token_missing_value(self, token_enabled):
        """'Bearer ' with no actual token should fail."""
        response = client.get(
            "/api/issues",
            headers={"Authorization": "Bearer "},
        )
        assert response.status_code == 401

    def test_basic_auth_scheme(self, token_enabled):
        """Basic auth scheme should not be accepted."""
        import base64
        creds = base64.b64encode(b"user:testtoken123").decode()
        response = client.get(
            "/api/issues",
            headers={"Authorization": f"Basic {creds}"},
        )
        assert response.status_code == 401

    def test_case_sensitive_scheme(self, token_enabled):
        """Bearer must be capitalized."""
        response = client.get(
            "/api/issues",
            headers={"Authorization": "bearer testtoken123"},
        )
        assert response.status_code == 401


# =============================================================================
# Cross-endpoint auth consistency
# =============================================================================

class TestAuthConsistency:

    @pytest.fixture(autouse=True)
    def _no_live_db_writes(self, monkeypatch):
        """Keep auth-contract tests from writing real tickets to the live DB.

        This class POSTs /api/issues as part of endpoint sweep — stub the
        route's DB helpers so no INSERT reaches cadena_knowledge.issues.
        """
        import backend.routes.issues as issues_route

        def fake_dict(columns, query):
            if "MAX(id)" in query:
                return [{"next_id": 900000}]
            return []

        monkeypatch.setattr(issues_route, "_sql_write", lambda sql: True)
        monkeypatch.setattr(issues_route, "_sql_dict", fake_dict)

    def test_all_public_read_endpoints_with_auth(self, token_enabled):
        """Verify all PublicRead endpoints work with valid bearer token."""
        headers = {"Authorization": "Bearer testtoken123"}
        endpoints = [
            ("GET", "/api/comments/itaa-1997/6-5"),
            ("GET", "/api/issues"),
        ]
        for method, path in endpoints:
            response = client.get(path, headers=headers)
            assert response.status_code == 200, f"{method} {path} returned {response.status_code}"

    def test_all_sso_endpoints_with_auth(self, token_enabled):
        """Verify all SSO-only endpoints return 401 with bearer token (no SSO session)."""
        headers = {"Authorization": "Bearer testtoken123"}
        endpoints = [
            ("GET", "/api/user/prefs"),
            ("PUT", "/api/user/prefs", {"theme": "light"}),
            ("POST", "/api/user/prefs/reset"),
            ("GET", "/api/admin/tokens"),
            ("GET", "/api/admin/health"),
            ("POST", "/api/admin/reindex"),
            ("GET", "/api/admin/logs"),
            ("GET", "/api/admin/users"),
            ("POST", "/api/mcp-token", {"name": "test"}),
            ("GET", "/api/mcp-tokens"),
        ]
        for endpoint in endpoints:
            method = endpoint[0]
            path = endpoint[1]
            body = endpoint[2] if len(endpoint) > 2 else None
            if method == "GET":
                response = client.get(path, headers=headers)
            elif method == "PUT":
                response = client.put(path, json=body, headers=headers)
            else:
                response = client.post(path, json=body if body else {}, headers=headers)
            assert response.status_code == 401, f"{method} {path} returned {response.status_code} (expected 401)"

    def test_all_endpoints_without_auth(self, token_enabled):
        """Verify ALL endpoints return 401 without auth header when BEARER_TOKEN is set."""
        endpoints = [
            ("GET", "/api/comments/itaa-1997/6-5"),
            ("GET", "/api/issues"),
            ("GET", "/api/user/prefs"),
            ("GET", "/api/admin/tokens"),
            ("GET", "/api/admin/health"),
            ("POST", "/api/admin/reindex"),
            ("GET", "/api/admin/logs"),
            ("GET", "/api/admin/users"),
            ("POST", "/api/mcp-token"),
            ("GET", "/api/mcp-tokens"),
        ]
        for method, path in endpoints:
            if method == "POST":
                response = client.post(path, json={})
            else:
                response = client.get(path)
            assert response.status_code == 401, f"{method} {path} returned {response.status_code} (expected 401)"

    def test_all_public_endpoints_in_public_mode(self, token_disabled):
        """Verify PublicRead endpoints work without any auth in public mode."""
        endpoints = [
            ("GET", "/api/comments/itaa-1997/6-5"),
            ("GET", "/api/issues"),
            ("POST", "/api/issues", {"category": "bug", "note": "Consistency test"}),
        ]
        for ep in endpoints:
            method = ep[0]
            path = ep[1]
            params = ep[2] if len(ep) > 2 else None
            if method == "GET":
                response = client.get(path)
            else:
                response = client.post(path, json=params if isinstance(params, dict) else {})
            assert response.status_code == 200, f"{method} {path} returned {response.status_code} (expected 200)"