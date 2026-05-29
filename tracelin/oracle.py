"""Brute-force reference linearizability checker — the differential oracle.

This is intentionally the dumbest correct thing: enumerate every linear
extension of the happens-before partial order and test it against the
sequential spec.  It is exponential, so it is capped at a small number of
operations and used *only* in tests as the ground truth that the real engine
(:mod:`tracelin.specs.linearizable`) must agree with on every generated case.

Keeping a separate, obviously-correct implementation is how we earn confidence
that the optimised Wing–Gong search has no soundness bug.
"""

from __future__ import annotations

from .hb import HappensBefore
from .history import Event
from .objects import SequentialSpec, is_legal_sequential

ORACLE_MAX_OPS = 8


class OracleTooLarge(Exception):
    """Raised when an object's op count exceeds :data:`ORACLE_MAX_OPS`."""


def _linear_extensions(events: list[Event], hb: HappensBefore):
    """Yield every ordering of ``events`` consistent with happens-before."""
    n = len(events)
    # precompute predecessor counts within this set
    idx = {e.span_id: i for i, e in enumerate(events)}
    before = [[False] * n for _ in range(n)]
    for i, a in enumerate(events):
        for j, b in enumerate(events):
            if i != j and hb.happens_before(a, b):
                before[i][j] = True  # a must precede b

    placed = [False] * n
    order: list[Event] = []

    def ready(j: int) -> bool:
        # all predecessors of j placed?
        for i in range(n):
            if before[i][j] and not placed[i]:
                return False
        return True

    def backtrack():
        if len(order) == n:
            yield list(order)
            return
        for j in range(n):
            if not placed[j] and ready(j):
                placed[j] = True
                order.append(events[j])
                yield from backtrack()
                order.pop()
                placed[j] = False

    _ = idx  # idx kept for readability/debugging
    yield from backtrack()


def oracle_linearizable(events: list[Event], hb: HappensBefore, spec: SequentialSpec) -> bool:
    """True iff some happens-before-respecting ordering is legal for ``spec``."""
    if len(events) > ORACLE_MAX_OPS:
        raise OracleTooLarge(f"{len(events)} ops > ORACLE_MAX_OPS={ORACLE_MAX_OPS}")
    for ext in _linear_extensions(events, hb):
        if is_legal_sequential(ext, spec):
            return True
    return False
