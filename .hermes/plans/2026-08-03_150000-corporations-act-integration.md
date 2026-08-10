# Corporations Act Integration Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Fully integrate the Corporations Act 2001 into the legislation explorer — data exists but gaps remain in definitions indexing, frontend display names, and UI navigation.

**Architecture:** The Corps Act data is already ingested (4,163 sections, 32 chapters, tree.json) and the backend FTS5 index already picks it up automatically. Three integration gaps remain: (1) definitions not extracted, (2) frontend lacks display name entry, (3) hardcoded act fallback list missing corps.

**Tech Stack:** Python (backend), TypeScript/React (frontend), SQLite FTS5 (search)

---

### Task 1: Add display name for corps act in frontend

**Objective:** The `shortActName` function in `display.ts` returns an ugly fallback for `corporations-act-2001`. Add the proper short name.

**Files:**
- Modify: `frontend/src/utils/display.ts:13`

**Step 1: Add entry**

Add `'corporations-act-2001': 'Corps Act',` to the `ACT_SHORT` map in `display.ts`.

Before:
```typescript
const ACT_SHORT: Record<string, string> = {
  'itaa-1997': 'ITAA97',
  ...
  'tax-cases': 'Tax Cases',
}
```

After:
```typescript
const ACT_SHORT: Record<string, string> = {
  'itaa-1997': 'ITAA97',
  ...
  'tax-cases': 'Tax Cases',
  'corporations-act-2001': 'Corps Act',
}
```

**Step 2: Verify**

Check that the frontend build compiles. Run: `cd /home/harrison/legislation-explorer/frontend && npx tsc --noEmit 2>&1 | head -20`

Expected: No TypeScript errors.

---

### Task 2: Add corps act to hardcoded fallback act list

**Objective:** The settings panel and act picker have a hardcoded fallback act list when the backend hasn't loaded acts yet. Add the corps act.

**Files:**
- Modify: `frontend/src/App.tsx:378` and `frontend/src/components/SettingsPanel.tsx:188`

**Step 1: Find and update fallback in App.tsx**

In `App.tsx`, find the act picker fallback:
```tsx
{(acts.length > 0 ? acts : [{ id: 'itaa-1997', name: 'ITAA 1997' }, { id: 'itaa-1936', name: 'ITAA 1936' }]).map(a => (
```

Add the corps act entry:
```tsx
{(acts.length > 0 ? acts : [
  { id: 'itaa-1997', name: 'ITAA 1997' },
  { id: 'itaa-1936', name: 'ITAA 1936' },
  { id: 'corporations-act-2001', name: 'Corporations Act 2001' }
]).map(a => (
```

**Step 2: Find and update fallback in SettingsPanel.tsx**

Same pattern — add the corps act to the fallback list.

**Step 3: Verify**

TypeScript check: `cd /home/harrison/legislation-explorer/frontend && npx tsc --noEmit 2>&1 | head -20`

Expected: No TypeScript errors.

---

### Task 3: Extract corps act definitions into definitions_all.json

**Objective:** The `definitions_all.json` file has definitions for `itaa-1997`, `itaa-1936`, and `gst-1999` but not for `corporations-act-2001`. Corps Act definitions live in dictionary sections (s.9, s.761A, s.1211A etc.). Extract them.

**Files:**
- Modify: `data/definitions_all.json` (via Python script)
- Create (temp): `scripts/extract_corps_definitions.py`

**Step 1: Read existing definitions pattern**

Check how definitions are structured in `definitions_all.json`:
```json
{
  "itaa-1997": {
    "section": "995-1",
    "terms": {
      "term name": { "section": "995-1", "definition": "..." },
      ...
    }
  }
}
```

**Step 2: Write extraction script**

Create `scripts/extract_corps_definitions.py` that:
1. Reads all corps act section markdown files
2. For dictionary sections (s.9, s.761A, etc.), parse the definition terms
3. Build the same `{ section, definition }` structure
4. Merge into `definitions_all.json`

The Corp Act dictionary sections are:
- s.9 (Ch 1 definitions)
- s.761A (Ch 7 definitions)
- s.1211A (Ch 8A definitions)
- s.1221 (Ch 8B definitions)
- s.1371 (transitional definitions)
- s.1400 (Schedule 4 definitions)
- And any other section tagged as "Definitions" or "Interpretation"

**Step 3: Run extraction**

```bash
cd /home/harrison/legislation-explorer && python3 scripts/extract_corps_definitions.py
```

**Step 4: Verify**

```bash
python3 -c "import json; d=json.load(open('data/definitions_all.json')); print('Corps terms:', len(d.get('corporations-act-2001',{}).get('terms',{})))"
```

Expected: At least several hundred defined terms.

---

### Task 4: Rebuild search index and restart server

**Objective:** After adding the corps act data changes, rebuild the FTS5 search index and restart the server so all changes take effect.

**Step 1: Delete old search DB**

```bash
rm -f /home/harrison/legislation-explorer/data/search.db
```

**Step 2: Restart server**

```bash
systemctl --user restart legislation-explorer.service
```

**Step 3: Wait for startup**

```bash
sleep 10
```

**Step 4: Verify corps act is in the API**

```bash
curl -s http://localhost:8765/api/acts | python3 -c "import sys,json; acts=json.load(sys.stdin); corps=[a for a in acts if 'corp' in a['id']]; print('Corps act in API:', bool(corps)); [print(f'  {a[\"id\"]}: {a[\"name\"]}') for a in corps]"
```

Expected: `Corps act in API: True` and the corps act listed.

**Step 5: Verify a corps section loads**

```bash
curl -s 'http://localhost:8765/api/section/corporations-act-2001/124' | head -20
```

Expected: Returns s.124 Legal capacity data.

**Step 6: Verify FTS5 search works for corps**

```bash
curl -s 'http://localhost:8765/api/search?q=director&act=corporations-act-2001&limit=5' | python3 -m json.tool | head -30
```

Expected: Returns corps act section hits for "director".

---

## Risks and Edge Cases

- **Definitions extraction quality**: Dictionary sections (s.9, s.761A) are large and use ad-hoc formatting. The regex/parsing approach may miss some definitions. Better to extract at least 80% than to wait for perfection.
- **Frontend tree rendering**: The corps act tree uses 'divisions' for Parts and 'subdivisions' for Divisions within a Part. This is the same nesting pattern as other acts — already verified compatible.
- **Server restart**: The FTS5 rebuild during server startup takes ~30s. During this time searches return empty results.
- **Large sections**: s.9 (dictionary) has ~400+ defined terms. The body may be truncated like s.995-1 ITAA 1997. The get_definition tool should be used for specific term lookups.

## Verification Checklist

- [ ] Frontend shows "Corps Act" in act picker
- [ ] Switching to corps act loads tree with chapter/part/division/section hierarchy
- [ ] Opening s.124 shows full text of "Legal capacity"
- [ ] Searching "director" within corps act returns relevant sections
- [ ] Searching "director" globally also shows corps hits
- [ ] get_definition("director", act="corporations-act-2001") works
- [ ] get_section works via MCP for corps act