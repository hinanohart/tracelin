# tracelin

> Conformance & race linter for **recorded** multi-agent agent traces
> (linearizability + happens-before + MAST failure-mode IDs under the hood).

`tracelin` is an **offline falsifier**: you give it a recorded multi-agent
execution trace (OpenTelemetry GenAI spans, JSONL, A2A task events, …), declare
a spec, and it tells you whether the trace can possibly be correct — and if not,
hands you a **1-minimal counterexample** you can replay by hand.

It is **not** a runtime guard. It reads history; it does not change it.

> Status: **v0.1.0a1 (pre-alpha)**. See the CLAIM / NON-CLAIM contract below
> before relying on any output.

(Full README is finalized at release. This is the build placeholder.)
