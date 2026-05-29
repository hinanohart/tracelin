"""tracelin — a conformance & race linter for recorded multi-agent traces.

Feed it a recorded multi-agent execution (OTel GenAI spans, a LangGraph trace,
A2A task events, ...) and it decides whether the trace conforms to a declared
spec, returning a *sound* four-valued verdict and, on failure, a 1-minimal
counter-example sub-history annotated with the closest MAST failure-mode
category.

It is a falsifier on *recorded* traces: every reported failure is real and
reproducible; it does not prevent races at runtime and cannot see concurrency
that the trace did not record.

Quick start::

    from tracelin import History, check
    history = History.from_records(rows)      # or use tracelin.adapters
    result = check(history, "a2a_lifecycle")
    print(result)                             # PASS / Witness / INSUFFICIENT_HB / UNKNOWN
"""

from .engine import check
from .history import Event, History, OpType
from .verdict import CheckResult, Verdict, Violation

__version__ = "0.1.0a3"

__all__ = [
    "check",
    "History",
    "Event",
    "OpType",
    "Verdict",
    "Violation",
    "CheckResult",
    "__version__",
]
