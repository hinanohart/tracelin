"""Negative fixtures: the two ways tracelin must NOT lie.

(1) It must never emit a sound PASS from an untrusted (program-order-only) order.
(2) It must never flag a correctly-merged concurrent write as a violation
    (the P-C3 reducer-merge false-positive guard)."""

from tracelin import check
from tracelin.verdict import Verdict

from conftest import ev, hist


def test_no_false_pass_under_program_order_only():
    # multi-agent, concurrency-relevant, no cross-agent causal edge:
    # the honest answer is INSUFFICIENT_HB, never PASS.
    h = hist(
        ev("a", "WRITE", key="x", value=1, span="a0"),
        ev("b", "READ", key="x", value=1, span="b0"),
    )
    assert check(h, "linearizable").verdict is not Verdict.PASS
    assert check(h, "linearizable").verdict is Verdict.INSUFFICIENT_HB


def test_correct_reducer_merge_is_not_a_violation():
    # two concurrent counter increments that correctly sum to 2 (operator.add):
    # must be PASS, not a false write-write race.
    h = hist(
        ev("s", "WRITE", key="x", value=0, span="i", object_type="counter", merge="add"),
        ev("a", "INC", key="x", span="a0", parent="i", object_type="counter", merge="add"),
        ev("b", "INC", key="x", span="b0", parent="i", object_type="counter", merge="add"),
        ev(
            "f",
            "READ",
            key="x",
            value=2,
            span="f0",
            parent="a0",
            links=("a0", "b0"),
            object_type="counter",
            merge="add",
        ),
    )
    assert check(h, "a2a_lifecycle").verdict is Verdict.PASS
    assert check(h, "linearizable").verdict is Verdict.PASS


def test_timestamp_only_does_not_produce_pass():
    a = ev("a", "WRITE", key="x", value=1, span="a0")
    b = ev("b", "WRITE", key="x", value=2, span="b0")
    a.ts, b.ts = 1.0, 2.0
    h = hist(a, b)
    # even with timestamps, no fabricated order -> no sound PASS
    assert check(h, "a2a_lifecycle").verdict is not Verdict.PASS
