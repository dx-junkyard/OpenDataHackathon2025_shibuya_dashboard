"""probe-agent instrumentation.

AI agents are decorated with `observed(component_id)`. When the probe-agent
Python SDK is installed and `PROBE_ENABLED=true`, calls are traced to the
probe-agent Control Server (and can be shadow-compared there). Otherwise the
decorator is a no-op so the app runs without probe-agent.
"""
from __future__ import annotations

import os
from typing import Any, Callable, Optional, TypeVar

F = TypeVar("F", bound=Callable[..., Any])

try:  # pragma: no cover - depends on the optional SDK
    from probe_agent import probe as _probe
except ImportError:  # pragma: no cover
    _probe = None


def enabled() -> bool:
    return _probe is not None and os.getenv("PROBE_ENABLED", "false").lower() == "true"


def observed(component_id: str, candidate: Optional[Callable[..., Any]] = None) -> Callable[[F], F]:
    """Trace `fn` as `component_id`. `candidate` is an alternative implementation
    that probe-agent runs on the same inputs when the component is in `shadow`
    mode; its result is only compared, never returned to the user."""

    def wrap(fn: F) -> F:
        if not enabled():
            return fn
        return _probe(component_id=component_id, candidate=candidate)(fn)  # type: ignore[misc]

    return wrap
