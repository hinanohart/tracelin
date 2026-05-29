"""Sequential specifications for the object types tracelin can linearise.

A sequential specification answers: *applied in this total order, is every
operation's recorded return value the one the object would produce?*  Both the
brute-force :mod:`tracelin.oracle` and the Wing–Gong search in
:mod:`tracelin.specs.linearizable` are defined against these specs, which keeps
the two checkers honest about exactly the same semantics.

v0.1 object types (architecture scope): ``register``, ``counter``, ``map``.
``map`` reduces to a per-subkey ``register`` (Herlihy–Wing per-object locality),
so the engine checks each subkey independently.  ``set`` / ``list`` are deferred.
"""

from __future__ import annotations

from typing import Any

from .history import Event, OpType

# A READ whose recorded return value is ``None`` is treated as *unchecked*: the
# trace did not capture what it read, so it constrains no linearisation.  (Agent
# reads typically return non-None content; this only loses the ability to check
# a read that genuinely returned None, which can never cause a false FAIL.)
UNCHECKED = None


class SpecViolation(Exception):
    """Raised by a sequential spec when an op's recorded return is impossible."""


class SequentialSpec:
    """Base class: a mutable reference object applied op-by-op."""

    def initial(self) -> Any:  # pragma: no cover - overridden
        raise NotImplementedError

    def apply(self, state: Any, event: Event) -> Any:
        """Apply ``event`` to ``state``; raise :class:`SpecViolation` if the
        recorded return value is inconsistent.  Return the new state."""
        raise NotImplementedError  # pragma: no cover


class RegisterSpec(SequentialSpec):
    """A read/write register. WRITE sets the value; READ must return current."""

    def initial(self) -> Any:
        return None

    def apply(self, state: Any, event: Event) -> Any:
        if event.op_type is OpType.WRITE:
            return event.value
        if event.op_type is OpType.READ:
            if event.value is not UNCHECKED and event.value != state:
                raise SpecViolation(f"READ returned {event.value!r} but register holds {state!r}")
            return state
        raise SpecViolation(f"register does not support op {event.op_type}")


class CounterSpec(SequentialSpec):
    """A counter. INC adds one; READ must return the current count.

    A WRITE is treated as an absolute set (used by ``__system__`` init events).
    This is where lost updates surface: N increments from 0 must read as N.
    """

    def initial(self) -> Any:
        return 0

    def apply(self, state: Any, event: Event) -> Any:
        if event.op_type is OpType.INC:
            return state + 1
        if event.op_type is OpType.WRITE:
            return event.value
        if event.op_type is OpType.READ:
            if event.value is not UNCHECKED and event.value != state:
                raise SpecViolation(f"READ returned {event.value!r} but counter holds {state!r}")
            return state
        raise SpecViolation(f"counter does not support op {event.op_type}")


class MapRegisterSpec(RegisterSpec):
    """A map is a family of registers keyed by ``event.meta['subkey']``.

    The engine partitions a map object's events by subkey and linearises each
    partition as an independent register (per-key compositionality).
    """


_SPECS: dict[str, type[SequentialSpec]] = {
    "register": RegisterSpec,
    "counter": CounterSpec,
    "map": MapRegisterSpec,
}


def spec_for(object_type: str) -> SequentialSpec:
    try:
        return _SPECS[object_type]()
    except KeyError:  # pragma: no cover - validated upstream in History
        raise ValueError(f"no sequential spec for object_type {object_type!r}") from None


def is_legal_sequential(events: list[Event], spec: SequentialSpec) -> bool:
    """True iff applying ``events`` in order satisfies ``spec`` end to end."""
    state = spec.initial()
    for e in events:
        try:
            state = spec.apply(state, e)
        except SpecViolation:
            return False
    return True
