"""Map a detected violation to a MAST failure-mode category — honestly.

MAST (Multi-Agent System Failure Taxonomy, arXiv:2503.13657) catalogues 14
failure modes of multi-agent LLM systems in three categories.  tracelin detects
*structural / ordering* violations, which overlap with MAST's (LLM-reasoning
centric) taxonomy only partially.  We therefore map each violation kind to a
MAST **category** where the correspondence is defensible, and to ``UNMAPPED``
otherwise.  This is an advisory annotation, **not** a claim that tracelin
detects that MAST mode or covers the taxonomy (NON-CLAIM, see README).
"""

from __future__ import annotations

from .verdict import Violation

# The three MAST categories (the stable, well-established level of the taxonomy).
MAST_CATEGORIES = {
    "FC1": "Specification & system design",
    "FC2": "Inter-agent misalignment",
    "FC3": "Task verification & termination",
}

# Reference list of the 14 MAST modes, for documentation only (not asserted as
# detected). Verbatim category assignment per the taxonomy's three groups.
MAST_MODES_REFERENCE = {
    "FC1": [
        "disobey task specification",
        "disobey role specification",
        "step repetition",
        "loss of conversation history",
        "unaware of termination conditions",
    ],
    "FC2": [
        "conversation reset",
        "fail to ask for clarification",
        "task derailment",
        "information withholding",
        "ignored other agent's input",
        "reasoning-action mismatch",
    ],
    "FC3": [
        "premature termination",
        "no or incomplete verification",
        "incorrect verification",
    ],
}

# tracelin violation kind -> (MAST category or "UNMAPPED", honest note).
_KIND_TO_MAST: dict[str, tuple[str, str]] = {
    "illegal_transition": (
        "FC1",
        "violates the declared task lifecycle specification",
    ),
    "act_after_terminal": (
        "FC3",
        "action occurs after the task reached a terminal state",
    ),
    "double_assignee": (
        "FC2",
        "two agents concurrently own one subtask (coordination misalignment)",
    ),
    "concurrent_write_race": (
        "FC2",
        "closest category; MAST is LLM-reasoning-centric whereas this is a "
        "structural lost-update race — treat as advisory",
    ),
    "not_linearizable": (
        "FC2",
        "lost update / stale read on shared state (advisory; structural, not an "
        "LLM-reasoning mode)",
    ),
}


def annotate(violation: Violation) -> Violation:
    """Set ``violation.mast_id`` from the honest kind→category table."""
    cat, _note = _KIND_TO_MAST.get(violation.kind, ("UNMAPPED", ""))
    violation.mast_id = cat
    return violation


def note_for(violation: Violation) -> str:
    return _KIND_TO_MAST.get(violation.kind, ("UNMAPPED", ""))[1]
