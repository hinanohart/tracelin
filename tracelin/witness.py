"""Witness minimisation: shrink a failing history to a 1-minimal sub-history.

Given a predicate that reports whether a sub-history *still exhibits the same
violation*, we repeatedly drop single events as long as the violation survives,
to a fixpoint.  The result is **1-minimal**: removing any single remaining event
makes the check pass.  (We claim local, not global, minimality — see README.)

Happens-before is recomputed for every candidate sub-history, so an event that
is only kept because it carries a causal edge between two surviving operations
is retained automatically: dropping it would change the order and the predicate
would no longer hold.
"""

from __future__ import annotations

from collections.abc import Callable

from .history import History

# predicate: given a sub-history, return True iff the target violation persists.
Predicate = Callable[[History], bool]


def minimize(history: History, predicate: Predicate) -> list[str]:
    """Return span ids of a 1-minimal sub-history that still fails ``predicate``.

    Assumes ``predicate(history)`` is already True.
    """
    order = [e.span_id for e in history.events]  # stable display order
    current: set[str] = set(order)

    changed = True
    while changed:
        changed = False
        for span in list(current):
            candidate = current - {span}
            if not candidate:
                continue
            if predicate(history.subhistory(candidate)):
                current = candidate
                changed = True
    return [s for s in order if s in current]  # type: ignore[misc]
