"""Sequential specifications."""

from tracelin.objects import (
    CounterSpec,
    RegisterSpec,
    is_legal_sequential,
    spec_for,
)

from conftest import ev


def test_register_read_must_match_last_write():
    spec = RegisterSpec()
    legal = [ev("a", "WRITE", value=5), ev("a", "READ", value=5)]
    illegal = [ev("a", "WRITE", value=5), ev("a", "READ", value=9)]
    assert is_legal_sequential(legal, spec)
    assert not is_legal_sequential(illegal, spec)


def test_counter_increments():
    spec = CounterSpec()
    seq = [
        ev("a", "INC", object_type="counter"),
        ev("a", "INC", object_type="counter"),
        ev("a", "READ", value=2, object_type="counter"),
    ]
    assert is_legal_sequential(seq, spec)
    bad = [
        ev("a", "INC", object_type="counter"),
        ev("a", "INC", object_type="counter"),
        ev("a", "READ", value=1, object_type="counter"),
    ]
    assert not is_legal_sequential(bad, spec)


def test_counter_read_unchecked_passes():
    spec = CounterSpec()
    seq = [
        ev("a", "INC", object_type="counter"),
        ev("a", "READ", value=None, object_type="counter"),
    ]
    # value=None means UNCHECKED -> not constrained
    assert is_legal_sequential(seq, spec)


def test_spec_for_returns_right_type():
    assert isinstance(spec_for("register"), RegisterSpec)
    assert isinstance(spec_for("counter"), CounterSpec)
    assert isinstance(spec_for("map"), RegisterSpec)  # map subkey reduces to register
