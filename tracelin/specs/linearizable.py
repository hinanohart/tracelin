"""Linearizability check via a memoised Wing–Gong / Lowe search.

For point operations carrying a happens-before partial order, a history is
linearizable iff some linear extension of that order is legal for the object's
sequential spec.  Brute force (:mod:`tracelin.oracle`) enumerates every
extension; here we do the standard optimisation: depth-first search that, at
each step, tries every *ready* operation (all happens-before predecessors
already committed) as the next linearisation point, applying it to a running
reference state and back-tracking on a spec violation.  Memoising on
``(remaining-ops, state)`` collapses the many orderings that reach the same
configuration — the search cost is governed by the per-object concurrency
width, not the total number of operations.

Per-object compositionality (Herlihy–Wing locality): the engine calls this once
per ``object_key`` (and once per map sub-key); a history is linearizable iff
every object is.  Hard caps convert intractable instances to ``UNKNOWN`` rather
than guessing.

Complexity note: the fixed-process, single-register subcase is polynomial
(Gibbons & Korach, 1997); the general multi-object / unbounded-process case is
NP-complete, which is precisely why the search is bounded by hard caps that yield
``UNKNOWN`` instead of degrading into a guess.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from ..hb import HappensBefore
from ..history import Event
from ..objects import SequentialSpec, SpecViolation

LINEARIZABLE = "linearizable"
NOT_LINEARIZABLE = "not_linearizable"
UNKNOWN = "unknown"


@dataclass(frozen=True)
class Caps:
    """Resource ceilings; exceeding any yields ``UNKNOWN`` (never a guess)."""

    max_ops: int = 256
    max_concurrent_per_object: int = 14
    max_steps: int = 2_000_000
    timeout_s: float = 5.0


def concurrency_width(events: list[Event], hb: HappensBefore) -> int:
    """A cheap, conservative over-approximation of the per-object concurrency
    width (the size of the largest set of pairwise-concurrent ops).

    For each op it counts that op plus every op concurrent with it; because those
    neighbours need not be pairwise concurrent, the result is an upper bound on
    the true width, not the exact value.  That is deliberate: it is used only to
    gate the search (``> max_concurrent_per_object`` -> UNKNOWN), so over-counting
    can only make the gate fire *earlier* — never a wrong PASS or FAIL, just a
    conservative UNKNOWN.
    """
    width = 0
    for i, a in enumerate(events):
        grp = 1
        for j, b in enumerate(events):
            if i != j and hb.concurrent(a, b):
                grp += 1
        width = max(width, grp)
    return width


def check_object(
    events: list[Event],
    hb: HappensBefore,
    spec: SequentialSpec,
    caps: Caps | None = None,
) -> str:
    """Return LINEARIZABLE / NOT_LINEARIZABLE / UNKNOWN for one object's ops."""
    if caps is None:
        caps = Caps()
    n = len(events)
    if n == 0:
        return LINEARIZABLE
    if n > caps.max_ops:
        return UNKNOWN
    if concurrency_width(events, hb) > caps.max_concurrent_per_object:
        return UNKNOWN

    spans = [e.span_id for e in events]
    span_set = set(spans)
    by_span = {e.span_id: e for e in events}
    # predecessor map restricted to this object's ops
    preds_in: dict[str, frozenset[str]] = {}
    for e in events:
        ps = {o.span_id for o in events if o.span_id != e.span_id and hb.happens_before(o, e)}
        preds_in[e.span_id] = frozenset(ps)  # type: ignore[index]

    deadline = time.monotonic() + caps.timeout_s
    steps = [0]
    memo: set[tuple[frozenset[str], object]] = set()
    timed_out = [False]

    def ready(remaining: frozenset[str]) -> list[str]:
        placed = span_set - remaining
        return [s for s in remaining if preds_in[s] <= placed]

    def dfs(remaining: frozenset[str], state: object) -> bool:
        if not remaining:
            return True
        steps[0] += 1
        if steps[0] > caps.max_steps or time.monotonic() > deadline:
            timed_out[0] = True
            return False
        key = (remaining, state)  # scalar object states are directly hashable
        if key in memo:
            return False
        for s in ready(remaining):
            e = by_span[s]
            try:
                ns = spec.apply(state, e)
            except SpecViolation:
                continue
            if dfs(remaining - {s}, ns):
                return True
        memo.add(key)
        return False

    ok = dfs(frozenset(spans), spec.initial())  # type: ignore[arg-type]
    if ok:
        return LINEARIZABLE
    if timed_out[0]:
        return UNKNOWN
    return NOT_LINEARIZABLE
