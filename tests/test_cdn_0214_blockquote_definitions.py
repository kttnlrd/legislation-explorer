"""CDN-0214 — the definitions extractor must scan blockquote (">") lines.

The 2026-09-19/20 ITAA-1997 re-ingest rendered the whole s 995-1 dictionary as
a single Markdown blockquote, so every definition line carries a leading ">".
``iter_definition_starts()`` skipped those lines outright, which hid 1,725 of
the 3,098 block lines and dropped three of the five R&D terms
(``R&D activities``, ``R&D entity``, ``core R&D activities``) from the served
catalogue. The fix strips the blockquote marker and keeps scanning; list
items, note lines and bare anchors are still filtered by the existing checks.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PIPELINE = ROOT / "pipeline"

# The served itaa-1997 dictionary source.
ITA_995_1 = (ROOT / "data" / "itaa-1997" / "sections" / "part-6-5"
             / "division-995" / "995-1.md")

# The 5 R&D terms the ticket's blast radius names; three live on ">" lines.
R_AND_D = {"r&d activities", "r&d entity", "r&d partnership",
           "core r&d activities", "supporting r&d activities"}


def _module():
    spec = importlib.util.spec_from_file_location(
        "extract_definitions_under_test", PIPELINE / "extract_definitions.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


ED = _module()


def test_blockquote_lines_are_scanned():
    """A blockquote definition line yields its term instead of being skipped."""
    block = (
        "> R&D entity has the meaning given by section 355-35.\n"
        "> RBA surplus has the same meaning as in Part IIB of the Taxation "
        "Administration Act 1953.\n"
    )
    got = list(ED.iter_definition_starts(block))
    assert "R&D entity" in got, got
    assert "RBA surplus" in got, got


def test_blockquote_anchor_and_note_lines_still_filtered():
    """Stripping ">" must not resurrect anchors or notes as terms."""
    block = (
        '> <a id="s995-1-a"></a>\n'
        "> **(a)** *accounting standards; or\n"
        "> **Note:** A CGT asset acquired before 20 September 1985 may be "
        "treated as acquired on or after that day.\n"
    )
    assert list(ED.iter_definition_starts(block)) == []


def test_all_five_r_and_d_terms_recovered():
    """The served source now re-derives all 5 R&D terms (CDN-0214)."""
    terms, _log = ED.extract_act("itaa-1997", ITA_995_1)
    got = {k for k in terms if k in R_AND_D}
    missing = sorted(R_AND_D - got)
    assert not missing, f"missing R&D terms: {missing}"


def test_rederivation_count_above_blockquote_regression_floor():
    """The run-on blockquote fix re-derives the bulk of the dictionary.

    Before the fix ``extract_act`` returned 803 terms (it skipped every ">"
    line). After it, ~1,497. The floor guards against a future regression that
    silently re-introduces the skip.
    """
    terms, _log = ED.extract_act("itaa-1997", ITA_995_1)
    assert len(terms) >= 1400, f"re-derived only {len(terms)} terms"


def test_table_reference_boilerplate_is_not_part_of_the_term():
    """A colon term followed by a table gets the bare term, not the marker.

    "X is defined as set out in this table:" announces that a table below defines
    X; the marker is not part of the term.  The bare-colon shape (no definition
    on the same line) must still capture X (CDN-0214).
    """
    block = (
        "tax-free amount of a payment is defined as set out in this table:\n"
        "ordinary payment is defined as set out in this table: Ordinary payment\n"
    )
    got = list(ED.iter_definition_starts(block))
    assert "tax-free amount of a payment" in got, got
    assert "ordinary payment" in got, got
    assert not any("defined as set out" in t for t in got), got


def test_table_reference_key_is_rejected():
    """reject_key drops the table-reference marker so it cannot be preserved."""
    assert ED.reject_key("ordinary payment is defined as set out in this table")
    assert not ED.reject_key("ordinary payment")
