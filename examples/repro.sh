#!/usr/bin/env bash
# Deterministic reproduction of tracelin's headline result on REAL recorded
# LangGraph traces (committed at tests/fixtures/langgraph_raw.jsonl).  Run from a
# clean clone after `pip install -e .` — no langgraph needed (the adapter only
# parses the recorded trace).  Used as the CI `repro` determinism gate.
set -uo pipefail

FIX=tests/fixtures/langgraph_raw.jsonl

echo "[repro] a2a_lifecycle (structural race layer) on real LangGraph traces"
a2a=$(tracelin check "$FIX" --adapter langgraph --spec a2a_lifecycle --show-witness)
echo "$a2a"
echo "$a2a" | grep -q "T1_writewrite_noreducer: Witness (a2a_lifecycle)" || { echo "FAIL: T1 should be a write-write race witness"; exit 1; }
echo "$a2a" | grep -q "T2_lostupdate_lww: PASS"                            || { echo "FAIL: T2 has a declared merge, no structural race"; exit 1; }
echo "$a2a" | grep -q "T3_correct_merge_add: PASS"                         || { echo "FAIL: T3 is a correct merge"; exit 1; }

echo "[repro] linearizable (lost-update layer)"
lin=$(tracelin check "$FIX" --adapter langgraph --spec linearizable --show-witness)
echo "$lin"
echo "$lin" | grep -q "T2_lostupdate_lww: Witness (linearizable)" || { echo "FAIL: T2 should be a lost-update witness"; exit 1; }
echo "$lin" | grep -q "T3_correct_merge_add: PASS"                || { echo "FAIL: T3 must linearize (no false positive)"; exit 1; }

echo "repro OK — real-trace detection reproduced deterministically"
