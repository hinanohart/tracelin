"""Differential test: the optimised engine must agree with the brute-force
oracle on every generated history.  This is how we earn trust in the Wing-Gong
search — any disagreement is a soundness bug."""

from hypothesis import given, settings
from hypothesis import strategies as st
from tracelin.hb import HappensBefore
from tracelin.history import Event, History, OpType
from tracelin.objects import spec_for
from tracelin.oracle import oracle_linearizable
from tracelin.specs import linearizable as lin


@st.composite
def small_history(draw):
    otype = draw(st.sampled_from(["register", "counter"]))
    n = draw(st.integers(min_value=1, max_value=6))
    ops_pool = ["WRITE", "READ"] if otype == "register" else ["INC", "READ"]
    events = []
    for i in range(n):
        op = draw(st.sampled_from(ops_pool))
        if op == "WRITE":
            val = draw(st.integers(min_value=0, max_value=2))
        elif op == "READ":
            val = draw(st.sampled_from([None, 0, 1, 2]))
        else:  # INC
            val = None
        earlier = [f"e{j}" for j in range(i)]
        links = (
            tuple(draw(st.lists(st.sampled_from(earlier), unique=True, max_size=i)))
            if earlier
            else ()
        )
        events.append(
            Event(
                agent_id=f"ag{i}",  # distinct agents -> HB only from links
                op_type=OpType(op),
                object_key="x",
                value=val,
                span_id=f"e{i}",
                links=links,
                object_type=otype,
            )
        )
    return History(events), otype


@given(small_history())
@settings(max_examples=400, deadline=None)
def test_oracle_and_engine_agree(data):
    h, otype = data
    hb = HappensBefore(h)
    evs = [e for e in h.by_object["x"] if e.is_data_op]
    spec_o = spec_for(otype)
    spec_e = spec_for(otype)
    oracle = oracle_linearizable(evs, hb, spec_o)  # bool
    engine = lin.check_object(evs, hb, spec_e, lin.Caps())
    assert engine in (lin.LINEARIZABLE, lin.NOT_LINEARIZABLE)  # no cap hit here
    assert (engine == lin.LINEARIZABLE) == oracle
