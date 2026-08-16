# Procedural Knowledge Specification — v0.1 (draft)
# Workflow maps for structured tax reasoning. The LLM follows a decision
# map; the graph supplies authority at each step.
# Companion spec: docs/specs/graph.md

## 1. Purpose

Tax analysis is procedural: CGT follows a statutory method (asset ->
event -> entity -> proceeds -> cost base -> exemptions -> discount ->
aggregation). A workflow is a decision map that tells the LLM *where it
could go next*, so it reasons in statutory order instead of free-form.

## 2. Workflow file format

YAML, one file per topic. Validated at compile time.

```yaml
id: cgt-analysis
name: CGT Analysis
area: income-tax
version: 0.1
entry: [asset, event]          # entry nodes (may be multiple)

nodes:
  asset:
    question: "Is there a CGT asset involved? (s 108-5)"
    fetch: ["itaa-1997:108-5"]          # section anchors (graph node keys)
    traverse: ["interpreted_by", "applies", "considered_in"]
    branches:
      - if: "not a CGT asset (...) under threshold)"
        then: stop_no_cgt
      - if: "is a CGT asset"
        then: event
    terminal: false            # optional, default false

  stop_no_cgt:
    question: "No CGT applies — end analysis."
    terminal: true

rules:
  - "At each node: retrieve fetched sections, pull graph context, then branch."
  - "Authorities must cite section numbers + ruling/case references — never invented."
```

Schema per node:
- `question` (required): what the LLM must determine from the facts
- `fetch` (optional): graph node keys to pull content for at this step
- `traverse` (optional): edge types to follow for graph context
- `branches` (optional): list of `{if: condition, then: node}` — the map
  of where to go next
- `terminal` (optional, default false): true = analysis ends here

Validation at compile time:
- every `fetch` key resolves in the graph nodes table
- every `then` target exists in the workflow's node map
- at least one entry node, and every entry node exists in the node map
- no unreachable nodes (warn)
- no cycles through terminal nodes (warn)

## 3. Lifecycle: author -> compile -> serve

### 3.1 Author
Human-authored YAML (tax specialist). Versioned in repo.
`data/workflows/cgt.yaml` is the reference implementation.

### 3.2 Compile (server start, once)
- Load all workflow files into an in-memory `WorkflowRegistry`
- Validate against graph node table (fetch anchors exist)
- Build node index: `{workflow_id: {node_id: {question, fetch, traverse, branches, terminal}}}`
- Cost: ~11KB per workflow, loaded once, never refetched
- On validation failure: refuse to serve that workflow, log the error

### 3.3 Serve (per query)
The LLM never receives the full map. Each step injects only the current
node's slice (~200 tokens):

```
## STEP: asset (CGT Analysis)
Q: Is there a CGT asset involved? (s 108-5)
FETCH: itaa-1997:108-5
WHERE TO GO NEXT:
  - not a CGT asset (...) -> stop (no CGT)
  - is a CGT asset -> event
```

The slice is produced by a dict lookup — no I/O, no model call.

## 4. Topic detection + routing

Before workflow attachment, detect whether a workflow applies to the query.

- Keyword/entity signal table per workflow (CGT: "CGT", "capital gain",
  "cost base", "main residence", "CGT event"; FBT: "FBT", "fringe
  benefit", "car benefit"; etc.)
- Cheap pre-filter: regex over the query (+ optionally the top search
  results' titles) — no model call in the hot path
- Ambiguous cases: include the workflow *entry node list* in context and
  let the LLM decide whether to follow it (the entry slice is tiny)
- One query can attach multiple workflows (e.g. CGT + deceased estates)
  — each injects its entry slice; the LLM chooses which to follow

## 5. Execution model

Stateless per request; the *conversation* carries state, not the server.

- Each search/query response includes:
  1. search results (nodes + graph context, per graph spec)
  2. the current workflow node slice (if a workflow is active)
- The LLM's reply includes the chosen branch node id (structured output
  or inline in text — parseable)
- Next request passes `?workflow=cgt-analysis&node=<chosen>` — server
  injects that node's slice
- No server-side session state; the workflow position travels in the
  query params. Simple, horizontally scalable, resumable.

If the LLM goes off-map (chooses a node not in branches, or the analysis
concludes): server returns terminal node slice, workflow ends.

## 6. Caching

- WorkflowRegistry: in-memory, loaded once (per §3.2)
- Node slices: generated once per node at compile time, cached in memory
  (22 nodes x ~200 tokens = trivial)
- Graph context for fetch anchors: served by the graph layer's normal
  query cache — no per-workflow duplication
- Nothing is refetched per query except the dict lookups

## 7. Anti-hallucination rules

- Authorities come from graph edges only — section numbers and
  ruling/case refs in the LLM's output must resolve to fetched nodes or
  traversed edges
- Rules section in each workflow enforces statutory order and
  prerequisites (e.g. small business concessions require s 152-10 basic
  conditions first)
- Terminal nodes force an explicit conclusion — the LLM can't wander
  after the map says stop

## 8. Reference implementation: CGT

`data/workflows/cgt.yaml` — 22 nodes, 9 stages:

asset -> event -> entity -> proceeds -> cost_base -> gain_loss ->
exemptions -> discount -> net_gain

With sub-maps: trust_path/deceased_estate, foreign_resident, indexation,
main_residence, small_business (4 concessions + basic-conditions gate),
rollover, losses. Entry: [asset, event].

## 9. Roadmap

1. WorkflowRegistry + validator + slice serializer (server-side)
2. Topic-detection pre-filter
3. Query-param state passing (`?workflow=&node=`)
4. (DONE) Pattern generalised: data/workflows/ already contains 8
   workflows (cgt, deceased-estates, div-7a, ess, gst, psi, tax-losses,
   trust-distributions) and workflow_registry.py + routes/workflows.py
   implement roadmap items 1-3. Next: coverage expansion, not proof.
5. Test harness: golden queries per workflow, assert the LLM follows
   statutory order and cites real graph authorities
6. Workflow editor (optional, later) — visual map authoring

## 10. Open questions

- Structured output for branch choice (JSON field) vs parsing inline text
  — JSON field is more reliable; decide at implementation
- Multi-workflow precedence when several attach (e.g. CGT + deceased
  estate): let the LLM choose at entry, or define a priority order
- Whether `fetch` anchors should also surface their depth-1 graph context
  automatically (yes, lean: counts + top-3, per graph spec §6.2)
