"""linearizable spec (Wing-Gong/Lowe search) + caps."""

from tracelin.hb import HappensBefore
from tracelin.objects import spec_for
from tracelin.specs import linearizable as lin

from conftest import ev, hist


def _check(h, key="x", otype="register"):
    hb = HappensBefore(h)
    evs = [e for e in h.by_object[key] if e.is_data_op]
    return lin.check_object(evs, hb, spec_for(otype), lin.Caps())


def test_serial_register_linearizable():
    h = hist(
        ev("a", "WRITE", value=1, span="a0"),
        ev("a", "READ", value=1, span="a1"),
    )
    assert _check(h) == lin.LINEARIZABLE


def test_stale_read_not_linearizable():
    # write 1 happens-before a read that returns the old value 0 -> impossible
    h = hist(
        ev("a", "WRITE", value=0, span="a0"),
        ev("a", "WRITE", value=1, span="a1"),
        ev("a", "READ", value=0, span="a2"),
    )
    assert _check(h) == lin.NOT_LINEARIZABLE


def test_concurrent_counter_increments_linearizable():
    # two concurrent incs, committed read = 2 -> linearizable
    h = hist(
        ev("s", "WRITE", value=0, span="i", object_type="counter"),
        ev("a", "INC", span="a0", parent="i", object_type="counter"),
        ev("b", "INC", span="b0", parent="i", object_type="counter"),
        ev("f", "READ", value=2, span="f0", parent="a0", links=("a0", "b0"), object_type="counter"),
    )
    assert _check(h, otype="counter") == lin.LINEARIZABLE


def test_lost_update_counter_not_linearizable():
    # two incs but committed read = 1 -> lost update
    h = hist(
        ev("s", "WRITE", value=0, span="i", object_type="counter"),
        ev("a", "INC", span="a0", parent="i", object_type="counter"),
        ev("b", "INC", span="b0", parent="i", object_type="counter"),
        ev("f", "READ", value=1, span="f0", parent="a0", links=("a0", "b0"), object_type="counter"),
    )
    assert _check(h, otype="counter") == lin.NOT_LINEARIZABLE


def test_cap_returns_unknown():
    # exceed max_ops -> UNKNOWN, never a guess
    events = [ev("a", "INC", span=f"a{i}", object_type="counter") for i in range(6)]
    h = hist(*events)
    hb = HappensBefore(h)
    caps = lin.Caps(max_ops=3)
    evs = [e for e in h.by_object["x"] if e.is_data_op]
    assert lin.check_object(evs, hb, spec_for("counter"), caps) == lin.UNKNOWN


def test_concurrency_width_cap():
    events = [ev(f"ag{i}", "WRITE", value=i, span=f"w{i}") for i in range(5)]
    h = hist(*events)
    hb = HappensBefore(h)
    caps = lin.Caps(max_concurrent_per_object=2)
    evs = [e for e in h.by_object["x"] if e.is_data_op]
    assert lin.check_object(evs, hb, spec_for("register"), caps) == lin.UNKNOWN
