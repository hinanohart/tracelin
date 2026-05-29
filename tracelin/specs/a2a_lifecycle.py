"""``a2a_lifecycle`` — the always-polynomial conformance layer (the headline).

Four structural rules over a single recorded trace, each decidable in time
polynomial in the trace size (DAG reachability + per-object pair scans).  None
of them needs to search linearisations, so they are always available and never
return ``UNKNOWN``:

1. **legal_transition** — A2A task state machine: every ``STATE_TRANSITION``
   follows a legal edge of the A2A lifecycle FSM (submitted/working/
   input-required/auth-required → terminal{completed,failed,canceled,rejected}).
2. **no_act_after_terminal** — once a task reaches a terminal state, no further
   event for that task may happen-after it.
3. **single_assignee** — a subtask is not concurrently ``ASSIGN``/``DELEGATE``-d
   to two different agents.
4. **concurrent_write_race** — two happens-before-concurrent writes to the same
   single-writer (``register``) object with no declared merge: the structural
   race condition S-Bus (arXiv:2605.17076) calls an SRC.  (Counters carry their
   own merge semantics and are judged by the ``linearizable`` spec instead.)

Returns a list of :class:`~tracelin.verdict.Violation`; the engine turns the
first (or a witness-minimised one) into a ``Witness`` verdict.  MAST annotation
is *not* set here: the engine calls :func:`tracelin.mast.annotate`, the single
source of truth, which maps each violation kind to a MAST **category** (FC1–FC3)
or ``UNMAPPED`` — tracelin deliberately does not claim mode-level MAST IDs.
"""

from __future__ import annotations

from ..hb import HappensBefore
from ..history import History, OpType
from ..verdict import Violation

# A2A task lifecycle FSM.  Keys are states; values are the states reachable in
# one transition.  Terminal states have no outgoing edges.
NON_TERMINAL = {"submitted", "working", "input-required", "auth-required"}
TERMINAL = {"completed", "failed", "canceled", "rejected"}
ALL_STATES = NON_TERMINAL | TERMINAL

TRANSITIONS: dict[str, set[str]] = {
    "submitted": {"working", "canceled", "rejected", "failed"},
    "working": {"input-required", "auth-required", "completed", "failed", "canceled"},
    "input-required": {"working", "canceled", "failed"},
    "auth-required": {"working", "canceled", "failed"},
    # terminal states: no outgoing edges
    "completed": set(),
    "failed": set(),
    "canceled": set(),
    "rejected": set(),
}

# Legal first observed state for a task (entry points).
ENTRY_STATES = {"submitted", "working"}

WRITE_OPS = {OpType.WRITE, OpType.INC}


def _has_declared_merge(events) -> bool:
    return any(e.meta.get("merge") for e in events)


def check(history: History, hb: HappensBefore, trust_concurrency: bool = True) -> list[Violation]:
    """Run the lifecycle rules.

    ``_check_transitions`` is tier-independent (per-task program order) and
    always runs.  The concurrency-dependent rules rely on happens-before
    concurrency, which is only sound when the order is trustworthy; the engine
    passes ``trust_concurrency=hb.trustworthy()`` and reports INSUFFICIENT_HB
    when they had to be skipped on a trace that contains concurrency-relevant
    operations.
    """
    violations: list[Violation] = []
    violations += _check_transitions(history, hb)
    if trust_concurrency:
        violations += _check_no_act_after_terminal(history, hb)
        violations += _check_single_assignee(history, hb)
        violations += _check_concurrent_write_race(history, hb)
    return violations


CONCURRENCY_RELEVANT_OPS = WRITE_OPS | {
    OpType.ASSIGN,
    OpType.DELEGATE,
    OpType.STATE_TRANSITION,
    OpType.TERMINAL,
}


def has_concurrency_relevant_ops(history: History) -> bool:
    """Whether skipping the concurrency rules could hide a real violation."""
    return any(e.op_type in CONCURRENCY_RELEVANT_OPS for e in history.events)


def _task_transitions(history: History):
    """Yield (task_key, [STATE_TRANSITION events in program order])."""
    by_task: dict[str, list] = {}
    for e in history.events:
        if e.op_type is OpType.STATE_TRANSITION and e.object_key is not None:
            by_task.setdefault(e.object_key, []).append(e)
    return by_task


def _check_transitions(history: History, hb: HappensBefore) -> list[Violation]:
    out: list[Violation] = []
    for task, evs in _task_transitions(history).items():
        prev_state: str | None = None
        for e in evs:
            to = e.value
            if to not in ALL_STATES:
                out.append(
                    Violation(
                        "illegal_transition",
                        f"unknown task state {to!r}",
                        [e.span_id],
                        task,
                    )
                )
                prev_state = to
                continue
            if prev_state is None:
                if to not in ENTRY_STATES:
                    out.append(
                        Violation(
                            "illegal_transition",
                            f"task entered at non-entry state {to!r}",
                            [e.span_id],
                            task,
                        )
                    )
            elif to not in TRANSITIONS.get(prev_state, set()):
                out.append(
                    Violation(
                        "illegal_transition",
                        f"illegal transition {prev_state!r} -> {to!r}",
                        [e.span_id],
                        task,
                    )
                )
            prev_state = to
    return out


def _check_no_act_after_terminal(history: History, hb: HappensBefore) -> list[Violation]:
    out: list[Violation] = []
    for task, evs in _task_transitions(history).items():
        terminal_evs = [e for e in evs if e.value in TERMINAL]
        if not terminal_evs:
            continue
        for term in terminal_evs:
            # any event on this task that happens-after the terminal transition
            for other in history.by_object.get(task, []):
                if other.span_id == term.span_id:
                    continue
                if hb.happens_before(term, other):
                    out.append(
                        Violation(
                            "act_after_terminal",
                            f"{other.op_type.value} happens-after terminal {term.value!r}",
                            [term.span_id, other.span_id],
                            task,
                        )
                    )
    return out


def _check_single_assignee(history: History, hb: HappensBefore) -> list[Violation]:
    out: list[Violation] = []
    for key, evs in history.by_object.items():
        assigns = [e for e in evs if e.op_type in (OpType.ASSIGN, OpType.DELEGATE)]
        # group by assignee (the value names the agent that gets the subtask)
        for i in range(len(assigns)):
            for j in range(i + 1, len(assigns)):
                a, b = assigns[i], assigns[j]
                if a.value != b.value and hb.concurrent(a, b):
                    out.append(
                        Violation(
                            "double_assignee",
                            f"subtask concurrently assigned to {a.value!r} and {b.value!r}",
                            [a.span_id, b.span_id],
                            key,
                        )
                    )
    return out


def _check_concurrent_write_race(history: History, hb: HappensBefore) -> list[Violation]:
    out: list[Violation] = []
    for key, evs in history.by_object.items():
        writes = [e for e in evs if e.op_type in WRITE_OPS and e.object_type == "register"]
        if _has_declared_merge(writes):
            continue  # concurrent writes here are intentional (declared merge)
        for i in range(len(writes)):
            for j in range(i + 1, len(writes)):
                a, b = writes[i], writes[j]
                if hb.concurrent(a, b):
                    out.append(
                        Violation(
                            "concurrent_write_race",
                            "two happens-before-concurrent writes to a "
                            "single-writer register with no declared merge "
                            "(structural race condition / lost update)",
                            [a.span_id, b.span_id],
                            key,
                        )
                    )
    return out
