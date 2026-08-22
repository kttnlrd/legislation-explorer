#!/bin/bash
# Legislation Explorer — Reproducible full rebuild from source PDFs.
# 
# WARNING: This wipes and regenerates data/sections/* for all acts.
# Run backup first: ./scripts/backup.sh
#
# Pipeline order is documented inline. Do not reorder stages without
# understanding dependencies.

set -euo pipefail

cd "$(dirname "$0")"
PROJECT="$(pwd)"
DATA="$PROJECT/data"
SOURCE="$PROJECT/source"

export PYTHONPATH="${PROJECT}/backend:${PYTHONPATH:-}"

# ---------------------------------------------------------------------------
# 0. Validation
# ---------------------------------------------------------------------------
echo "=== 0. Validation ==="
for cmd in pdftotext python3; do
    if ! command -v "$cmd" &>/dev/null; then
        echo "ERROR: $cmd not found"
        exit 1
    fi
done

# ---------------------------------------------------------------------------
# 1. Extract PDFs to raw text (idempotent — only if raw/ missing or stale)
# ---------------------------------------------------------------------------
echo "=== 1. PDF extraction ==="

extract_pdfs() {
    local act_dir="$1"
    local raw_dir="$2"
    mkdir -p "$raw_dir"
    local extracted=0
    for pdf in "$act_dir"/*.pdf; do
        [ -e "$pdf" ] || continue
        local basename
        basename=$(basename "$pdf" .pdf | tr '[:upper:]' '[:lower:]')
        # Map volume names: C2026C00122VOL01.pdf -> vol01.txt
        local volname
        volname=$(echo "$basename" | grep -oP 'vol\d+' || echo "$basename")
        local txtout="$raw_dir/${volname}.txt"
        if [ ! -f "$txtout" ] || [ "$pdf" -nt "$txtout" ]; then
            echo "  Extracting $pdf -> $txtout"
            pdftotext -layout "$pdf" "$txtout"
            extracted=$((extracted + 1))
        fi
    done
    echo "  $extracted volumes extracted"
}

extract_pdfs "$SOURCE/itaa-1997"   "$DATA/itaa-1997/raw"
extract_pdfs "$SOURCE/itaa-1936"   "$DATA/itaa-1936/raw"
extract_pdfs "$SOURCE/gst-1999"    "$DATA/gst-1999/raw"
extract_pdfs "$SOURCE/taa-1953"    "$DATA/taa-1953/raw"

# ---------------------------------------------------------------------------
# 2. Parse primary legislation
# ---------------------------------------------------------------------------
echo "=== 2. Parse ITAA 1997 ==="
rm -rf "$DATA/itaa-1997/sections"
python3 pipeline/parse_itaa97.py \
    --raw-dir "$DATA/itaa-1997/raw" \
    --out-dir "$DATA/itaa-1997/sections" \
    --compilation-no 266 \
    --compilation-date 2026-07-01

echo "=== 3. Parse ITAA 1936 (vols 1-4) ==="
rm -rf "$DATA/itaa-1936/sections"
python3 pipeline/parse_itaa36.py \
    --raw-dir "$DATA/itaa-1936/raw" \
    --out-dir "$DATA/itaa-1936/sections" \
    --compilation-no 192 \
    --compilation-date 2026-07-01

echo "=== 4. Parse ITAA 1936 schedules (vol 5) ==="
python3 pipeline/parse_itaa36_schedules.py \
    --raw-file "$DATA/itaa-1936/raw/vol05.txt" \
    --out-dir "$DATA/itaa-1936/sections" \
    --tree-file "$DATA/itaa-1936/tree.json"

echo "=== 5. Parse GST 1999 ==="
rm -rf "$DATA/gst-1999/sections"
python3 pipeline/parse_gst1999.py \
    --raw-dir "$DATA/gst-1999/raw" \
    --out-dir "$DATA/gst-1999/sections" \
    --compilation-no 96 \
    --compilation-date 2026-01-01

echo "=== 6. Parse TAA 1953 ==="
rm -rf "$DATA/taa-1953/sections"
python3 pipeline/parse_taa53.py \
    --raw-dir "$DATA/taa-1953/raw" \
    --out-dir "$DATA/taa-1953/sections" \
    --compilation-no 225 \
    --compilation-date 2026-07-01

# ---------------------------------------------------------------------------
# 3. Build navigation trees
# ---------------------------------------------------------------------------
echo "=== 7. Build trees ==="
python3 pipeline/build_tree.py \
    --sections-dir "$DATA/itaa-1997/sections" \
    --out-file "$DATA/itaa-1997/tree.json" \
    --act "ITAA 1997" \
    --compilation-no 266 \
    --compilation-date 2026-07-01

python3 pipeline/build_tree.py \
    --sections-dir "$DATA/itaa-1936/sections" \
    --out-file "$DATA/itaa-1936/tree.json" \
    --act "ITAA 1936" \
    --compilation-no 192 \
    --compilation-date 2026-07-01

python3 pipeline/build_tree.py \
    --sections-dir "$DATA/gst-1999/sections" \
    --out-file "$DATA/gst-1999/tree.json" \
    --act "GST Act 1999" \
    --compilation-no 96 \
    --compilation-date 2026-01-01

python3 pipeline/build_tree.py \
    --sections-dir "$DATA/taa-1953/sections" \
    --out-file "$DATA/taa-1953/tree.json" \
    --act "TAA 1953" \
    --compilation-no 225 \
    --compilation-date 2026-07-01 \
    --flat-divisions

# ---------------------------------------------------------------------------
# 4. CCH commentary (depends on external MCP pipeline output)
# ---------------------------------------------------------------------------
echo "=== 8. Build CCH commentary ==="
python3 pipeline/build_cch_explorer.py

# ---------------------------------------------------------------------------
# 5. Definitions
# ---------------------------------------------------------------------------
# Flow: extract_definitions.py  -> data/{act}/definitions.json  (per-act term catalog)
#       extract_all_definitions.py -> data/definitions_all.json  (merged; served by backend)
# Definition linking is done at serve time in backend/processors/markdown.py.
# pipeline/link_definitions.py (static in-place linker) has been retired and moved
# to scripts/legacy/link_definitions.py.
echo "=== 9. Extract definitions ==="
python3 pipeline/extract_definitions.py
python3 pipeline/extract_all_definitions.py

# ---------------------------------------------------------------------------
# 6. Citation / ruling / smartlink indices
# ---------------------------------------------------------------------------
echo "=== 10. Build citation index ==="
python3 pipeline/build_citation_index.py

echo "=== 11. Build ruling index ==="
python3 scripts/build_ruling_index.py

echo "=== 12. Build smartlink index ==="
python3 scripts/build_smartlink_index.py

# ---------------------------------------------------------------------------
# 7. Search index
# ---------------------------------------------------------------------------
echo "=== 13. Rebuild search index ==="
rm -f "$PROJECT/search_index.db"
python3 scripts/rebuild_search_index.py

# ---------------------------------------------------------------------------
# 8. Verification
# ---------------------------------------------------------------------------
echo "=== 14. Verification ==="
TOTAL_MD=$(find "$DATA" -name '*.md' | wc -l)
echo "  Total .md files: $TOTAL_MD"
for act in itaa-1997 itaa-1936 gst-1999 taa-1953 master-tax-guide master-gst-guide master-tax-examples; do
    tree="$DATA/$act/tree.json"
    if [ -f "$tree" ]; then
        PARTS=$(python3 -c "import json; t=json.load(open('$tree')); print(len(t.get('parts',[])))" 2>/dev/null || echo 0)
        echo "  $act: $PARTS parts"
    else
        echo "  $act: NO tree.json"
    fi
done

if [ -f "$PROJECT/search_index.db" ]; then
    SIZE=$(du -h "$PROJECT/search_index.db" | cut -f1)
    echo "  search_index.db: $SIZE"
else
    echo "  WARNING: search_index.db missing"
fi

echo ""
echo "Rebuild complete."

# ---------------------------------------------------------------------------
# 15. Data validation gate
# ---------------------------------------------------------------------------
echo "=== 15. Data validation ==="
VALIDATE_EXIT=0
python3 "$PROJECT/scripts/validate_data.py" --data-dir "$DATA" || VALIDATE_EXIT=$?
if [ $VALIDATE_EXIT -ne 0 ]; then
    echo "ERROR: Data validation failed — see above for details."
fi
exit $VALIDATE_EXIT
