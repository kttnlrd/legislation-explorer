**1. VERDICT**
APPROVE-WITH-CHANGES

**2. BLOCKERS**
*   **Incorrect PDF Source Mapping:** The plan's Phase 0 table contains factual errors that will cause incorrect fallbacks. You must update the plan's mapping to reflect the verified evidence: `itaa-1936` staging PDFs *are* comp 191 (matching corpus, safe to use directly), and `itaa-1997` comp 266 PDFs *do* exist at `staging/data/itaa-1997/raw/comp266/vol01-12.pdf`.
*   **Unsafe Fidelity Gate:** A 98% fidelity gate is unacceptable for legal text (losing 2% of words could mean dropping "not" or "only"). You must replace this with a 100% bidirectional token-provenance gate.
*   **Lack of Prose-Preservation Gate:** The plan lacks a programmatic guarantee that non-table text remains untouched. 

**3. REQUIRED CHANGES BEFORE EXECUTION (Prioritised)**
1.  **Update Source Mapping:** Hardcode the correct PDF paths for `itaa-1997` (comp 266 at the `staging/data/.../comp266/` path) and `itaa-1936` (comp 191).
2.  **Implement 100% Token Gate:** Write a validator that extracts all words from the PDF table bounding box and all words from the rebuilt Markdown table. Strip punctuation, markdown formatting, and case. Assert `Counter(pdf_tokens) == Counter(md_tokens)`.
3.  **Implement Strict Diff Gate:** Before saving any rebuilt file, strip all lines starting with `|` from both the original and rebuilt markdown strings. Assert the remaining text is byte-for-byte identical.
4.  **Reorder Execution:** Move `sis-1993` (32 findings, perfect PDF match) to Phase 1 for calibration. Move `itaa-1997` (418 findings, complex pathing) to Phase 2.
5.  **Fix Extractor Defects First:** Apply the fixes for the hardcoded 'Item' header, the 55pt row cap, the y>=600 footer drop, and the subprocess overhead *before* running the pipeline on any act.

**4. SPECIFIC ASSESSMENTS**

*   **(a) >=98% fidelity gate vs 100% bidirectional token-provenance:** 
    98% is a research metric, not a legal engineering gate. You must use 100% bidirectional token matching (using `collections.Counter` on alphanumeric tokens). If a table fails 100% due to complex reading order or formulas, it must be rejected and flagged for manual review. Do not silently accept lossy text.
*   **(b) Rebuilding itaa-1997 from comp-266 PDFs:** 
    It is safe *only if* you use the verified path (`staging/data/itaa-1997/raw/comp266/vol01-12.pdf`). Before extracting tables, you must verify that the non-table prose in the PDF page exactly matches the non-table prose in the corpus markdown to ensure no compilation drift occurred between the staging raw and the corpus.
*   **(c) Order of acts:** 
    Starting with `itaa-1997` is high-risk. Calibrate the extractor and gates on `sis-1993` first. It has only 32 findings, and its staging PDFs perfectly match the corpus compilation (126). Once the 100% token gate passes on `sis-1993`, proceed to `fbt-1986`, then tackle `itaa-1997`.
*   **(d) How to prove ONLY table regions changed:** 
    In memory, before writing to disk: `original_prose = "\n".join([line for line in old_md.splitlines() if not line.strip().startswith("|")])`. Do the same for `new_md`. Assert `original_prose == new_prose`. This mathematically guarantees zero regression outside tables.
*   **(e) Missing gates for completeness:** 
    *   *Row counts:* `new_row_count >= old_row_count` (since the bug is truncated/merged rows, rows should only increase or stay the same).
    *   *Headers:* The first row of the MD table must contain the exact column headers detected in the PDF.
    *   *Notes:* Asterisk notes (e.g., "*To find definitions...") must be detected via regex and explicitly appended *below* the markdown table, not swallowed or injected into cells.
    *   *Formula tables:* Reject any table containing `ç ÷ ´ ê ú æ` in the final markdown. Flag for manual reconstruction.

---USAGE--- {"prompt_tokens": 5575, "completion_tokens": 2687, "total_tokens": 8262, "cost": 0.043394, "is_byok": false, "prompt_tokens_details": {"cached_tokens": 0, "cache_write_tokens": 0, "audio_tokens": 0, "video_tokens": 0}, "cost_details": {"upstream_inference_cost": 0.043394, "upstream_inference_prompt_cost": 0.01115, "upstream_inference_completions_cost": 0.032244}, "completion_tokens_details": {"reasoning_tokens": 1604, "image_tokens": 0, "audio_tokens": 0}}
R2API_DONE
