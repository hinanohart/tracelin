"""``tracelin`` command-line interface.

    tracelin check  TRACE  [--spec a2a_lifecycle|linearizable] [--adapter ...] [--ci]
    tracelin classify TRACE [--adapter ...]

``check`` runs one spec and prints a verdict per trace.  ``classify`` runs both
specs and reports the conformance picture (the power-user view).  ``--ci`` makes
the exit code fail-closed: non-zero on any Witness, and (since they are not a
confirmed PASS) also on INSUFFICIENT_HB / UNKNOWN.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterable

from . import engine
from .adapters import langgraph as lg_adapter
from .adapters import otel_genai as otel_adapter
from .history import History
from .verdict import Verdict

EXIT_OK = 0
EXIT_WITNESS = 1
EXIT_UNCONFIRMED = 2  # INSUFFICIENT_HB / UNKNOWN under --ci


def _read_jsonl(path: str) -> list[dict]:
    rows = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def load_histories(path: str, adapter: str) -> list[tuple[str, History]]:
    if adapter == "native":
        return [("trace", History.from_records(_read_jsonl(path)))]
    if adapter == "langgraph":
        return [
            (r.get("label", f"run{i}"), lg_adapter.from_raw(r))
            for i, r in enumerate(_read_jsonl(path))
        ]
    if adapter == "otel_genai":
        return [("trace", otel_adapter.from_spans(_read_jsonl(path)))]
    raise ValueError(f"unknown adapter {adapter!r}")


def _ci_exit(verdicts: Iterable[Verdict]) -> int:
    vs = list(verdicts)
    if any(v is Verdict.WITNESS for v in vs):
        return EXIT_WITNESS
    if any(v in (Verdict.INSUFFICIENT_HB, Verdict.UNKNOWN) for v in vs):
        return EXIT_UNCONFIRMED
    return EXIT_OK


def cmd_check(args: argparse.Namespace) -> int:
    histories = load_histories(args.trace, args.adapter)
    verdicts = []
    for name, hist in histories:
        result = engine.check(hist, args.spec)
        verdicts.append(result.verdict)
        print(f"{name}: {result}")
        if result.violation is not None and args.show_witness:
            print(f"    witness sub-history: {result.witness_spans}")
    if args.ci:
        return _ci_exit(verdicts)
    return EXIT_OK


def cmd_classify(args: argparse.Namespace) -> int:
    histories = load_histories(args.trace, args.adapter)
    verdicts = []
    for name, hist in histories:
        line = [f"{name}:"]
        for spec in engine.SPECS:
            result = engine.check(hist, spec)
            verdicts.append(result.verdict)
            line.append(f"{spec}={result.verdict.value}")
        print("  ".join(line))
    if args.ci:
        return _ci_exit(verdicts)
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="tracelin", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("trace", help="path to the trace file (JSONL)")
    common.add_argument(
        "--adapter",
        default="native",
        choices=["native", "langgraph", "otel_genai"],
        help="trace format (default: native event JSONL)",
    )
    common.add_argument("--ci", action="store_true", help="fail-closed exit codes")

    c = sub.add_parser("check", parents=[common], help="run one spec")
    c.add_argument("--spec", default="a2a_lifecycle", choices=list(engine.SPECS))
    c.add_argument("--show-witness", action="store_true")
    c.set_defaults(func=cmd_check)

    cl = sub.add_parser("classify", parents=[common], help="run all specs")
    cl.set_defaults(func=cmd_classify)
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
