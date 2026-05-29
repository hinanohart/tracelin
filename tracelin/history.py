"""History and Event: the normalised input form for every tracelin check.

A :class:`History` is an ordered collection of :class:`Event` objects extracted
from a recorded multi-agent trace (OTel GenAI spans, LangGraph state updates,
A2A task events, ...).  Adapters live in :mod:`tracelin.adapters`; everything
downstream (happens-before reconstruction, the specs, the engine) consumes only
``History`` so the core never depends on any agent framework.

Design note (the hardest part of the system, solved first): a sound verdict can
only be as trustworthy as the partial order we reconstruct over events.  Events
therefore carry *explicit* causal hints (``parent_span_id`` and ``links``) which
:mod:`tracelin.hb` turns into a happens-before DAG.  ``ts`` (wall-clock) is kept
but is only ever consulted in the degraded ``timestamp`` tier, which can never
yield a sound ``PASS`` (see :mod:`tracelin.hb` and :mod:`tracelin.engine`).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class OpType(str, Enum):
    """Operation kinds an event may represent.

    The first three are *data-plane* operations on a shared object and feed the
    ``linearizable`` spec.  The rest are *control-plane* operations on the agent
    lifecycle and feed ``a2a_lifecycle``.  ``object_type`` on the event selects
    the sequential specification used for the data-plane ops.
    """

    READ = "READ"
    WRITE = "WRITE"
    INC = "INC"  # counter increment (read-modify-write modelled as one op)

    ASSIGN = "ASSIGN"  # a subtask is assigned to an agent
    DELEGATE = "DELEGATE"  # an agent hands a subtask to another
    TOOL_CALL = "TOOL_CALL"
    TOOL_RESULT = "TOOL_RESULT"
    STATE_TRANSITION = "STATE_TRANSITION"  # A2A task FSM transition
    CONSENT = "CONSENT"
    TERMINAL = "TERMINAL"  # task reached a terminal state


# Operations that touch shared mutable state (data-plane).
DATA_OPS = frozenset({OpType.READ, OpType.WRITE, OpType.INC})


@dataclass
class Event:
    """A single recorded operation.

    Attributes:
        agent_id: the actor that performed the operation.
        op_type: see :class:`OpType`.
        object_key: the shared object / task id the op concerns (``None`` for
            ops that are not about a specific object).
        value: written value, read return value, target state name, etc.
        span_id: unique id of this event; auto-filled by :class:`History` if
            omitted.
        parent_span_id: explicit happens-before predecessor (e.g. OTel parent
            span, the cause of this event).  ``None`` for roots.
        links: additional explicit happens-before predecessors (e.g. OTel span
            links / message receipts).
        ts: wall-clock timestamp; *advisory only* — never used for a sound PASS.
        object_type: sequential-spec selector for data-plane ops, one of
            ``register`` | ``counter`` | ``map``.
        meta: free-form provenance (framework, raised error, map sub-key, ...).
    """

    agent_id: str
    op_type: OpType
    object_key: str | None = None
    value: Any = None
    span_id: str = ""  # empty == "assign me"; History fills it deterministically
    parent_span_id: str | None = None
    links: tuple[str, ...] = ()
    ts: float | None = None
    object_type: str = "register"
    meta: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if isinstance(self.op_type, str) and not isinstance(self.op_type, OpType):
            self.op_type = OpType(self.op_type)
        self.links = tuple(self.links)

    @property
    def is_data_op(self) -> bool:
        return self.op_type in DATA_OPS

    def map_subkey(self) -> str | None:
        """For ``map`` objects, the sub-key this op addresses (per-key reduction)."""
        return self.meta.get("subkey")


_VALID_OBJECT_TYPES = frozenset({"register", "counter", "map"})


class History:
    """An ordered list of events plus the indexes the rest of the system needs.

    Span ids are filled in deterministically when missing (``<agent>#<n>``) so
    that two events are never confused and witnesses can name events stably.
    Program order (per-agent sequence) is derived from input order; explicit
    causal edges come from ``parent_span_id`` / ``links``.
    """

    def __init__(self, events: list[Event]):
        self.events: list[Event] = events
        self._assign_span_ids()
        self._validate()
        # indexes
        self.by_span: dict[str, Event] = {e.span_id: e for e in events}  # type: ignore[misc]
        self.by_agent: dict[str, list[Event]] = {}
        self.by_object: dict[str, list[Event]] = {}
        for e in events:
            self.by_agent.setdefault(e.agent_id, []).append(e)
            if e.object_key is not None:
                self.by_object.setdefault(e.object_key, []).append(e)

    def _assign_span_ids(self) -> None:
        counters: dict[str, int] = {}
        seen: set[str] = set()
        for e in self.events:
            if not e.span_id:
                n = counters.get(e.agent_id, 0)
                e.span_id = f"{e.agent_id}#{n}"
                counters[e.agent_id] = n + 1
            if e.span_id in seen:
                raise ValueError(f"duplicate span_id: {e.span_id!r}")
            seen.add(e.span_id)

    def _validate(self) -> None:
        for e in self.events:
            if e.object_type not in _VALID_OBJECT_TYPES:
                raise ValueError(
                    f"unknown object_type {e.object_type!r} (span {e.span_id}); "
                    f"expected one of {sorted(_VALID_OBJECT_TYPES)}"
                )
            if e.op_type in DATA_OPS and e.object_key is None:
                # A data-plane op with no object_key would be dropped from the
                # by_object index below and silently skipped by the linearizable
                # check — a possible false PASS.  Reject it instead of lying.
                raise ValueError(
                    f"data-plane op {e.op_type.value} (span {e.span_id}) has no "
                    f"object_key; a READ/WRITE/INC must name the shared object it "
                    f"concerns"
                )

    # -- program order -----------------------------------------------------
    def program_order_pred(self, event: Event) -> Event | None:
        """The previous event of the same agent in input order, if any."""
        siblings = self.by_agent[event.agent_id]
        i = siblings.index(event)
        return siblings[i - 1] if i > 0 else None

    def object_keys(self) -> list[str]:
        return list(self.by_object.keys())

    def __len__(self) -> int:
        return len(self.events)

    def __iter__(self):
        return iter(self.events)

    def subhistory(self, span_ids: set[str]) -> History:
        """A new History restricted to the given span ids (witness extraction)."""
        kept = [e for e in self.events if e.span_id in span_ids]
        # deep-ish copy so span-id reassignment / index rebuild is clean
        import copy

        return History([copy.copy(e) for e in kept])

    # -- (de)serialisation -------------------------------------------------
    @classmethod
    def from_records(cls, records: list[dict[str, Any]]) -> History:
        """Build from a list of plain dicts (one JSONL row per event)."""
        events = []
        for r in records:
            events.append(
                Event(
                    agent_id=r["agent_id"],
                    op_type=OpType(r["op_type"]),
                    object_key=r.get("object_key"),
                    value=r.get("value"),
                    span_id=r.get("span_id") or "",
                    parent_span_id=r.get("parent_span_id"),
                    links=tuple(r.get("links", ())),
                    ts=r.get("ts"),
                    object_type=r.get("object_type", "register"),
                    meta=r.get("meta", {}),
                )
            )
        return cls(events)

    def to_records(self) -> list[dict[str, Any]]:
        out = []
        for e in self.events:
            out.append(
                {
                    "agent_id": e.agent_id,
                    "op_type": e.op_type.value,
                    "object_key": e.object_key,
                    "value": e.value,
                    "span_id": e.span_id,
                    "parent_span_id": e.parent_span_id,
                    "links": list(e.links),
                    "ts": e.ts,
                    "object_type": e.object_type,
                    "meta": e.meta,
                }
            )
        return out
