"""Shared result types: the four-valued verdict and the violation record.

These live in their own module so specs, the witness extractor, and the engine
can share them without import cycles.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Verdict(str, Enum):
    """The four outcomes of a check.

    ``PASS`` and ``WITNESS`` are sound conclusions.  ``INSUFFICIENT_HB`` is a
    *refusal* (the order is too weak to underwrite a sound PASS), and
    ``UNKNOWN`` means a resource cap was hit.  Neither refusal nor unknown is
    ever silently turned into PASS — that is the whole point of having four
    values instead of a boolean.
    """

    PASS = "PASS"
    WITNESS = "Witness"
    INSUFFICIENT_HB = "INSUFFICIENT_HB"
    UNKNOWN = "UNKNOWN"


@dataclass
class Violation:
    """A concrete, reproducible rule break."""

    kind: str  # e.g. "concurrent_write_race", "illegal_transition"
    detail: str
    span_ids: list[str] = field(default_factory=list)
    object_key: str | None = None
    mast_id: str = "UNMAPPED"

    def __str__(self) -> str:
        loc = f" on {self.object_key!r}" if self.object_key else ""
        return f"[{self.kind}{loc}] {self.detail} (events: {', '.join(self.span_ids)}; MAST {self.mast_id})"


@dataclass
class CheckResult:
    """What :func:`tracelin.engine.check` returns."""

    verdict: Verdict
    spec: str
    violation: Violation | None = None
    witness_spans: list[str] = field(default_factory=list)
    reason: str = ""

    @property
    def ok(self) -> bool:
        return self.verdict is Verdict.PASS

    @property
    def failed(self) -> bool:
        return self.verdict is Verdict.WITNESS

    def __str__(self) -> str:
        if self.violation is not None:
            return f"{self.verdict.value} ({self.spec}): {self.violation}"
        extra = f" — {self.reason}" if self.reason else ""
        return f"{self.verdict.value} ({self.spec}){extra}"
