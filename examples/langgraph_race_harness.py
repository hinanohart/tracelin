"""Reproduce, with a real LangGraph run, the concurrent shared-state phenomena
that S-Bus (arXiv:2605.17076) calls "Structural Race Conditions", and emit them
as RAW langgraph-shaped trace records (one JSON object per run).

This is a producer of *raw* traces; turning a raw record into a tracelin
``History`` is the job of :mod:`tracelin.adapters.langgraph` — keeping the two
separate is what lets the adapter be tested honestly.

Three runs:
  T1  no reducer            -> LangGraph raises InvalidUpdateError
                               (LastValue channel = a register; two concurrent
                               writes = a write-write race).
  T2  last-writer-wins      -> lost update: two increments, final counter = 1.
  T3  operator.add          -> correct merge: final counter = 2.

Run:  python examples/langgraph_race_harness.py raw_traces.jsonl
"""

import json
import operator
import sys
from typing import Annotated, TypedDict

from langgraph.errors import InvalidUpdateError
from langgraph.graph import END, START, StateGraph


def make_node(name, trace):
    def node(state):
        v = state["counter"]
        trace.append({"agent": name, "read": {"counter": v}, "write": {"counter": v + 1}})
        return {"counter": v + 1}

    return node


def build(reducer):
    if reducer is None:
        State = TypedDict("State", {"counter": int})
    else:
        State = TypedDict("State", {"counter": Annotated[int, reducer]})
    trace = []
    g = StateGraph(State)
    g.add_node("agent_a", make_node("agent_a", trace))
    g.add_node("agent_b", make_node("agent_b", trace))
    g.add_edge(START, "agent_a")  # fan-out: both run in the SAME superstep
    g.add_edge(START, "agent_b")
    g.add_edge("agent_a", END)
    g.add_edge("agent_b", END)
    return g.compile(), trace


def run(reducer, reducer_name, label):
    app, trace = build(reducer)
    raised = None
    final = None
    try:
        final = app.invoke({"counter": 0})
    except InvalidUpdateError as e:
        raised = "InvalidUpdateError: " + str(e).splitlines()[0]
    return {
        "label": label,
        "framework": "langgraph",
        "framework_version": _lg_version(),
        "reducer": reducer_name,
        "initial": {"counter": 0},
        "nodes": trace,  # per-node reads/writes, in execution order
        "superstep": 1,  # all nodes share one fan-out superstep
        "raised": raised,
        "observed_final": final,
    }


def _lg_version() -> str:
    import importlib.metadata as m

    return "langgraph==" + m.version("langgraph")


def main():
    runs = [
        run(None, "none", "T1_writewrite_noreducer"),
        run(lambda _old, new: new, "lww", "T2_lostupdate_lww"),
        run(operator.add, "add", "T3_correct_merge_add"),
    ]
    out_path = sys.argv[1] if len(sys.argv) > 1 else "raw_traces.jsonl"
    with open(out_path, "w") as f:
        for r in runs:
            f.write(json.dumps(r) + "\n")
    summary = {
        "T1_raised": bool(runs[0]["raised"]),
        "T1_both_writes_recovered": len(runs[0]["nodes"]) == 2,
        "T2_final": (runs[1]["observed_final"] or {}).get("counter"),
        "T3_final": (runs[2]["observed_final"] or {}).get("counter"),
        "written": out_path,
    }
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
