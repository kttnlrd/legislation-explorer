"""API route assembly."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter

from .acts import router as acts_router
from .definitions import router as definitions_router
from .search import router as search_router
from .cases import router as cases_router
from .rulings import router as rulings_router
from .commentary import router as commentary_router
from .comments import router as comments_router
from .tax_cases import router as tax_cases_router
from .user_prefs import router as user_prefs_router
from .admin import router as admin_router
from .data_versions import router as data_versions_router

from .graph import router as graph_router
from .issues import router as issues_router
from .insolvency import router as insolvency_router
from .regulatory_guides import router as regulatory_guides_router
from .treaties import router as treaties_router

router = APIRouter()
router.include_router(acts_router)
router.include_router(definitions_router)
router.include_router(search_router)
router.include_router(cases_router)
router.include_router(rulings_router)
router.include_router(commentary_router)
router.include_router(comments_router)
router.include_router(tax_cases_router)
router.include_router(user_prefs_router)
router.include_router(admin_router)
router.include_router(data_versions_router)
router.include_router(graph_router)
router.include_router(issues_router)
router.include_router(insolvency_router)
router.include_router(regulatory_guides_router)
router.include_router(treaties_router)


VERSION = "2.8.0"

CHANGELOG = [
    {
        "version": "2.8.0",
        "date": "2026-08-14",
        "title": "Tax Treaties, Regulatory Guides, Social Composer, Knowledge Graph",
        "changes": [
            "New features:",
            "|– 42 treaty countries ingested with per-article markdown files + FTS5 search",
            "|– REST API: /api/treaties, /api/treaties/{country}, /api/treaties/{country}/article/{article}, /api/treaties/search",
            "|– MCP tools: list_treaty_articles(country) and get_treaty_article(country, article)",
            "|– Tax Treaties moved to single entry under new International Tax heading in act picker",
            "|– Regulatory Guides: full integration with backend API, MCP tools (get_regulatory_guide, get_rg_sections), frontend component with structured summary panel and PDF download, Corps Act section cross-referencing",
            "|– Social Post Composer: backend for generating drafts via OpenRouter and posting to Buffer",
            "|– Knowledge Graph: case edges from section_case_index, permanent labels on all nodes, tree layout as default",
            "|– FTS5 case search over summaries (BM25-ranked, Porter tokenizer)",
            "|– Ruling search: exact-match pinning, LIKE fallback for FTS5 misses, citation display formatting (TR_2012_1 → TR 2012/1)",
            "|– PostgreSQL connection pooling with auto-reconnect fallback",
            "|– Expanded ruling type coverage (ATOID, CR, PR, GSTR, MT, TA, SGR, AID) with URL generation",
            "|– Cross-act definition fallback: big-def sections (s 995-1, s 318, s 6, s 195-1) truncated with get_definition redirect",
            "|– Rate limit relaxation: MCP SSE 10→60, messages 30→120, auth 20→60, global RPM 1000→3000",
            "|– Act picker domain-grouped with settings panel optgroups",
            "",
            "Bugs fixed:",
            "|– CDN-0094: scraped markup stripped before processor injects anchors — prevents HTML artifact bleed",
            "|– CDN-0095: centralised scraped-markup stripper (text_cleaner.py) applied to section, ruling, and case endpoints",
            "|– CDN-0097: insolvency-keays frontmatter fixed, YAML frontmatter stripped from API responses",
            "|– resolve_alias false positives: section existence validated against tree before returning results",
            "|– Bracketless case citations normalized (2024 HCA 18 → [2024] HCA 18)",
            "|– Stale tree state race condition fixed with generation ref counter",
            "|– Hall of Fame UI removed (dead code, deprecated API)",
            "|– Search result snippets truncated to 150 chars instead of unbounded",
            "|– Case search now included in search_sections path",
            "|– Ruling FTS index falls back to summaries for real titles",
            "|– Unicode definition term keys normalised (curly quotes → ASCII apostrophes)",
        ],
    },
    {
        "version": "2.7.5",
        "date": "2026-08-02",
        "title": "Cross-act definition lookup",
        "changes": [
            "get_definition now searches all acts, not just the requested one — terms like 'arm's length' (not in any dictionary section) and 'associate' (ITAA 1936 s 318) fall back to other acts' indexes",
            "Cross-act results include `also_defined_in` listing matches from other acts with act, section, text, and path",
            "load_definitions falls back to definitions.json when definitions_all.json is absent",
            "Disabled stale cadena-knowledge.service (directory removed, MCP runs inside legislation-explorer)",
            "Version bumped to 2.7.5",
        ],
    },
    {
        "version": "2.7.4",
        "date": "2026-08-02",
        "title": "UI cleanup, user prefs persistence fix",
        "changes": [
            "Fixed user preference persistence — text_color and bg_color were silently dropped by the server (missing DB columns). Reset to defaults now actually writes defaults.",
            "Removed redundant Report a Bug button in sidebar (Bugs modal already has report form).",
            "Cleaned up sidebar button formatting — removed flexWrap/center that caused cramped layout.",
            "Filter tabs (All, Sections, Rulings, Cases, Commentary) now auto-trigger search on click — no need to press Search again.",
            "Removed autocomplete dropdown — search button goes straight to full paginated results.",
            "Removed color coding of open vs. known issues in IssuesModal (resolved section split is sufficient).",
            "Cleaned up 24 test/placeholder tickets from the issues database. Updated notes to remove B-notation.",
            "Version bumped to 2.7.4",
        ],
    },
    {
        "version": "2.7.2",
        "date": "2026-08-01",
        "title": "Definition popover overflow fix, collapsible Related panel, no-404 defined terms",
        "changes": [
            "Definition popover now wraps long text and scrolls — overflow-wrap, word-break, max-height with scrollbar for definitions like 'consolidated group'",
            "Related panel rewritten with collapsible dropdowns (default closed), max 10 items per category",
            "References section removed from SectionContent — merged into Related panel to eliminate duplication",
            "Defined terms now use italic-only matching (regex \\*...\\*) instead of substring match — prevents every common word from appearing as a defined term",
            "Clicking defined terms no longer 404s — link text asterisks stripped in both backend markdown formatter and frontend DefinitionPopover safety net",
            "App.tsx cleaned up — removed stale open/close state for commentary/cases/rulings",
            "Version bumped to 2.7.2",
        ],
    },
    {
        "version": "2.7.0",
        "date": "2026-08-05",
        "title": "Unified search, related content on every section, graph visualisation, section quality & test suite",
        "changes": [
            "New MCP tool: search_all — unified search across sections, cases, rulings, and commentary with type_filter and act scoping. Replaces separate per-type tools including get_rulings_for_section (retired)",
            "get_section now returns related content: top 10 cases, rulings, commentary, and cross-referenced sections alongside every section lookup",
            "Smart fallback search: when a section, case, or ruling isn't found by identifier, automatically suggests alternatives via FTS search with 'did you mean' results",
            "Cross-similarity index: embedding-based similarity linking every section to relevant cases and rulings — powered by build_cross_similarity.py against the embeddings database",
            "Court mapping fixed across all courts — AATA, ARTA, FCAFC, FCA, HCA correctly identified for all 5,368+ tax cases (verified: 0 unknown-court errors across 4,000+ endpoint calls)",
            "Section content quality: 887+ markdown files normalized (heading structure, paragraph breaks, inline bullets). 51 sections with missing headings or empty bodies fixed",
            "Tree.json data integrity: 116 sections in ITAA 1997 and ITAA 1936 had incorrect 'sections/' prefix paths — stripped, restoring proper rendering",
            "Hybrid search pagination: offset parameter working correctly for deep result browsing",
            "358 automated tests (259 API contract + 34 integration + 65 vector quality) — all passing against live dev deployment",
            "MCP get_case and get_ruling enhanced with FTS fallback search on identifier miss",
            "Version bumped to 2.7.0",
        ],
    },
    {
        "version": "2.6.0",
        "date": "2026-07-31",
        "title": "MCP overhaul: OAuth + Streamable HTTP, case retrieval rework, summarised cases & rulings, toolchain",
        "changes": [
            "MCP transport: SSE → Streamable HTTP (single endpoint). OAuth 2.1 authorization server maintained for future builds — /.well-known/oauth-authorization-server, /oauth/authorize, /oauth/token, /oauth/register",
            "MCP toolchain: get_info returns routing table (which tool for what task), tool descriptions, and usage conventions. standards tool covers verification, matter-structure, premises, memory, and toolchain topics",
            "Case retrieval rework: paragraph layer deleted (miscoded section_type, wrong paragraph_number). get_case gains search= and context= for full-text matching over the judgment body with sentence-windowed context. Structured sources with honest fetchable flags (text=true, court=conditional, austlii=false, browser=false). case_link and download_case tools retired — 3 tools folded into 1",
            "All cases summarised and added to database — 4,895 tax cases from HCA, FCA, FCAFC, AATA with AI-generated summaries and full citation metadata",
            "All rulings summarised and added to database — 11,339 ATO rulings (TR, TD, ATO ID, SIC, etc.) with AI-generated summaries",
            "New MCP tooling: get_info (routing table + tool descriptions + usage conventions), standards (verification, matter-structure, premises, memory, toolchain), report_issue (parameterised bug submission), search (FTS5 across all content), get_case enhanced with search=/context= and structured sources",
            "Issues portal — Bugs button lists open/known/resolved issues from the DB. Manual bug report form. Resolved issues expandable at bottom",
            "Full-text search via FTS5 across all 11,339 ATO rulings — full-page results with snippet highlights, source filter, pagination",
            "Ruling display redesign — subject, question, background, and ruling text shown inline (no collapsible dropdown)",
            "Definition extraction improved — expanded pattern matching for s 995-1 defined terms",
            "Security: report_issue and all issue writes moved to parameterised queries — no SQL string interpolation of user input",
            "Ruling tree click routing fixed — sidebar rulings navigate to proper detail view, not 404",
            "Automatic daily bug-fix cron — queries reported issues, fixes top 3 by hit count via parallel subagents",
            "Version bumped to 2.6.0",
        ],
    },
    {
        "version": "2.5.0",
        "date": "2026-07-29",
        "title": "Rulings sidebar + dedicated pages, court-grouped cases, hyperlinked cross-references",
        "changes": [
            "Rulings sidebar tree (act='rulings') — browse by year → type, click to open full text",
            "Dedicated /rulings/{citation} pages for all 7,310 ATO rulings — full text + referenced sections",
            "Fixed URL routing for ruling citations with slashes (TR 2025/1, PS LA 2011/10)",
            "Cases on section pages now grouped by court: High Court, Full Federal Court, Federal Court, AAT",
            "Legislation references in case detail pages are hyperlinked — click to navigate to the section",
            "Case citations on section pages are hyperlinked — click to open the tax case page",
            "Version bumped to 2.5.0",
        ],
    },
    {
        "version": "2.4.0",
        "date": "2026-07-27",
        "title": "Search includes rulings, pagination, full-page results, related content panel, tree view",
        "changes": [
            "Flat search now includes 6,618 ATO rulings alongside legislation sections — FTS5 rulings_fts virtual table indexed from ruling text files",
            "Search results paginated at 25 per page with page number buttons and Previous/Next navigation",
            "Full-page search results layout — results flow naturally below search bar, homepage expands to full width, welcome footer hidden while searching",
            "Source filter now re-applies to existing results — selecting/deselecting acts in the filter immediately narrows results",
            "Display fixes: no more 's' prefix on CCH guide sections, left-aligned snippets with FTS5 highlights, long titles wrap instead of truncating",
            "Drawer icon (three-line SVG) at top-left of main pane on mobile — opens sidebar, separate from search bar",
            "Definitions are clickable — tapping a defined term navigates to the defining section with anchor",
            "Commentary, Cases, and Rulings sections consolidated into unified 'Related' panel with subsections: Sections, Rulings, Defined Terms, Cases (placeholder), Commentary (placeholder)",
            "Rulings in Related panel display proper display names (TR 2023/2) not raw citations (TR_2023_2)",
            "Tree view in main content pane when browsing an act — all parts expanded, select a section to open content",
            "Auto-build search index on flat search request when index is missing",
        ],
    },
    {
        "version": "2.3.1",
        "date": "2026-07-25",
        "title": "ATO rulings URLs fixed, IT rulings indexed, MCP tools enhanced",
        "changes": [
            "ATO ruling URLs switched from dead /law/view/pdf/ and URL-encoded DocID to working plain-slash DocID + &PiT=99991231235958 format",
            "233 IT rulings (IT 1→363) extracted from Postgres and added to the rulings tree",
            "PS LA citation parsing fixed — citations like PS_LA_2011_10 now display and link correctly",
            "New MCP tool: list_rulings — returns all 388 rulings grouped by year/type with ATO.gov.au and AustLII links",
            "MCP get_ruling now includes ato_url, austlii_url, and citation_display fields",
            "MCP get_rulings_for_section passes through enriched data including ATO URLs",
        ],
    },
    {
        "version": "2.3.0",
        "date": "2026-07-25",
        "title": "Microsoft SSO, public content, Cadena IP gating",
        "changes": [
            "Microsoft Entra ID SSO — sign in with @cadenalegal.com.au account",
            "All existing content (legislation, rulings, cases, search) is now public — no login required",
            "Cadena IP content (precedents, strategies, research) gated behind login",
            "Auth middleware restructured: only /api/cadena/* and /mcp/cadena/* require authentication",
        ],
    },
    {
        "version": "2.2.0",
        "date": "2026-07-25",
        "title": "Case MCP tools, enriched case detail, shareable URLs, head_notes fix",
        "changes": [
            "New MCP tool: get_case — case metadata with section-type outline (no paragraph text)",
            "New MCP tool: get_case_paragraphs — paragraph content filtered by section type, paginated, capped at 100/50K chars",
            "New MCP tool: search_case_paragraphs — FTS across 7,377 cases, optional citation scope",
            "New MCP tool: download_case — AustLII download URLs for offline research",
            "Case detail view in UI enriched with judges, outcome, paragraph count, file size, linked legislation",
            "Share button in sidebar — copies current page URL to clipboard (supports sections, rulings, tax cases)",
            "Direct URL loading for tax cases — e.g. /tax-cases/%5B2026%5D%20FCAFC%2010 navigates straight to the case",
            "Bug fix: head_notes incorrectly parsed as flat array instead of JSON object — _infer_type now checks JSON before PG array literal",
            "Bug fix: case endpoint now falls back to Postgres DB for cases not in flat JSON files",
            "Bug fix: DB-only cases now extract catchwords from head_notes JSON",
        ],
    },
    {
        "version": "2.1.2",
        "date": "2026-07-25",
        "title": "ATO rulings: year fix, LCR→LCG alias, full titles, PDF extraction, MCP enrichment; get_definition fixes & GST metadata",
        "changes": [
            "Bug fix: get_rulings_for_section no longer returns year=0 — year extracted from filename regex fallback in citation_index builder",
            "Bug fix: get_ruling now normalises LCR → LCG citation alias (ATO publishes as LCR, files stored as LCG)",
            "Bug fix: get_definition no longer requires definitions at column 0 — uses (?<!\\w) lookbehind to match inline text, so ITAA 1936 'dividend' (s 6(1)) and GST 'enterprise' (s 195-1) now resolve correctly",
            "Bug fix: GST compilation metadata updated — all 824 section files from compilation 96 (2026-01-01) to compilation 228 (2026-04-01) to match tree.json",
            "load_rulings now extracts descriptive full_title from ruling text content (e.g. 'Income tax: whether penalty interest is deductible')",
            "21 ATO ruling PDFs (1 TD + 20 TR) extracted to text and indexed in citation_index via pipeline/extract_ato_ruling_pdfs.py",
            "MCP get_rulings_for_section enriched with load_rulings() data (proper year, full_title)",
            "MCP get_ruling returns full_title field, supports LCR→LCG alias",
            "Rulings list in sidebar shows citation + full descriptive title",
            "Section view ruling links display proper citation (TR 2019/2) not internal filename (TR_2019_2)",
        ],
    },
    {
        "version": "2.1.1",
        "date": "2026-07-24",
        "title": "get_definition now returns definition text, not just a pointer",
        "changes": [
            "get_definition now resolves the anchor server-side and returns the full definition text (body, anchor, section)",
            "Removed load_definitions import — get_definition_text does complete lookup internally",
        ],
    },
    {
        "version": "2.1.0",
        "date": "2026-07-24",
        "title": "Simplified MCP tools, year fix, citation normalization & get_info tool",
        "changes": [
            "MCP tools simplified: removed get_case and get_cases_for_section — all case lookup via search_cases",
            "get_ruling now accepts TR 2020/1, TR_2020_1, or TR 2024/1 (mixed spacing/slash formats)",
            "Ruling year field fixed — was always 0, now correctly parsed from citation for all ruling types",
            "New get_info MCP tool — returns version, changelog, and tool list (no args)",
            "get_rulings_for_section tool description updated",
        ],
    },
    {
        "version": "2.0.0",
        "date": "2026-07-24",
        "title": "Tax Cases, CCH Titles, Hall of Fame & Code-splitting",
        "changes": [
            "6,701 tax cases across HCA, FCA, FCAFC, and AAT (ARTA) — searchable and browsable",
            "Cases appear as collapsible tree in sidebar: Court → Year → Case",
            "Unified search bar in main pane — searches all acts, CCH guides, rulings, and cases simultaneously",
            "CCH Master Tax Guide and Master Tax Examples — backfilled 45 chapter titles and section titles",
            "TAA Schedule 1 renamed from 'Part UNKNOWN' — all 74 divisions now visible and expandable",
            "MCP Hall of Fame — named tokens, call logging, daily/weekly/monthly/all-time leaderboard",
            "Scrolling Hall of Fame banner at top of page with dismiss + modal popup",
            "Frontend code-split: bundle reduced from 507 KB to 170 KB (11 lazy-loaded chunks)",
            "MCP token creation requires name input",
            "MCP case tools simplified: removed get_case and get_cases_for_section — all case lookup via search_cases (name + catchwords → weblink)",
            "Monthly automated sync: scrapes AustLII, ingests into SQL + JSON, restarts server",
            "Concurrent scraping (5x parallel) for faster monthly updates",
            "2026 cases: 163 tax cases across all courts",
        ],
    },
    {
        "version": "1.0.0",
        "date": "2026-05-17",
        "title": "Initial Release",
        "changes": [
            "Legislation browser with ITAA 1997, ITAA 1936, GST Act, TAA 1953, and more",
            "Full-text search across acts and rulings",
            "ATO rulings database (TR, TD, PCG, PS LA)",
            "MCP integration for Claude Desktop",
            "Pinned tabs, comments, keyboard shortcuts",
        ],
    },
]


@router.get("/api/info")
def api_info():
    """Return version, changelog, and available endpoints."""
    return {
        "name": "Legislation Explorer",
        "version": VERSION,
        "changelog": CHANGELOG,
        "docs_url": "/docs",
        "endpoints": {
            "legislation": {
                "GET /api/acts": "List all available acts and rulings",
                "GET /api/tree/{act}": "Get the full structure of an act",
                "GET /api/section/{act}/{section}": "Retrieve full text of a section",
                "GET /api/search": "Search sections by keyword or number",
                "GET /api/definitions/{act}": "Look up definitions in an act",
            },
            "rulings": {
                "GET /api/rulings": "List all ATO rulings",
                "GET /api/ruling/{citation}": "Retrieve a ruling by citation",
                "GET /api/rulings-for-section/{act}/{section}": "Get rulings related to a section",
            },
            "regulatory_guides": {
                "GET /api/regulatory-guides": "List all ASIC Regulatory Guides",
                "GET /api/regulatory-guide/{rg_number}": "Retrieve a regulatory guide by number",
                "GET /api/regulatory-guide/{rg_number}/download": "Download PDF of a regulatory guide",
                "GET /api/regulatory-guides/search": "Search regulatory guides by keyword",
            },
            "tax_cases": {
                "GET /api/tax-cases/search": "Search tax cases by name, citation, or catchwords",
                "GET /api/tax-cases": "List available tax case sources (deprecated)",
                "GET /api/tax-cases/{court}": "Get cases for a court grouped by year (deprecated)",
                "GET /api/section-tax-cases/{act}/{section}": "Cases referencing a section (deprecated)",
            },
            "mcp": {
                "GET /mcp/sse": "SSE endpoint for MCP (requires token)",
                "POST /api/mcp-token": "Create an MCP access token",
                "GET /api/mcp-tokens": "List active MCP tokens",
                "POST /api/mcp-tokens/{token}/revoke": "Revoke an MCP token",
            },
            "system": {
                "GET /api/info": "This endpoint — version and documentation",
                "GET /health": "Health check",
                "GET /docs": "OpenAPI documentation (Swagger UI)",
            },
        },
    }
