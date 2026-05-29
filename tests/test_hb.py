"""Happens-before reconstruction, vector clocks, and trust tier."""

from tracelin.hb import HappensBefore

from conftest import ev, hist


def test_program_order_within_agent():
    h = hist(ev("a", "READ", span="a0"), ev("a", "WRITE", span="a1"))
    hb = HappensBefore(h)
    assert hb.happens_before(h.by_span["a0"], h.by_span["a1"])
    assert not hb.concurrent(h.by_span["a0"], h.by_span["a1"])


def test_cross_agent_concurrent_when_no_edge():
    h = hist(ev("a", "WRITE", span="a0"), ev("b", "WRITE", span="b0"))
    hb = HappensBefore(h)
    assert hb.concurrent(h.by_span["a0"], h.by_span["b0"])


def test_explicit_parent_edge_orders_cross_agent():
    h = hist(ev("a", "WRITE", span="a0"), ev("b", "READ", span="b0", parent="a0"))
    hb = HappensBefore(h)
    assert hb.happens_before(h.by_span["a0"], h.by_span["b0"])


def test_links_create_edges():
    h = hist(
        ev("a", "WRITE", span="a0"),
        ev("b", "WRITE", span="b0"),
        ev("c", "READ", span="c0", links=("a0", "b0")),
    )
    hb = HappensBefore(h)
    assert hb.happens_before(h.by_span["a0"], h.by_span["c0"])
    assert hb.happens_before(h.by_span["b0"], h.by_span["c0"])
    assert hb.concurrent(h.by_span["a0"], h.by_span["b0"])


def test_tier_causal_when_cross_agent_edge_present():
    h = hist(ev("a", "WRITE", span="a0"), ev("b", "READ", span="b0", parent="a0"))
    assert HappensBefore(h).tier == "causal"
    assert HappensBefore(h).trustworthy()


def test_tier_program_order_when_no_cross_agent_edge():
    h = hist(ev("a", "WRITE", span="a0"), ev("b", "WRITE", span="b0"))
    hb = HappensBefore(h)
    assert hb.tier == "program_order"
    assert not hb.trustworthy()


def test_single_agent_is_causal():
    h = hist(ev("a", "WRITE", span="a0"), ev("a", "READ", span="a1"))
    assert HappensBefore(h).tier == "causal"


def test_timestamps_never_fabricate_edges():
    # two agents, ts present but NO causal edge -> still concurrent, untrusted
    a = ev("a", "WRITE", span="a0")
    b = ev("b", "WRITE", span="b0")
    a.ts, b.ts = 1.0, 2.0
    h = hist(a, b)
    hb = HappensBefore(h)
    assert hb.concurrent(h.by_span["a0"], h.by_span["b0"])
    assert hb.tier == "program_order"


def test_cycle_detection():
    import pytest

    h = hist(ev("a", "READ", span="a0", parent="b0"), ev("b", "READ", span="b0", parent="a0"))
    with pytest.raises(ValueError, match="cycle"):
        HappensBefore(h)
