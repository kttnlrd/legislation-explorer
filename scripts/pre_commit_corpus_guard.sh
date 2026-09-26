#!/bin/sh
# Versioned git pre-commit hook: run corpus_change_guard over the staged
# corpus section files AND any untracked (never-added) section file.
# Installed by scripts/install_corpus_guard_hook.sh.
#
# Escape hatch for deliberate bulk work (e.g. a reviewed compilation import):
#   CORPUS_GUARD_BYPASS=1 git commit ...
set -e
[ -n "$CORPUS_GUARD_BYPASS" ] && { echo "corpus guard: bypassed (CORPUS_GUARD_BYPASS set)"; exit 0; }

# Nothing to do, and no python started, UNLESS a section file is either staged or untracked.
# X1 (2026-09-26): the early exit used to test only the staged diff, so a commit that staged
# code and nothing else walked straight past corpus_change_guard.py's untracked-file scan
# (:194) - a bulk dump into data/ never touches the index, so a bad-shape section file could
# sit unnoticed until some unrelated corpus commit. Both populations are now the guard's
# trigger; the guard itself decides what to do with them.
if ! git diff --cached --name-only | grep -Eq '^data/[^/]+/sections/.*\.md$' \
   && ! git ls-files --others --exclude-standard -- data | grep -Eq 'sections/.*\.md'; then
    exit 0
fi

PY=/usr/bin/python3.12
[ -x "$PY" ] || PY=python3
exec "$PY" "$(git rev-parse --show-toplevel)/scripts/corpus_change_guard.py" --quiet-ok
