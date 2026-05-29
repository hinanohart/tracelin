"""CLI: verdict output and fail-closed exit codes."""

import json

from tracelin.cli import EXIT_OK, EXIT_UNCONFIRMED, EXIT_USAGE, EXIT_WITNESS, main

from conftest import ev, hist


def _write_native(tmp_path, h):
    p = tmp_path / "trace.jsonl"
    p.write_text("\n".join(json.dumps(r) for r in h.to_records()))
    return str(p)


def test_check_pass_exit_ok(tmp_path, capsys):
    h = hist(
        ev("o", "STATE_TRANSITION", key="t", value="submitted", span="s0"),
        ev("o", "STATE_TRANSITION", key="t", value="working", span="s1"),
    )
    rc = main(["check", _write_native(tmp_path, h), "--spec", "a2a_lifecycle", "--ci"])
    assert rc == EXIT_OK


def test_check_witness_exit_one(tmp_path, capsys):
    h = hist(
        ev("s", "WRITE", key="x", value=0, span="i", object_type="register"),
        ev("a", "WRITE", key="x", value=1, span="a0", parent="i", object_type="register"),
        ev("b", "WRITE", key="x", value=2, span="b0", parent="i", object_type="register"),
    )
    rc = main(["check", _write_native(tmp_path, h), "--spec", "a2a_lifecycle", "--ci"])
    assert rc == EXIT_WITNESS
    assert "Witness" in capsys.readouterr().out


def test_check_insufficient_hb_exit_two(tmp_path):
    h = hist(
        ev("a", "WRITE", key="x", value=1, span="a0"),
        ev("b", "READ", key="x", value=1, span="b0"),
    )
    rc = main(["check", _write_native(tmp_path, h), "--spec", "linearizable", "--ci"])
    assert rc == EXIT_UNCONFIRMED


def test_classify_runs_all_specs(tmp_path, capsys):
    h = hist(
        ev("o", "STATE_TRANSITION", key="t", value="submitted", span="s0"),
    )
    main(["classify", _write_native(tmp_path, h)])
    out = capsys.readouterr().out
    assert "a2a_lifecycle=" in out and "linearizable=" in out


def test_langgraph_adapter_via_cli(tmp_path, capsys):
    raw = {
        "label": "race",
        "reducer": "none",
        "initial": {"counter": 0},
        "nodes": [
            {"agent": "agent_a", "read": {"counter": 0}, "write": {"counter": 1}},
            {"agent": "agent_b", "read": {"counter": 0}, "write": {"counter": 1}},
        ],
        "observed_final": None,
    }
    p = tmp_path / "raw.jsonl"
    p.write_text(json.dumps(raw))
    rc = main(["check", str(p), "--adapter", "langgraph", "--spec", "a2a_lifecycle", "--ci"])
    assert rc == EXIT_WITNESS


def test_missing_file_is_a_clean_error(tmp_path, capsys):
    rc = main(["check", str(tmp_path / "nope.jsonl")])
    assert rc == EXIT_USAGE
    err = capsys.readouterr().err
    assert "not found" in err and "Traceback" not in err


def test_malformed_json_is_a_clean_error(tmp_path, capsys):
    p = tmp_path / "bad.jsonl"
    p.write_text("{not json}")
    rc = main(["check", str(p)])
    assert rc == EXIT_USAGE
    err = capsys.readouterr().err
    assert "error" in err and "Traceback" not in err


def test_unknown_op_type_is_a_clean_error(tmp_path, capsys):
    p = tmp_path / "weird.jsonl"
    p.write_text(json.dumps({"agent_id": "a", "op_type": "FROBNICATE", "object_key": "x"}))
    rc = main(["check", str(p)])
    assert rc == EXIT_USAGE
    err = capsys.readouterr().err
    assert "error" in err and "Traceback" not in err


def test_usage_exit_code_is_distinct_from_unconfirmed():
    # a bad-input error must be distinguishable from an unconfirmed verdict
    assert EXIT_USAGE != EXIT_UNCONFIRMED


def test_show_witness_surfaces_mast_advisory(tmp_path, capsys):
    # a structural write-write race carries an advisory MAST FC2 note
    h = hist(
        ev("s", "WRITE", key="x", value=0, span="i", object_type="register"),
        ev("a", "WRITE", key="x", value=1, span="a0", parent="i", object_type="register"),
        ev("b", "WRITE", key="x", value=2, span="b0", parent="i", object_type="register"),
    )
    main(["check", _write_native(tmp_path, h), "--spec", "a2a_lifecycle", "--show-witness"])
    out = capsys.readouterr().out
    assert "witness sub-history:" in out
    assert "MAST FC2 (advisory):" in out
