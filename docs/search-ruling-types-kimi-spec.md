# Search: ruling-type filters + grouped sources — Kimi implementation spec

Repo: `/home/harrison/legislation-explorer` (branch already created: `feature/search-ruling-types-and-source-groups`)
Stack: FastAPI backend (`backend/`), React+Vite frontend (`frontend/`). Service: `systemctl --user legislation-explorer.service`, health `http://localhost:8765/health`.

## User request (Harry Dell, verbatim)

"it catagorises rulings and private rulings under the same catagory in the search. Also need the capability to sear TR, TD, ATOID etc types of rulings seperately. Sources can be laid out better, as a list under Australian tax, NZ tax, Corps Law etc."

Three deliverables:
1. **Public rulings and private rulings must be separate categories** in search (currently they mix).
2. **Ruling-series filter**: search TR, TD, ATOID/AID, PS LA, GSTR, PCG, CR, IT, TA etc. separately.
3. **Sources filter grouped by jurisdiction**: Australian Tax / NZ Tax / Corporate Law / etc., not a flat list.

## Background facts (verified)

- Hybrid search endpoint: `GET /api/search/hybrid` in `backend/routes/search.py` (fn `search_hybrid` ~line 440). Params: `q, act, limit, type, offset, operator, date_from, date_to`. `type` is comma-separated source_type set: `section, ruling, commentary, case, private_ruling`.
- **BUG 1 (mixing)**: private ruling embeddings are stored in `data/embeddings.db` with `source_type='ruling'`, `act='private'` (see `scripts/embed_private_rulings.py` insert). But `backend/services/vector_search_service.py` `search()` maps any `source_type=='ruling'` to `act='rulings'`, losing the private/public distinction. So vector hits for private rulings come back as `source_type='ruling', act='rulings'` — indistinguishable from public rulings.
- **BUG 2 (type filter)**: in `search_hybrid`, line ~500: `if type_filter and not (type_filter & {"ruling", "private_ruling"}): private_results = []` — selecting `type=ruling` KEEPS private results (intersection non-empty). Should exclude private unless `private_ruling` explicitly selected.
- Ruling series prefixes present in DB (public rulings, `source_type='ruling', act='ato'`): AID 5931, CR 2480, PR 1051, TD 801, PS 255, TR 241, IT 233, TA 151, GSTR 128, PCG 71, LCG 37, MT 16, SGR 4. Sections look like `TR 2005/23`, `PS LA 2004 3`, `TD 2020/7` (note: PS LA has a space after LA). Private ruling sections are 13-digit authnums like `1012705415641`.
- SearchPanel UI: `frontend/src/components/SearchPanel.tsx` (632 lines). Type tabs hardcoded ~line 462: `All / Sections / Rulings / Cases / Commentary`. `typeFilter` state string; passed to `api.searchHybrid(term, activeFilter, 200, {...})`.
- `frontend/src/api.ts` `searchHybrid(q, type?, limit?, opts?)` — needs an `rtype` param added.
- **DOMAINS grouping already exists** in `frontend/src/App.tsx` (top of file, ~line 44):
  ```ts
  const DOMAINS: { label: string; ids: string[] }[] = [
    { label: 'Australian Tax', ids: ['itaa-1997','itaa-1936','gst-1999','taa-1953','fbt-1986','sis-1993','master-tax-guide','master-tax-examples','master-gst-guide','rulings','tax-cases'] },
    { label: 'Private Rulings', ids: ['private-rulings'] },
    { label: 'International Tax', ids: ['treaties'] },
    { label: 'New Zealand Tax', ids: ['nz-it-2007'] },
    { label: 'Corporate Law', ids: ['corporations-act-2001','regulatory-guides'] },
    { label: 'Corporate Insolvency', ids: ['insolvency-keays'] },
    { label: 'AML/CTF', ids: ['aml-ctf-2006','aml-ctf-rules-2007'] },
    { label: 'System', ids: ['spec'] },
  ]
  ```
  It is NOT exported. `acts` prop passed to SearchPanel is the flat list from `/api/acts` (20 items, same ids as DOMAINS ids + treaties children not in list). `shortActName` in `frontend/src/utils/display.ts` maps act id → short label.
- SearchPanel receives `acts={acts}` prop from App.tsx at line ~1003. `toggleAct` + `selectedActs` Set filter results client-side by `r.act`.

## Backend changes

### 1. `backend/services/vector_search_service.py` — fix private/public ruling distinction
In `search()` result mapping, when `source_type == 'ruling'` and the meta's original act is `'private'`, emit `source_type='private_ruling'` and `act='private-rulings'`:
```python
if source_type == "case":
    act = "tax-cases"
elif source_type == "ruling" and m_act == "private":
    source_type = "private_ruling"
    act = "private-rulings"
elif source_type == "ruling":
    act = "rulings"
else:
    act = m_act
```

