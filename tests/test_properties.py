"""Four invariants tracelin must satisfy (property-based)."""

from hypothesis import given, settings
from hypothesis import strategies as st
from tracelin import check
from tracelin.history import Event, History, OpType
from tracelin.verdict import Verdict


# --- Property 1: a legal totally-ordered (single-agent) history linearizes ----
@st.composite
def legal_register_run(draw):
    n = draw(st.integers(min_value=1, max_value=7))
    events = []
    cur = None
    for i in range(n):
        if draw(st.booleans()) or cur is None:
            cur = draw(st.integers(min_value=0, max_value=3))
            events.append(Event("a", OpType.WRITE, "x", cur, span_id=f"e{i}"))
        else:
            events.append(Event("a", OpType.READ, "x", cur, span_id=f"e{i}"))
    return History(events)


@given(legal_register_run())
@settings(max_examples=150, deadline=None)
def test_prop1_serial_legal_is_linearizable(h):
    assert check(h, "linearizable").verdict is Verdict.PASS


# --- Property 2: adding a happens-before edge never turns a Witness into PASS --
def test_prop2_added_edge_never_fixes_violation():
    base = History(
        [
            Event("a", OpType.WRITE, "x", 0, span_id="a0"),
            Event("a", OpType.WRITE, "x", 1, span_id="a1"),
            Event("a", OpType.READ, "x", 0, span_id="a2"),  # stale read
        ]
    )
    assert check(base, "linearizable").verdict is Verdict.WITNESS
    # add an extra (acyclic) edge; more constraints cannot create a legal order
    enriched = History(
        [
            Event("a", OpType.WRITE, "x", 0, span_id="a0"),
            Event("a", OpType.WRITE, "x", 1, span_id="a1"),
            Event("a", OpType.READ, "x", 0, span_id="a2", links=("a0",)),
        ]
    )
    assert check(enriched, "linearizable").verdict is Verdict.WITNESS


# --- Property 3: a reported witness, re-checked alone, reproduces the violation
def test_prop3_witness_reproduces():
    h = History(
        [
            Event("s", OpType.WRITE, "x", 0, span_id="i", object_type="counter"),
            Event("a", OpType.INC, "x", span_id="a0", parent_span_id="i", object_type="counter"),
            Event("b", OpType.INC, "x", span_id="b0", parent_span_id="i", object_type="counter"),
            Event(
                "f",
                OpType.READ,
                "x",
                1,
                span_id="f0",
                parent_span_id="a0",
                links=("a0", "b0"),
                object_type="counter",
            ),
        ]
    )
    r = check(h, "linearizable")
    assert r.verdict is Verdict.WITNESS
    sub = h.subhistory(set(r.witness_spans))
    assert check(sub, "linearizable").verdict is Verdict.WITNESS


# --- Property 4: the reported witness is 1-minimal ----------------------------
def test_prop4_witness_one_minimal():
    h = History(
        [
            Event("s", OpType.WRITE, "x", 0, span_id="i", object_type="counter"),
            Event("a", OpType.INC, "x", span_id="a0", parent_span_id="i", object_type="counter"),
            Event("b", OpType.INC, "x", span_id="b0", parent_span_id="i", object_type="counter"),
            Event(
                "f",
                OpType.READ,
                "x",
                1,
                span_id="f0",
                parent_span_id="a0",
                links=("a0", "b0"),
                object_type="counter",
            ),
        ]
    )
    r = check(h, "linearizable")
    w = set(r.witness_spans)
    for s in list(w):
        sub = h.subhistory(w - {s})
        assert check(sub, "linearizable").verdict is not Verdict.WITNESS
