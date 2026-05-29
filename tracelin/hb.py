"""Happens-before reconstruction over a :class:`~tracelin.history.History`.

We build a partial order (Lamport's happens-before) from *explicit* causal hints
and per-agent program order, then compute Fidge–Mattern vector clocks so that
"are these two events concurrent?" is an O(agents) test.

Trust tier (the soundness lever)
--------------------------------
``HappensBefore.tier`` reports how the order was obtained:

* ``"explicit"`` — every cross-event edge comes from ``parent_span_id`` /
  ``links`` (plus per-agent program order).  Trustworthy.
* ``"timestamp"`` — we had to fall back to wall-clock ``ts`` to order anything.
  *Not* trustworthy: a convenient order we invent here could reorder two ops
  that truly had a real-time dependency, producing a **false PASS**.

The engine uses the tier to decide whether a "no violation found" result may be
reported as ``PASS`` or must be reported as ``INSUFFICIENT_HB`` (see
:mod:`tracelin.engine`).  A *witness* (violation) is always sound regardless of
tier: fewer known edges means more candidate linearisations, so if none is
legal under the weak order, none is legal under any stronger one either.
"""

from __future__ import annotations

from collections import defaultdict

from .history import Event, History


class HappensBefore:
    """Partial order over events with vector clocks and a trust tier."""

    def __init__(self, history: History):
        self.history = history
        self._agents = sorted(history.by_agent.keys())
        self._agent_idx = {a: i for i, a in enumerate(self._agents)}
        # direct predecessor edges: span_id -> set(span_id)
        self.preds: dict[str, set[str]] = defaultdict(set)
        self.tier: str = "explicit"
        self._build_edges()
        self.vc: dict[str, tuple[int, ...]] = {}
        self._compute_vector_clocks()

    # -- edge construction -------------------------------------------------
    def _build_edges(self) -> None:
        h = self.history
        has_cross_agent_edge = False
        for e in h.events:
            assert e.span_id is not None
            # program order: previous event of the same agent (always trusted)
            po = h.program_order_pred(e)
            if po is not None:
                self.preds[e.span_id].add(po.span_id)  # type: ignore[arg-type]
            # explicit causal edges from the trace
            for pred_span in self._explicit_preds(e):
                self.preds[e.span_id].add(pred_span)
                if h.by_span[pred_span].agent_id != e.agent_id:
                    has_cross_agent_edge = True

        # Trust tier (degradation ladder; we NEVER fabricate edges from ts):
        #   "causal"        -- single-agent, OR at least one real cross-agent
        #                      causal edge was recorded -> trustworthy: absence
        #                      of an edge is taken to mean genuine concurrency,
        #                      so a "no violation" result may be reported PASS.
        #   "program_order" -- multi-agent but no cross-agent causal edge at all
        #                      -> untrusted: cross-agent ops are treated as
        #                      concurrent (sound for witnesses) but PASS is
        #                      refused (INSUFFICIENT_HB) because absence of edges
        #                      may just mean the trace omitted them.
        # ``ts`` is retained on events for display/future use but is never used
        # to add ordering edges in v0.1 (a fabricated order could create a false
        # FAIL; the "timestamp" tier of the ladder is deliberately deferred).
        multi_agent = len(self._agents) > 1
        self.tier = "program_order" if (multi_agent and not has_cross_agent_edge) else "causal"

    def _explicit_preds(self, e: Event):
        h = self.history
        preds: list[str] = []
        if e.parent_span_id is not None and e.parent_span_id in h.by_span:
            preds.append(e.parent_span_id)
        for link in e.links:
            if link in h.by_span:
                preds.append(link)
        return preds

    # -- vector clocks -----------------------------------------------------
    def _topo_order(self) -> list[str]:
        indeg: dict[str, int] = {e.span_id: 0 for e in self.history.events}  # type: ignore[misc]
        succ: dict[str, list[str]] = defaultdict(list)
        for s, ps in self.preds.items():
            for p in ps:
                succ[p].append(s)
                indeg[s] += 1
        queue = [s for s, d in indeg.items() if d == 0]
        order: list[str] = []
        while queue:
            # deterministic: pop smallest span id for stable clocks
            queue.sort()
            n = queue.pop(0)
            order.append(n)
            for m in succ[n]:
                indeg[m] -= 1
                if indeg[m] == 0:
                    queue.append(m)
        if len(order) != len(self.history.events):
            raise ValueError("cycle detected in happens-before graph")
        return order

    def _compute_vector_clocks(self) -> None:
        n = len(self._agents)
        for span in self._topo_order():
            e = self.history.by_span[span]
            ai = self._agent_idx[e.agent_id]
            clock = [0] * n
            for p in self.preds[span]:
                pc = self.vc[p]
                clock = [max(clock[i], pc[i]) for i in range(n)]
            clock[ai] += 1
            self.vc[span] = tuple(clock)

    # -- queries -----------------------------------------------------------
    def _vc_le(self, x: tuple[int, ...], y: tuple[int, ...]) -> bool:
        return all(x[i] <= y[i] for i in range(len(x)))

    def happens_before(self, a: Event, b: Event) -> bool:
        """True iff ``a`` causally precedes ``b`` (a -> b)."""
        return a.span_id != b.span_id and self._vc_le(
            self.vc[a.span_id],
            self.vc[b.span_id],  # type: ignore[index]
        )

    def concurrent(self, a: Event, b: Event) -> bool:
        """True iff ``a`` and ``b`` are happens-before incomparable."""
        if a.span_id == b.span_id:
            return False
        return not self.happens_before(a, b) and not self.happens_before(b, a)

    def trustworthy(self) -> bool:
        """Whether the order may underwrite a sound PASS."""
        return self.tier == "causal"
