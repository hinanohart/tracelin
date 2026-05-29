"""Adapter: a raw LangGraph fan-out trace record -> a tracelin ``History``.

The modelling follows LangGraph's channel semantics faithfully:

* **No reducer** — the state key is a ``LastValue`` channel, i.e. a *register*
  that admits one write per superstep.  Each node's write becomes a ``WRITE``
  event on a ``register`` object with no declared merge.  Two nodes in the same
  superstep therefore produce two happens-before-concurrent register writes —
  exactly the write-write race LangGraph itself rejects with
  ``InvalidUpdateError``, and what ``a2a_lifecycle`` flags structurally.

* **With a reducer** — the channel aggregates, so we model the developers'
  intent (each node increments) as an ``INC`` on a ``counter`` object carrying
  ``meta['merge'] = <reducer name>``.  The reducer's committed result becomes a
  final ``READ`` (by ``__final__``) that happens-after both increments.  A
  lossy reducer (last-writer-wins) yields a committed value below the number of
  increments, which ``linearizable`` reports as a lost update; a correct
  reducer (``operator.add``) yields a value consistent with the spec (PASS).

Happens-before is encoded with span ids: a ``__system__`` init write is the
common ancestor of both nodes (so they share causal history but are concurrent
with each other), and the final read links to both node writes.
"""

from __future__ import annotations

from typing import Any

from ..history import Event, History, OpType


def from_raw(raw: dict[str, Any]) -> History:
    """Convert one raw LangGraph run record into a History."""
    reducer = raw.get("reducer", "none")
    nodes = raw.get("nodes", [])
    observed_final = raw.get("observed_final") or {}
    initial = raw.get("initial", {})

    events: list[Event] = []
    # the keys touched in this run
    keys = sorted({k for n in nodes for k in n.get("write", {})})

    # __system__ init writes (common causal ancestor)
    for key in keys:
        events.append(
            Event(
                agent_id="__system__",
                op_type=OpType.WRITE,
                object_key=key,
                value=initial.get(key, 0),
                span_id=f"init:{key}",
                parent_span_id=None,
                object_type="counter" if reducer != "none" else "register",
                meta=_merge_meta(reducer),
            )
        )

    node_write_spans: dict[str, list[str]] = {k: [] for k in keys}
    for n in nodes:
        agent = n["agent"]
        for key, wval in n.get("write", {}).items():
            span = f"{agent}:{key}"
            if reducer == "none":
                # register write-write (the race)
                events.append(
                    Event(
                        agent_id=agent,
                        op_type=OpType.WRITE,
                        object_key=key,
                        value=wval,
                        span_id=span,
                        parent_span_id=f"init:{key}",
                        object_type="register",
                    )
                )
            else:
                # increment intent on a counter with a declared (possibly lossy) merge
                events.append(
                    Event(
                        agent_id=agent,
                        op_type=OpType.INC,
                        object_key=key,
                        value=None,
                        span_id=span,
                        parent_span_id=f"init:{key}",
                        object_type="counter",
                        meta=_merge_meta(reducer),
                    )
                )
            node_write_spans[key].append(span)

    # committed value as a final READ that happens-after both node writes
    if reducer != "none" and observed_final:
        for key, val in observed_final.items():
            if key not in node_write_spans:
                continue
            events.append(
                Event(
                    agent_id="__final__",
                    op_type=OpType.READ,
                    object_key=key,
                    value=val,
                    span_id=f"final:{key}",
                    parent_span_id=node_write_spans[key][0]
                    if node_write_spans[key]
                    else f"init:{key}",
                    links=tuple(node_write_spans[key]),
                    object_type="counter",
                    meta=_merge_meta(reducer),
                )
            )
    return History(events)


def _merge_meta(reducer: str) -> dict[str, Any]:
    return {"merge": reducer} if reducer and reducer != "none" else {}
