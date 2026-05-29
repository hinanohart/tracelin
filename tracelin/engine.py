"""The engine: turn a History + a spec name into a sound four-valued verdict.

``check(history, spec)`` is the single public entry point.  It owns the rules
that keep verdicts honest:

* A *linearizability* witness is sound at any trust tier (fewer known edges only
  add candidate linearisations, so a violation under a weak order persists under
  any stronger one) and is always reported.  The *concurrency* rules of
  ``a2a_lifecycle`` (race / double-assignee / act-after-terminal) are the
  opposite — dropping an edge can fabricate apparent concurrency — so they are
  withheld on an untrusted order (reported ``INSUFFICIENT_HB``) and only emit a
  witness at the ``causal`` tier.  Either way, a witness that *is* emitted is sound.
* A "no violation found" result is reported ``PASS`` only when the happens-before
  order is trustworthy (``causal`` tier).  Otherwise it becomes
  ``INSUFFICIENT_HB`` — we refuse to claim PASS on an order we do not trust,
  which is how false PASSes are made structurally impossible.
* Resource-bounded searches that hit a cap return ``UNKNOWN`` (never a guess).

Per-object compositionality (Herlihy–Wing locality) is applied for
``linearizable``: each ``object_key`` (and each ``map`` sub-key) is checked
independently and the history is linearizable iff all objects are.
"""

from __future__ import annotations

from . import mast
from .hb import HappensBefore
from .history import DATA_OPS, Event, History
from .objects import spec_for
from .specs import a2a_lifecycle
from .specs import linearizable as lin
from .verdict import CheckResult, Verdict, Violation
from .witness import minimize

SPECS = ("a2a_lifecycle", "linearizable")


def check(
    history: History,
    spec: str = "a2a_lifecycle",
    *,
    caps: lin.Caps | None = None,
) -> CheckResult:
    if spec not in SPECS:
        raise ValueError(f"unknown spec {spec!r}; choose from {SPECS}")
    hb = HappensBefore(history)
    if spec == "a2a_lifecycle":
        return _check_a2a(history, hb)
    return _check_linearizable(history, hb, caps or lin.Caps())


# -- a2a_lifecycle ---------------------------------------------------------
def _check_a2a(history: History, hb: HappensBefore) -> CheckResult:
    trust = hb.trustworthy()
    violations = a2a_lifecycle.check(history, hb, trust_concurrency=trust)
    if violations:
        v = _pick(violations)
        mast.annotate(v)
        spans = minimize(history, _a2a_predicate(v))
        v.span_ids = [s for s in v.span_ids if s in spans] or v.span_ids
        return CheckResult(Verdict.WITNESS, "a2a_lifecycle", violation=v, witness_spans=spans)
    if not trust and a2a_lifecycle.has_concurrency_relevant_ops(history):
        return CheckResult(
            Verdict.INSUFFICIENT_HB,
            "a2a_lifecycle",
            reason=(
                "no cross-agent causal edges in a multi-agent trace; the "
                "concurrency rules (race / double-assignee / act-after-terminal) "
                "cannot be soundly judged. Enrich the trace with parent/link "
                "edges, or treat this as program-order-only."
            ),
        )
    return CheckResult(Verdict.PASS, "a2a_lifecycle")


def _a2a_predicate(target: Violation):
    # Recompute trust from each sub-history (do NOT force the original tier): an
    # event that supplies the only cross-agent causal edge is then retained,
    # because dropping it would make the order untrusted and the violation would
    # no longer reproduce. This is what keeps a witness independently replayable.
    def pred(sub: History) -> bool:
        sub_hb = HappensBefore(sub)
        for v in a2a_lifecycle.check(sub, sub_hb, trust_concurrency=sub_hb.trustworthy()):
            if v.kind == target.kind and v.object_key == target.object_key:
                return True
        return False

    return pred


# -- linearizable ----------------------------------------------------------
def _object_partitions(history: History):
    """Yield (label, object_type, [data events]) partitions to linearise."""
    for key in history.object_keys():
        evs = [e for e in history.by_object[key] if e.op_type in DATA_OPS]
        if not evs:
            continue
        otype = evs[0].object_type
        if otype == "map":
            by_sub: dict[str, list[Event]] = {}
            for e in evs:
                by_sub.setdefault(e.map_subkey() or "", []).append(e)
            for sub, sevs in by_sub.items():
                yield (f"{key}[{sub}]", "register", sevs)
        else:
            yield (key, otype, evs)


def _check_linearizable(history: History, hb: HappensBefore, caps: lin.Caps) -> CheckResult:
    trust = hb.trustworthy()
    unknown_obj: str | None = None
    for label, otype, evs in _object_partitions(history):
        spec = spec_for(otype)
        result = lin.check_object(evs, hb, spec, caps)
        if result == lin.NOT_LINEARIZABLE:
            v = Violation(
                "not_linearizable",
                f"object {label!r} ({otype}) has no happens-before-respecting "
                f"linearisation consistent with its sequential spec (lost update / "
                f"stale read)",
                span_ids=[e.span_id for e in evs],  # type: ignore[misc]
                object_key=label,
            )
            mast.annotate(v)
            spans = minimize(history, _lin_predicate(label, otype, caps))
            v.span_ids = [s for s in v.span_ids if s in spans] or v.span_ids
            return CheckResult(Verdict.WITNESS, "linearizable", violation=v, witness_spans=spans)
        if result == lin.UNKNOWN and unknown_obj is None:
            unknown_obj = label
    if unknown_obj is not None:
        return CheckResult(
            Verdict.UNKNOWN,
            "linearizable",
            reason=f"resource cap hit while checking object {unknown_obj!r}",
        )
    if not trust:
        return CheckResult(
            Verdict.INSUFFICIENT_HB,
            "linearizable",
            reason=(
                "no cross-agent causal edges in a multi-agent trace: a "
                "linearisation found under this weak order could reorder truly "
                "dependent operations, so PASS cannot be claimed soundly."
            ),
        )
    return CheckResult(Verdict.PASS, "linearizable")


def _lin_predicate(label: str, otype: str, caps: lin.Caps):
    def pred(sub: History) -> bool:
        sub_hb = HappensBefore(sub)
        spec = spec_for(otype)
        for plabel, _potype, evs in _object_partitions(sub):
            if (
                plabel == label
                and lin.check_object(evs, sub_hb, spec, caps) == lin.NOT_LINEARIZABLE
            ):
                return True
        return False

    return pred


def _pick(violations: list[Violation]) -> Violation:
    """Deterministically choose one violation to report (earliest involved event)."""
    return sorted(violations, key=lambda v: (v.span_ids or ["~"], v.kind))[0]
