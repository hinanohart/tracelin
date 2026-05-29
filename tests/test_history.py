"""History / Event normalisation."""

import pytest
from tracelin.history import Event, History, OpType


def test_span_ids_autoassigned_per_agent():
    h = History([Event("a", OpType.READ), Event("a", OpType.WRITE), Event("b", OpType.READ)])
    assert [e.span_id for e in h.events] == ["a#0", "a#1", "b#0"]


def test_duplicate_span_id_rejected():
    with pytest.raises(ValueError, match="duplicate span_id"):
        History([Event("a", OpType.READ, span_id="s"), Event("b", OpType.WRITE, span_id="s")])


def test_unknown_object_type_rejected():
    with pytest.raises(ValueError, match="unknown object_type"):
        History([Event("a", OpType.READ, object_type="bag")])


def test_indexes_by_agent_and_object():
    h = History(
        [
            Event("a", OpType.WRITE, object_key="x"),
            Event("b", OpType.READ, object_key="x"),
            Event("a", OpType.READ, object_key="y"),
        ]
    )
    assert set(h.by_agent) == {"a", "b"}
    assert set(h.by_object) == {"x", "y"}
    assert len(h.by_object["x"]) == 2


def test_program_order_pred():
    e0 = Event("a", OpType.READ)
    e1 = Event("a", OpType.WRITE)
    h = History([e0, e1, Event("b", OpType.READ)])
    assert h.program_order_pred(e1) is e0
    assert h.program_order_pred(e0) is None


def test_records_roundtrip():
    h = History(
        [
            Event("a", OpType.WRITE, object_key="x", value=1, object_type="counter"),
            Event("b", OpType.READ, object_key="x", value=1, object_type="counter"),
        ]
    )
    recs = h.to_records()
    h2 = History.from_records(recs)
    assert h2.to_records() == recs


def test_op_type_string_coercion():
    e = Event("a", "WRITE")  # type: ignore[arg-type]
    assert e.op_type is OpType.WRITE


def test_subhistory_preserves_span_ids():
    h = History([Event("a", OpType.READ, span_id="s0"), Event("b", OpType.WRITE, span_id="s1")])
    sub = h.subhistory({"s0"})
    assert [e.span_id for e in sub.events] == ["s0"]