### 2. `backend/routes/search.py` — type filter semantics
Change:
```python
if type_filter and not (type_filter & {"ruling", "private_ruling"}):
    private_results = []
```
to:
```python
if type_filter and "private_ruling" not in type_filter:
    private_results = []
```
So `type=ruling` → public only; `type=private_ruling` → private only.

### 3. `backend/routes/search.py` — add `rtype` param (ruling series filter)
- Add `rtype: str | None = None` to `search_hybrid` signature.
- Parse: `rtype_set = set(rtype.upper().split(",")) if rtype else None`.
- After `ruling_results` fetched: filter to series prefixes:
  ```python
  if rtype_set:
      ruling_results = [r for r in ruling_results
                        if any(r.get("section", "").upper().startswith(p) for p in rtype_set)]
  ```
  Also filter vector results: after the existing `act`/`type_filter` filters, add:
  ```python
  if rtype_set:
      vector_results = [r for r in vector_results
                        if not (r.get("source_type") == "ruling") or
                        any(r.get("section", "").upper().startswith(p) for p in rtype_set)]
  ```
  (Public rulings only — private have source_type private_ruling after fix #1.)
- Note PS LA sections look like `PS LA 2004 3` — prefix `PS` matches. Good enough; don't over-engineer.

## Frontend changes

### 4. `frontend/src/api.ts` — `rtype` param
```ts
searchHybrid: (q: string, type?: string, limit?: number, opts?: { operator?: string; dateFrom?: string; dateTo?: string; rtype?: string }) => {
  ...
  if (opts?.rtype) url += `&rtype=${encodeURIComponent(opts.rtype)}`
  ...
}
```

### 5. `frontend/src/components/SearchPanel.tsx`
- **Type tabs** (~line 462): add `{ key: 'private_ruling', label: 'Private rulings' }` after Rulings. Keep 'ruling' label as 'Rulings'.
- **Ruling-series chips**: when `typeFilter === 'ruling'`, render a second row of chips below the tabs: `All | TR | TD | ATOID | PS LA | GSTR | PCG | CR | IT | TA`. State: `const [rtype, setRtype] = useState<string>('')`. Chip click: set rtype, reset page, `doSearch(undefined, 'ruling')`. Pass `rtype: rtype || undefined` in the opts of the hybrid call (only when typeFilter==='ruling'). "All" clears rtype.
- **Sources grouped**: replace the flat `acts.map(...)` Sources block (~line 440-460) with grouped rendering. Define the groups locally (import DOMAINS if exported, otherwise define a local `SOURCE_GROUPS` constant matching the DOMAINS list above — prefer exporting DOMAINS from App.tsx or moving it to a shared location; simplest safe option: define a local const in SearchPanel.tsx duplicating the groups, since App.tsx's DOMAINS is not exported and moving it risks touching App.tsx broadly). Render per group:
  ```
  <div key={g.label}>
    <div style={groupLabel}>{g.label}</div>
    <div style={chips}>{acts.filter(a => g.ids.includes(a.id)).map(act => checkbox)}</div>
  </div>
  ```
  Keep the same checkbox styling as today. Acts not in any group can render under an "Other" group (defensive).

### 6. Result badge
Line ~530 already handles `private_ruling` badge (`'PR'`, amber). Confirm `isRuling` includes private_ruling (`r.type === 'ruling' || r.type === 'private_ruling'` — it already does). No change needed, just verify.

## Verification (must all pass)

1. `cd /home/harrison/legislation-explorer && ./backend/venv/bin/python -c "import ast; ast.parse(open('backend/routes/search.py').read()); ast.parse(open('backend/services/vector_search_service.py').read()); print('syntax OK')"`
2. Restart: `systemctl --user restart legislation-explorer.service && sleep 4 && curl -s http://127.0.0.1:8765/health` → `{"status":"ok"}`
3. API checks:
   - `curl 'http://127.0.0.1:8765/api/search/hybrid?q=capital%20gains&limit=30&type=ruling'` → all results `source_type == 'ruling'` (NO private_ruling mixed in, NO authnum sections like `101...`)
   - `curl '...&type=private_ruling'` → all results `source_type == 'private_ruling'` with authnum sections
   - `curl '...&type=ruling&rtype=TD'` → all sections start with `TD`
   - `curl '...&type=ruling&rtype=TR,TD'` → all sections start with TR or TD
4. Frontend: `cd frontend && npx tsc --noEmit` clean (or `npm run build` succeeds).
5. Rebuild dist: `cd frontend && npm run build` (deployment serves `frontend/dist`).

## Constraints
- Do NOT touch `scripts/`, `data/`, cron files, or anything outside `backend/services/vector_search_service.py`, `backend/routes/search.py`, `frontend/src/api.ts`, `frontend/src/components/SearchPanel.tsx` (and optionally `frontend/src/App.tsx` if exporting DOMAINS).
- Keep the existing UI style (COLORS.* tokens, Montserrat 10-11px, accent highlight `COLORS.accent + '22'`).
- No new dependencies.
- Commit on the existing feature branch with a descriptive message when done.
