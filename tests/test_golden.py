"""Frozen golden cases: verdict + witness kind + MAST category pinned."""

import pytest
from tracelin import check
from tracelin.verdict import Verdict

from conftest import ev, hist

# (name, spec, History, expected verdict, expected kind|None, expected MAST|None)
CASES = [
    (
        "a2a_clean",
        "a2a_lifecycle",
        hist(
            ev("o", "STATE_TRANSITION", key="t", value="submitted", span="s0"),
            ev("o", "STATE_TRANSITION", key="t", value="working", span="s1"),
            ev("o", "STATE_TRANSITION", key="t", value="completed", span="s2"),
        ),
        Verdict.PASS,
        None,
        None,
    ),
    (
        "a2a_illegal_transition",
        "a2a_lifecycle",
        hist(
            ev("o", "STATE_TRANSITION", key="t", value="submitted", span="s0"),
            ev("o", "STATE_TRANSITION", key="t", value="completed", span="s1"),
        ),
        Verdict.WITNESS,
        "illegal_transition",
        "FC1",
    ),
    (
        "a2a_non_entry_start",
        "a2a_lifecycle",
        hist(
            ev("o", "STATE_TRANSITION", key="t", value="working", span="s0"),
        ),
        Verdict.PASS,
        None,
        None,
    ),  # working is a valid entry
    (
        "a2a_bad_entry",
        "a2a_lifecycle",
        hist(
            ev("o", "STATE_TRANSITION", key="t", value="completed", span="s0"),
        ),
        Verdict.WITNESS,
        "illegal_transition",
        "FC1",
    ),
    (
        "a2a_act_after_terminal",
        "a2a_lifecycle",
        hist(
            ev("o", "STATE_TRANSITION", key="t", value="submitted", span="s0"),
            ev("o", "STATE_TRANSITION", key="t", value="failed", span="s1"),
            ev("w", "TOOL_CALL", key="t", span="s2", parent="s1"),
        ),
        Verdict.WITNESS,
        "act_after_terminal",
        "FC3",
    ),
    (
        "a2a_double_assignee",
        "a2a_lifecycle",
        hist(
            ev("sys", "STATE_TRANSITION", key="sub", value="submitted", span="root"),
            ev("o1", "ASSIGN", key="sub", value="alice", span="s0", parent="root"),
            ev("o2", "ASSIGN", key="sub", value="bob", span="s1", parent="root"),
        ),
        Verdict.WITNESS,
        "double_assignee",
        "FC2",
    ),
    (
        "a2a_register_race",
        "a2a_lifecycle",
        hist(
            ev("s", "WRITE", key="x", value=0, span="i", object_type="register"),
            ev("a", "WRITE", key="x", value=1, span="a0", parent="i", object_type="register"),
            ev("b", "WRITE", key="x", value=2, span="b0", parent="i", object_type="register"),
        ),
        Verdict.WITNESS,
        "concurrent_write_race",
        "FC2",
    ),
    (
        "a2a_declared_merge_ok",
        "a2a_lifecycle",
        hist(
            ev("s", "WRITE", key="x", value=0, span="i", object_type="register", merge="add"),
            ev(
                "a",
                "WRITE",
                key="x",
                value=1,
                span="a0",
                parent="i",
                object_type="register",
                merge="add",
            ),
            ev(
                "b",
                "WRITE",
                key="x",
                value=2,
                span="b0",
                parent="i",
                object_type="register",
                merge="add",
            ),
        ),
        Verdict.PASS,
        None,
        None,
    ),
    (
        "lin_register_serial",
        "linearizable",
        hist(
            ev("a", "WRITE", value=1, span="a0"),
            ev("a", "READ", value=1, span="a1"),
        ),
        Verdict.PASS,
        None,
        None,
    ),
    (
        "lin_register_stale",
        "linearizable",
        hist(
            ev("a", "WRITE", value=0, span="a0"),
            ev("a", "WRITE", value=1, span="a1"),
            ev("a", "READ", value=0, span="a2"),
        ),
        Verdict.WITNESS,
        "not_linearizable",
        "FC2",
    ),
    (
        "lin_counter_correct",
        "linearizable",
        hist(
            ev("s", "WRITE", value=0, span="i", object_type="counter"),
            ev("a", "INC", span="a0", parent="i", object_type="counter"),
            ev("b", "INC", span="b0", parent="i", object_type="counter"),
            ev(
                "f",
                "READ",
                value=2,
                span="f0",
                parent="a0",
                links=("a0", "b0"),
                object_type="counter",
            ),
        ),
        Verdict.PASS,
        None,
        None,
    ),
    (
        "lin_counter_lost_update",
        "linearizable",
        hist(
            ev("s", "WRITE", value=0, span="i", object_type="counter"),
            ev("a", "INC", span="a0", parent="i", object_type="counter"),
            ev("b", "INC", span="b0", parent="i", object_type="counter"),
            ev(
                "f",
                "READ",
                value=1,
                span="f0",
                parent="a0",
                links=("a0", "b0"),
                object_type="counter",
            ),
        ),
        Verdict.WITNESS,
        "not_linearizable",
        "FC2",
    ),
    (
        "lin_map_ok",
        "linearizable",
        hist(
            ev("a", "WRITE", key="m", value=1, span="m0", object_type="map", subkey="k1"),
            ev("a", "READ", key="m", value=1, span="m1", object_type="map", subkey="k1"),
            ev("a", "WRITE", key="m", value=9, span="m2", object_type="map", subkey="k2"),
            ev("a", "READ", key="m", value=9, span="m3", object_type="map", subkey="k2"),
        ),
        Verdict.PASS,
        None,
        None,
    ),
    (
        "lin_map_one_bad_subkey",
        "linearizable",
        hist(
            ev("a", "WRITE", key="m", value=1, span="m0", object_type="map", subkey="k1"),
            ev("a", "READ", key="m", value=2, span="m1", object_type="map", subkey="k1"),
        ),
        Verdict.WITNESS,
        "not_linearizable",
        "FC2",
    ),
    (
        "lin_program_order_only",
        "linearizable",
        hist(
            ev("a", "WRITE", key="x", value=1, span="a0"),
            ev("b", "READ", key="x", value=1, span="b0"),
        ),
        Verdict.INSUFFICIENT_HB,
        None,
        None,
    ),
    (
        "lin_single_agent_legal",
        "linearizable",
        hist(
            ev("a", "WRITE", value=7, span="a0"),
            ev("a", "READ", value=7, span="a1"),
            ev("a", "WRITE", value=8, span="a2"),
            ev("a", "READ", value=8, span="a3"),
        ),
        Verdict.PASS,
        None,
        None,
    ),
]


@pytest.mark.parametrize("name,spec,h,verdict,kind,mast", CASES, ids=[c[0] for c in CASES])
def test_golden(name, spec, h, verdict, kind, mast):
    r = check(h, spec)
    assert r.verdict is verdict, f"{name}: {r}"
    if kind is not None:
        assert r.violation is not None and r.violation.kind == kind, f"{name}: {r.violation}"
    if mast is not None:
        assert r.violation.mast_id == mast, f"{name}: MAST {r.violation.mast_id}"


def test_golden_count():
    assert len(CASES) >= 15  # architecture: 15-20 golden cases
