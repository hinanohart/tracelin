"""End-to-end on REAL recorded LangGraph traces (the ship-and-yank guard).

``tests/fixtures/langgraph_raw.jsonl`` is produced by a real LangGraph 1.x run
(see examples/langgraph_race_harness.py); no langgraph install is needed here
because the adapter only parses the recorded record.

Hand-replay of the T2 witness: the counter object 'counter' receives two
concurrent increments (agent_a, agent_b) from 0, yet the committed final READ is
1 — no ordering of two increments yields 1, so the trace cannot be linearised
for a counter (a lost update).  Verified below."""

import json
import pathlib

import pytest
from tracelin import check
from tracelin.adapters import langgraph as lg
from tracelin.verdict import Verdict

FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "langgraph_raw.jsonl"


def _runs():
    return {
        json.loads(line)["label"]: json.loads(line)
        for line in FIXTURE.read_text().splitlines()
        if line.strip()
    }


@pytest.fixture(scope="module")
def runs():
    return _runs()


def test_fixture_has_three_real_runs(runs):
    assert set(runs) == {
        "T1_writewrite_noreducer",
        "T2_lostupdate_lww",
        "T3_correct_merge_add",
    }
    # provenance: produced by a real langgraph run
    assert all(r["framework"] == "langgraph" for r in runs.values())
    assert runs["T1_writewrite_noreducer"]["raised"]  # InvalidUpdateError really happened


def test_T1_write_write_race(runs):
    h = lg.from_raw(runs["T1_writewrite_noreducer"])
    assert check(h, "a2a_lifecycle").verdict is Verdict.WITNESS
    assert check(h, "linearizable").verdict is Verdict.PASS


def test_T2_lost_update(runs):
    h = lg.from_raw(runs["T2_lostupdate_lww"])
    r = check(h, "linearizable")
    assert r.verdict is Verdict.WITNESS
    assert "counter" in (r.violation.object_key or "")
    # the witness includes the committed read (final:counter) that proves the loss
    assert any("final" in s for s in r.witness_spans)


def test_T3_correct_merge_no_false_positive(runs):
    h = lg.from_raw(runs["T3_correct_merge_add"])
    assert check(h, "a2a_lifecycle").verdict is Verdict.PASS
    assert check(h, "linearizable").verdict is Verdict.PASS
