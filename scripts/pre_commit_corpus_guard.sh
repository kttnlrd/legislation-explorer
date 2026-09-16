#!/bin/sh
# Versioned git pre-commit hook: run corpus_change_guard over the staged
# corpus section files.  Installed by scripts/install_corpus_guard_hook.sh.
#
# Escape hatch for deliberate bulk work (e.g. a reviewed compilation import):
#   CORPUS_GUARD_BYPASS=1 git commit ...
set -e
[ -n "$CORPUS_GUARD_BYPASS" ] && { echo "corpus guard: bypassed (CORPUS_GUARD_BYPASS set)"; exit 0; }

# no corpus files staged -> nothing to do, no python started
git diff --cached --name-only | grep -Eq '^data/[^/]+/sections/.*\.md$' || exit 0

PY=/usr/bin/python3.12
[ -x "$PY" ] || PY=python3
exec "$PY" "$(git rev-parse --show-toplevel)/scripts/corpus_change_guard.py" --quiet-ok
