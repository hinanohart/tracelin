"""Adapter: OpenTelemetry GenAI spans -> a tracelin ``History``.

OTel's GenAI semantic conventions describe *spans* (``gen_ai.*`` attributes) but
have no standard notion of "a write to shared agent state".  tracelin therefore
reads an explicit, documented convention layered on top of ordinary spans:

    attribute                 meaning
    ------------------------- ------------------------------------------------
    tracelin.op_type          one of OpType (READ/WRITE/INC/ASSIGN/...)
    tracelin.object_key       the shared object / task id the op concerns
    tracelin.value            written value / read return / target state
    tracelin.object_type      register | counter | map   (default register)
    tracelin.subkey           map sub-key (for object_type=map)

Agent identity falls back ``tracelin.agent_id`` -> ``gen_ai.agent.name`` ->
``gen_ai.system`` -> ``service.name``.  Happens-before comes from each span's
``parent_span_id`` and ``links`` (a list of span ids) — never from timestamps.
Spans without ``tracelin.op_type`` are ignored (they are not state operations).
"""

from __future__ import annotations

from typing import Any

from ..history import Event, History, OpType


def from_spans(spans: list[dict[str, Any]]) -> History:
    """Convert a list of OTel-shaped span dicts into a History."""
    events: list[Event] = []
    for span in spans:
        attrs = span.get("attributes", {})
        op_raw = attrs.get("tracelin.op_type")
        if op_raw is None:
            continue  # not a tracelin state operation
        events.append(
            Event(
                agent_id=_agent_of(attrs),
                op_type=OpType(op_raw),
                object_key=attrs.get("tracelin.object_key"),
                value=attrs.get("tracelin.value", _UNSET),
                span_id=span.get("span_id") or "",
                parent_span_id=span.get("parent_span_id"),
                links=tuple(span.get("links", ())),
                ts=span.get("start_time"),
                object_type=attrs.get("tracelin.object_type", "register"),
                meta=_meta_of(span, attrs),
            )
        )
    return History(events)


_UNSET = None


def _agent_of(attrs: dict[str, Any]) -> str:
    for k in ("tracelin.agent_id", "gen_ai.agent.name", "gen_ai.system", "service.name"):
        if attrs.get(k):
            return str(attrs[k])
    return "unknown"


def _meta_of(span: dict[str, Any], attrs: dict[str, Any]) -> dict[str, Any]:
    meta: dict[str, Any] = {}
    if "tracelin.subkey" in attrs:
        meta["subkey"] = attrs["tracelin.subkey"]
    if "tracelin.merge" in attrs:
        meta["merge"] = attrs["tracelin.merge"]
    if "name" in span:
        meta["span_name"] = span["name"]
    return meta
