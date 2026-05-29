"""Engine: four-valued verdicts, INSUFFICIENT_HB refusal, compositionality."""

from tracelin import check
from tracelin.verdict import Verdict

from conftest import ev, hist


def test_pass_on_clean_trace():
    h = hist(
        ev("orch", "STATE_TRANSITION", key="t1", value="submitted", span="s0"),
        ev("orch", "STATE_TRANSITION", key="t1", value="working", span="s1"),
    )
    assert check(h, "a2a_lifecycle").verdict is Verdict.PASS


def test_witness_carries_violation_and_minimal_spans():
    h = hist(
        ev("s", "WRITE", key="x", value=0, span="i", object_type="register"),
        ev("a", "WRITE", key="x", value=1, span="a0", parent="i", object_type="register"),
        ev("b", "WRITE", key="x", value=2, span="b0", parent="i", object_type="register"),
    )
    r = check(h, "a2a_lifecycle")
    assert r.verdict is Verdict.WITNESS
    assert r.violation is not None
    # the init "i" is retained: it supplies the cross-agent edge that makes the
    # order causal-tier, so the witness independently reproduces the race.
    assert set(r.witness_spans) == {"i", "a0", "b0"}


def test_insufficient_hb_refuses_pass_for_linearizable():
    # multi-agent, no cross-agent edge, no violation found -> must NOT be PASS
    h = hist(
        ev("a", "WRITE", key="x", value=1, span="a0"),
        ev("b", "READ", key="x", value=1, span="b0"),
    )
    r = check(h, "linearizable")
    assert r.verdict is Verdict.INSUFFICIENT_HB


def test_insufficient_hb_refuses_pass_for_a2a_concurrency():
    # multi-agent concurrency-relevant ops, untrusted order -> refuse PASS
    h = hist(
        ev("a", "WRITE", key="x", value=1, span="a0", object_type="register"),
        ev("b", "WRITE", key="x", value=2, span="b0", object_type="register"),
    )
    r = check(h, "a2a_lifecycle")
    assert r.verdict is Verdict.INSUFFICIENT_HB


def test_witness_sound_even_without_trust():
    # a lost update is a real violation even with a weak order
    h = hist(
        ev("a", "WRITE", key="x", value=1, span="a0"),
        ev("a", "READ", key="x", value=0, span="a1"),  # reads stale own write -> impossible
    )
    r = check(h, "linearizable")
    assert r.verdict is Verdict.WITNESS


def test_unknown_propagates_from_caps():
    from tracelin.specs.linearizable import Caps

    events = [ev("a", "INC", span=f"a{i}", object_type="counter") for i in range(6)]
    h = hist(*events)
    r = check(h, "linearizable", caps=Caps(max_ops=3))
    assert r.verdict is Verdict.UNKNOWN


def test_per_object_compositionality():
    # object x is fine, object y has a stale read -> overall Witness on y
    h = hist(
        ev("a", "WRITE", key="x", value=1, span="x0"),
        ev("a", "READ", key="x", value=1, span="x1"),
        ev("a", "WRITE", key="y", value=1, span="y0"),
        ev("a", "READ", key="y", value=5, span="y1"),  # impossible
    )
    r = check(h, "linearizable")
    assert r.verdict is Verdict.WITNESS
    assert r.violation.object_key == "y"


def test_map_per_subkey():
    h = hist(
        ev("a", "WRITE", key="m", value=1, span="m0", object_type="map", subkey="k1"),
        ev("a", "READ", key="m", value=1, span="m1", object_type="map", subkey="k1"),
        ev("a", "WRITE", key="m", value=2, span="m2", object_type="map", subkey="k2"),
        ev("a", "READ", key="m", value=2, span="m3", object_type="map", subkey="k2"),
    )
    assert check(h, "linearizable").verdict is Verdict.PASS


def test_unknown_spec_raises():
    import pytest

    with pytest.raises(ValueError, match="unknown spec"):
        check(hist(ev("a", "READ")), "nonsense")
