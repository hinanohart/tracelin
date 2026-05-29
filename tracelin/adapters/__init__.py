"""Trace-format adapters: turn a recorded trace into a tracelin ``History``.

The core never imports an agent framework; adapters are the only place where
format-specific knowledge lives.  v0.1 ships two: :mod:`langgraph` (raw
LangGraph fan-out records) and :mod:`otel_genai` (OpenTelemetry GenAI spans).
"""

from . import langgraph, otel_genai

__all__ = ["langgraph", "otel_genai"]
