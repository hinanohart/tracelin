"""Adapters: langgraph raw records and OTel GenAI spans -> History."""

from tracelin import check
from tracelin.adapters import langgraph as lg
from tracelin.adapters import otel_genai as otel
from tracelin.history import OpType
from tracelin.verdict import Verdict


def _raw(reducer, final):
    return {
        "label": "t",
        "reducer": reducer,
        "initial": {"counter": 0},
        "nodes": [
            {"agent": "agent_a", "read": {"counter": 0}, "write": {"counter": 1}},
            {"agent": "agent_b", "read": {"counter": 0}, "write": {"counter": 1}},
        ],
        "observed_final": final,
    }


def test_langgraph_noreducer_makes_register_writes():
    h = lg.from_raw(_raw("none", None))
    writes = [e for e in h.events if e.op_type is OpType.WRITE and e.agent_id != "__system__"]
    assert len(writes) == 2
    assert all(e.object_type == "register" for e in writes)
    assert check(h, "a2a_lifecycle").verdict is Verdict.WITNESS


def test_langgraph_lww_makes_counter_incs_with_final_read():
    h = lg.from_raw(_raw("lww", {"counter": 1}))
    incs = [e for e in h.events if e.op_type is OpType.INC]
    finals = [e for e in h.events if e.agent_id == "__final__"]
    assert len(incs) == 2 and len(finals) == 1
    assert all(e.meta.get("merge") == "lww" for e in incs)
    assert check(h, "linearizable").verdict is Verdict.WITNESS


def test_langgraph_add_reducer_passes():
    h = lg.from_raw(_raw("add", {"counter": 2}))
    assert check(h, "linearizable").verdict is Verdict.PASS
    assert check(h, "a2a_lifecycle").verdict is Verdict.PASS


def test_otel_genai_parses_tracelin_attrs():
    spans = [
        {
            "span_id": "s0",
            "parent_span_id": None,
            "attributes": {
                "tracelin.op_type": "WRITE",
                "tracelin.object_key": "x",
                "tracelin.value": 1,
                "gen_ai.agent.name": "writer",
            },
        },
        {
            "span_id": "s1",
            "parent_span_id": "s0",
            "attributes": {
                "tracelin.op_type": "READ",
                "tracelin.object_key": "x",
                "tracelin.value": 1,
                "tracelin.agent_id": "reader",
            },
        },
        {"span_id": "s2", "attributes": {"gen_ai.operation.name": "chat"}},  # ignored
    ]
    h = otel.from_spans(spans)
    assert len(h.events) == 2
    assert h.events[0].agent_id == "writer"
    assert h.events[1].agent_id == "reader"
    assert check(h, "linearizable").verdict is Verdict.PASS


def test_otel_map_subkey_carried():
    spans = [
        {
            "span_id": "s0",
            "attributes": {
                "tracelin.op_type": "WRITE",
                "tracelin.object_key": "m",
                "tracelin.value": 1,
                "tracelin.object_type": "map",
                "tracelin.subkey": "k1",
                "tracelin.agent_id": "a",
            },
        },
    ]
    h = otel.from_spans(spans)
    assert h.events[0].map_subkey() == "k1"
