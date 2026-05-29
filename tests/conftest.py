"""Shared test helpers."""

from __future__ import annotations

from tracelin.history import Event, History, OpType


def ev(
    agent: str,
    op: str,
    key: str | None = "x",
    value=None,
    span: str | None = None,
    parent: str | None = None,
    links: tuple[str, ...] = (),
    object_type: str = "register",
    **meta,
) -> Event:
    return Event(
        agent_id=agent,
        op_type=OpType(op),
        object_key=key,
        value=value,
        span_id=span,
        parent_span_id=parent,
        links=links,
        object_type=object_type,
        meta=meta,
    )


def hist(*events: Event) -> History:
    return History(list(events))
