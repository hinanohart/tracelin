"""The MAST annotation table stays internally consistent and honest.

These tests make the taxonomy reference data load-bearing: every category the
engine can emit must be a real MAST category, the documented mode reference must
faithfully list all 14 modes, and the advisory note must be present exactly when
a mapping exists.
"""

from tracelin.mast import (
    _KIND_TO_MAST,
    MAST_CATEGORIES,
    MAST_MODES_REFERENCE,
    annotate,
    note_for,
)
from tracelin.verdict import Violation


def test_every_mapped_category_is_a_known_mast_category():
    for kind, (cat, _note) in _KIND_TO_MAST.items():
        assert cat in MAST_CATEGORIES, f"{kind} maps to unknown category {cat!r}"


def test_reference_lists_all_fourteen_modes_across_the_three_categories():
    assert set(MAST_MODES_REFERENCE) == set(MAST_CATEGORIES)
    total = sum(len(modes) for modes in MAST_MODES_REFERENCE.values())
    assert total == 14


def test_annotate_sets_category_and_defaults_to_unmapped():
    v = annotate(Violation("concurrent_write_race", "race"))
    assert v.mast_id == "FC2"
    u = annotate(Violation("something_not_modelled", "x"))
    assert u.mast_id == "UNMAPPED"


def test_note_is_present_iff_mapped():
    assert note_for(Violation("concurrent_write_race", "race")) != ""
    assert note_for(Violation("illegal_transition", "t")) != ""
    assert note_for(Violation("not_a_known_kind", "x")) == ""
