"""Witness minimisation: 1-minimality."""

from tracelin import check
from tracelin.hb import HappensBefore
from tracelin.specs import a2a_lifecycle
from tracelin.verdict import Verdict

from conftest import ev, hist


def _still_races(span_ids, full):
    sub = full.subhistory(set(span_ids))
    hb = HappensBefore(sub)
    vs = a2a_lifecycle.check(sub, hb, trust_concurrency=hb.trustworthy())
    return any(v.kind == "concurrent_write_race" for v in vs)


def test_witness_is_one_minimal():
    h = hist(
        ev("s", "WRITE", key="x", value=0, span="i", object_type="register"),
        ev("a", "WRITE", key="x", value=1, span="a0", parent="i", object_type="register"),
        ev("b", "WRITE", key="x", value=2, span="b0", parent="i", object_type="register"),
    )
    r = check(h, "a2a_lifecycle")
    w = r.witness_spans
    assert _still_races(w, h)
    # removing any single event must break the violation (1-minimal)
    for s in w:
        assert not _still_races([x for x in w if x != s], h)


def test_witness_replays_same_violation():
    h = hist(
        ev("a", "WRITE", key="x", value=0, span="a0"),
        ev("a", "WRITE", key="x", value=1, span="a1"),
        ev("a", "READ", key="x", value=0, span="a2"),  # stale read of own old write
    )
    r = check(h, "linearizable")
    assert r.verdict is Verdict.WITNESS
    sub = h.subhistory(set(r.witness_spans))
    assert check(sub, "linearizable").verdict is Verdict.WITNESS
