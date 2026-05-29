# tracelin

> Conformance & race linter for **recorded** multi-agent agent traces
> — linearizability + happens-before + MAST failure-mode categories under the hood.

`tracelin` is an **offline falsifier**. You give it a recorded multi-agent
execution trace (OpenTelemetry GenAI spans, a LangGraph trace, A2A task events,
JSONL …), declare a spec, and it tells you whether the trace *can possibly be
correct*. When it cannot, it hands you a **1-minimal counterexample sub-history**
you can replay by hand, tagged with the closest [MAST](https://arxiv.org/abs/2503.13657)
failure-mode category.

It reads history; it does **not** change it. It is not a runtime guard — it is
the thing you run over the traces you already collect, in CI or after an
incident, to find the lost updates and lifecycle violations that silent
"it mostly works" multi-agent systems hide.

> **Status: v0.1.0a4 (pre-alpha).** Read the CLAIM / NON-CLAIM contract below
> before relying on any output. APIs may change.

## Install

Not on PyPI yet (pre-alpha). Install from source:

```bash
pip install "git+https://github.com/hinanohart/tracelin"          # core (pure stdlib, zero deps)
pip install "tracelin[otel] @ git+https://github.com/hinanohart/tracelin"   # + OTel helpers
```

## Quickstart

```python
from tracelin import History, check

# A counter that two agents incremented concurrently; the committed value is 1.
rows = [
    {"agent_id": "sys", "op_type": "WRITE", "object_key": "n", "value": 0,
     "span_id": "i", "object_type": "counter"},
    {"agent_id": "a", "op_type": "INC", "object_key": "n",
     "span_id": "a0", "parent_span_id": "i", "object_type": "counter"},
    {"agent_id": "b", "op_type": "INC", "object_key": "n",
     "span_id": "b0", "parent_span_id": "i", "object_type": "counter"},
    {"agent_id": "final", "op_type": "READ", "object_key": "n", "value": 1,
     "span_id": "f", "parent_span_id": "a0", "links": ["a0", "b0"],
     "object_type": "counter"},
]
result = check(History.from_records(rows), "linearizable")
print(result)
# Witness (linearizable): [not_linearizable on 'n'] object 'n' (counter) has no
# happens-before-respecting linearisation consistent with its sequential spec
# (lost update / stale read) (events: a0, b0, f; MAST FC2)
```

Command line:

```bash
tracelin check trace.jsonl --spec a2a_lifecycle --ci          # native event JSONL
tracelin check raw.jsonl   --adapter langgraph --spec linearizable
tracelin classify trace.jsonl                                  # all specs at once
```

`--ci` makes the exit code fail-closed: non-zero on any `Witness`, and (because
they are not a confirmed pass) also on `INSUFFICIENT_HB` / `UNKNOWN`.

A runnable, deterministic reproduction on a **real** LangGraph run lives in
[`examples/repro.sh`](examples/repro.sh) (the trace was recorded by
[`examples/langgraph_race_harness.py`](examples/langgraph_race_harness.py),
which reproduces LangGraph's `InvalidUpdateError` and a last-writer-wins lost
update).

## The four verdicts

| Verdict | Meaning |
|---|---|
| `PASS` | No violation, and the happens-before order was trustworthy enough to say so. |
| `Witness` | A real, reproducible violation, with a 1-minimal counter-example sub-history. |
| `INSUFFICIENT_HB` | A *refusal*: the trace lacked the cross-agent causal edges needed to soundly claim PASS. Not a pass, not a fail. |
| `UNKNOWN` | A resource cap (ops / concurrency width / time) was hit. Never a guess. |

The point of four values instead of a boolean is that **tracelin never emits a
false PASS**. If it cannot trust the order, it says `INSUFFICIENT_HB`; if a
search blows its budget, it says `UNKNOWN`. A *linearizability* `Witness` is sound
at any trust tier — fewer known edges only add candidate linearisations, so a
violation found under a weak order persists under any stronger one. The
*concurrency* checks (race / double-assignee / act-after-terminal) work the other
way: fewer edges can fabricate apparent concurrency, so tracelin withholds them on
an untrusted order (reporting `INSUFFICIENT_HB`) and emits those witnesses only at
the `causal` tier. Either way, a `Witness` that *is* emitted is sound.

## CLAIM / NON-CLAIM

**CLAIM.** tracelin is a *sound falsifier* over recorded traces:
- Every reported `Witness` corresponds to a real violation and is replayable by
  hand from the sub-history.
- Within its resource bounds the search is complete; reported witnesses are
  1-minimal (removing any single event makes the violation disappear).
- It never reports `PASS` from an untrusted (program-order-only / timestamp)
  order, and never fabricates ordering from wall-clock timestamps.

**NON-CLAIM.** tracelin is *not*:
- a runtime prevention layer (that is [S-Bus](https://arxiv.org/abs/2605.17076)'s
  job; tracelin is the offline, post-hoc complement);
- able to see concurrency the trace did not record (untraced races are invisible
  — so a `PASS` is "no violation *in this trace*", not "the system is correct");
- an exhaustive MAST detector — witnesses are mapped to a MAST *category* via a
  small manual table, and anything without a defensible mapping is reported
  `UNMAPPED`;
- a checker of `causal` / `sequential` consistency in v0.1 (full causal-
  consistency checking is NP-complete in general,
  [Bouajjani et al., POPL 2017](https://arxiv.org/abs/1611.00580); these tiers
  are deliberately deferred rather than claimed).

## How it works

1. **Adapters** turn a recorded trace into a `History` of `Event`s. The core
   imports no agent framework.
2. **Happens-before** (`hb.py`) builds a vector-clock partial order from explicit
   `parent_span_id` / `links` edges plus per-agent program order, and labels its
   **trust tier** (`causal` if real cross-agent edges exist, else
   `program_order`). Timestamps are never turned into ordering edges.
3. **Specs** decide conformance:
   - `a2a_lifecycle` — always-polynomial structural rules: A2A task-state-machine
     legality, no action after a terminal state, single-assignee per subtask, and
     concurrent write-write races to a single-writer object with no declared
     merge (the *structural race condition* of S-Bus).
   - `linearizable` — a memoised Wing–Gong/Lowe search per object
     (`register` / `counter` / `map`), with hard caps that yield `UNKNOWN`
     rather than guessing. Validated against a brute-force oracle by a
     differential property test.
4. **Witness** minimisation (`witness.py`) shrinks a failing history to a
   1-minimal sub-history; **mast.py** annotates the closest failure-mode category.

## Prior art & credits

tracelin re-targets four decades of distributed-systems verification
(Herlihy–Wing linearizability, Lamport happens-before, Knossos/Jepsen/Porcupine/
Elle, Wing–Gong/Lowe) at agent traces, and builds on MAST, the A2A lifecycle,
OpenTelemetry GenAI conventions, S-Bus, OmniLink, and ddmin. Full attributions
are in [`NOTICE`](NOTICE). No code is copied from those projects.

## License

Apache-2.0. See [`LICENSE`](LICENSE) and [`NOTICE`](NOTICE).
