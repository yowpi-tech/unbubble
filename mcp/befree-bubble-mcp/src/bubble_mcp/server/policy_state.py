"""Marks the dynamic extent of an agent-facing tool call (UnBubble edition).

`server/policy.py` sets the flag around every call that comes from an agent (stdio server, skill
runner, program runner); `server/tools.call_tool` re-applies the policy to every NESTED tool call
made while the flag is set — readiness checks, runtime smokes and other composite tools dispatch
inner tools through `call_tool`, and those inner calls must not escape the policy. Direct Python
callers (unit tests) never set the flag.
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Iterator

_AGENT_CALL: ContextVar[bool] = ContextVar("unbubble_agent_call", default=False)


def agent_call_active() -> bool:
    return _AGENT_CALL.get()


@contextmanager
def agent_call() -> Iterator[None]:
    token = _AGENT_CALL.set(True)
    try:
        yield
    finally:
        _AGENT_CALL.reset(token)
