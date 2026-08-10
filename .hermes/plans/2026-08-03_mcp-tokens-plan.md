# MCP Token Separation Plan — Tax / Corps / AML

## Goal

Split the monolithic legislation-explorer MCP into 3 domain-scoped endpoints, each with its own auth token and FTS5 index, so that:
- Corps Act search results don't pollute tax search rankings
- AML/CTF data is isolated from both
- Each domain can have different access tokens

## Architecture

Three FastMCP sub-apps, all mounted on the same FastAPI app with different path prefixes:

```
/mcp/tax/messages     — Tax domain (itaa-1997, itaa-1936, gst-1999, taa-1953, rulings, cases, commentary)
/mcp/corps/messages   — Corps domain (corporations-act-2001, ASIC RGs)
/mcp/aml/messages     — AML/CTF domain (aml-ctf-2006, aml-ctf-rules)
```

Each sub-app:
- Has its own BEARER_TOKEN env var (tax_token, corps_token, aml_token)
- Registers only its own domain-scoped tools (e.g. `tax_get_section`, `corps_get_section`, `aml_get_section`)
- Targets its own FTS5 index table (sections_fts_tax, sections_fts_corps, sections_fts_aml)

The existing `/mcp/messages` endpoint continues to serve all domains (backward compat).

## Files to Create/Modify

### 1. `backend/fastmcp_server.py` — Add 3 domain MCP apps

Create three FastMCP instances alongside the existing monolithic one:

```python
mcp_tax = FastMCP("legislation-explorer-tax", ...)
mcp_corps = FastMCP("legislation-explorer-corps", ...)
mcp_aml = FastMCP("legislation-explorer-aml", ...)
```

Each registers only its domain-scoped tools. Use shared helper functions from services/ but register different tool names.

### 2. `backend/config.py` — Add domain tokens

```python
TAX_BEARER_TOKEN = os.environ.get("TAX_BEARER_TOKEN")
CORPS_BEARER_TOKEN = os.environ.get("CORPS_BEARER_TOKEN")
AML_BEARER_TOKEN = os.environ.get("AML_BEARER_TOKEN")
```

### 3. `backend/services/search_service.py` — Domain-scoped FTS5

Add per-domain FTS5 tables:
- `sections_fts_tax`, `sections_meta_tax`
- `sections_fts_corps`, `sections_meta_corps`  
- `sections_fts_aml`, `sections_meta_aml`

Modify `init_search_index()` to build all 3. Add `search_sections_by_domain(domain, q, act, limit)`.

### 4. `backend/main.py` — Mount domain MCPs

```python
mcp_tax_app = mcp_tax.streamable_http_app()
mcp_corps_app = mcp_corps.streamable_http_app()
mcp_aml_app = mcp_aml.streamable_http_app()

# Add auth middleware per domain
app.mount("/mcp/tax", auth_middleware(mcp_tax_app, TAX_BEARER_TOKEN))
app.mount("/mcp/corps", auth_middleware(mcp_corps_app, CORPS_BEARER_TOKEN))
app.mount("/mcp/aml", auth_middleware(mcp_aml_app, AML_BEARER_TOKEN))
```

### 5. `.env` — Add 3 token env vars

```
TAX_BEARER_TOKEN=tax-xxx
CORPS_BEARER_TOKEN=corps-xxx
AML_BEARER_TOKEN=aml-xxx
```

Update systemd service to load all three.

## Tool Scoping

Each domain MCP registers only its relevant tools:

| Tool | Tax | Corps | AML |
|------|-----|-------|-----|
| get_section | ✓ (tax acts) | ✓ (corps act) | ✓ (aml act) |
| get_act_tree | ✓ (tax) | ✓ (corps) | ✓ (aml) |
| get_definition | ✓ (tax defs) | ✓ (corps defs) | ✓ (aml defs) |
| search_sections | ✓ (tax FTS5) | ✓ (corps FTS5) | ✓ (aml FTS5) |
| search_all | ✓ (tax scoped) | ✓ (corps scoped) | ✓ (aml scoped) |
| get_case | ✓ | ✗ | ✗ |
| get_ruling | ✓ | ✗ | ✗ |
| list_acts | ✓ (tax) | ✓ (corps) | ✓ (aml) |
| get_commentary | ✓ | ✗ | ✗ |

## FTS5 Index Strategy

Three separate tables in the same `search.db`:
- `sections_fts_tax` — itaa-1997, itaa-1936, gst-1999, taa-1953
- `sections_fts_corps` — corporations-act-2001, (future: ASIC RGs as sections)
- `sections_fts_aml` — aml-ctf-2006, aml-ctf-rules

All built in `init_search_index()` in a single pass. No schema change needed — same table structure, just different names.

## Implementation Order

1. **Add domain FTS5 tables** to search_service.py (non-breaking, existing code still works)
2. **Add domain-scoped search functions** (same file, new functions)
3. **Create domain MCP apps** in fastmcp_server.py (register subset of tools)
4. **Add config vars** for domain tokens
5. **Mount in main.py** with auth middleware
6. **Update .env and systemd** service
7. **Test** each endpoint with curl
8. **Rebuild** FTS5 index, restart server

## Backward Compatibility

The existing monolithic MCP at `/mcp/messages` continues to work with the existing BEARER_TOKEN until all clients migrate. The `sections_fts` table (without domain suffix) is preserved for the monolithic endpoint.

## Effort Estimate

- FTS5 changes: 30 min
- Domain MCP apps: 1 hr
- Auth middleware: 15 min
- Config + env: 15 min
- Testing: 30 min
- **Total: ~2.5 hrs**