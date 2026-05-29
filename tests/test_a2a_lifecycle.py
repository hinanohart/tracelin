"""a2a_lifecycle structural rules."""

from tracelin.hb import HappensBefore
from tracelin.specs import a2a_lifecycle

from conftest import ev, hist


def _run(h):
    hb = HappensBefore(h)
    return a2a_lifecycle.check(h, hb, trust_concurrency=hb.trustworthy())


def test_legal_transition_sequence_passes():
    h = hist(
        ev("orch", "STATE_TRANSITION", key="t1", value="submitted", span="s0"),
        ev("orch", "STATE_TRANSITION", key="t1", value="working", span="s1"),
        ev("orch", "STATE_TRANSITION", key="t1", value="completed", span="s2"),
    )
    assert _run(h) == []


def test_illegal_transition_flagged():
    h = hist(
        ev("orch", "STATE_TRANSITION", key="t1", value="submitted", span="s0"),
        ev(
            "orch", "STATE_TRANSITION", key="t1", value="completed", span="s1"
        ),  # skip working? legal? no
    )
    # submitted -> completed is NOT a legal edge
    vs = _run(h)
    assert any(v.kind == "illegal_transition" for v in vs)


def test_non_entry_first_state_flagged():
    h = hist(ev("orch", "STATE_TRANSITION", key="t1", value="completed", span="s0"))
    vs = _run(h)
    assert any(v.kind == "illegal_transition" for v in vs)


def test_act_after_terminal_flagged():
    h = hist(
        ev("orch", "STATE_TRANSITION", key="t1", value="submitted", span="s0"),
        ev("orch", "STATE_TRANSITION", key="t1", value="completed", span="s1"),
        ev("worker", "TOOL_CALL", key="t1", span="s2", parent="s1"),  # acts after terminal
    )
    vs = _run(h)
    assert any(v.kind == "act_after_terminal" for v in vs)


def test_double_assignee_flagged():
    # shared ancestor "root" gives a cross-agent causal edge (causal tier), so the
    # two assigns are trustworthy-concurrent rather than program-order-unknown.
    h = hist(
        ev("sys", "STATE_TRANSITION", key="sub1", value="submitted", span="root"),
        ev("orch", "ASSIGN", key="sub1", value="alice", span="s0", parent="root"),
        ev("orch2", "ASSIGN", key="sub1", value="bob", span="s1", parent="root"),
    )
    vs = _run(h)
    assert any(v.kind == "double_assignee" for v in vs)


def test_concurrent_write_race_flagged():
    h = hist(
        ev("sys", "WRITE", key="x", value=0, span="i", object_type="register"),
        ev("a", "WRITE", key="x", value=1, span="a0", parent="i", object_type="register"),
        ev("b", "WRITE", key="x", value=2, span="b0", parent="i", object_type="register"),
    )
    vs = _run(h)
    assert any(v.kind == "concurrent_write_race" for v in vs)


def test_declared_merge_suppresses_race():
    h = hist(
        ev("a", "WRITE", key="x", value=1, span="a0", object_type="register", merge="add"),
        ev("b", "WRITE", key="x", value=2, span="b0", object_type="register", merge="add"),
    )
    vs = _run(h)
    assert not any(v.kind == "concurrent_write_race" for v in vs)
