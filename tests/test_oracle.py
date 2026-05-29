"""Brute-force reference oracle."""

import pytest
from tracelin.hb import HappensBefore
from tracelin.objects import spec_for
from tracelin.oracle import ORACLE_MAX_OPS, OracleTooLarge, oracle_linearizable

from conftest import ev, hist


def _ops(h, key="x"):
    return [e for e in h.by_object[key] if e.is_data_op]


def test_oracle_accepts_legal_serial():
    h = hist(ev("a", "WRITE", value=1, span="a0"), ev("a", "READ", value=1, span="a1"))
    assert oracle_linearizable(_ops(h), HappensBefore(h), spec_for("register"))


def test_oracle_rejects_stale_read():
    h = hist(
        ev("a", "WRITE", value=0, span="a0"),
        ev("a", "WRITE", value=1, span="a1"),
        ev("a", "READ", value=0, span="a2"),
    )
    assert not oracle_linearizable(_ops(h), HappensBefore(h), spec_for("register"))


def test_oracle_counter_lost_update():
    h = hist(
        ev("s", "WRITE", value=0, span="i", object_type="counter"),
        ev("a", "INC", span="a0", parent="i", object_type="counter"),
        ev("b", "INC", span="b0", parent="i", object_type="counter"),
        ev("f", "READ", value=1, span="f0", links=("a0", "b0"), object_type="counter"),
    )
    assert not oracle_linearizable(_ops(h), HappensBefore(h), spec_for("counter"))


def test_oracle_too_large_raises():
    events = [
        ev("a", "INC", span=f"a{i}", object_type="counter") for i in range(ORACLE_MAX_OPS + 1)
    ]
    h = hist(*events)
    with pytest.raises(OracleTooLarge):
        oracle_linearizable(_ops(h), HappensBefore(h), spec_for("counter"))
