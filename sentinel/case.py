"""Running one account. The single entry point used by the CLI, the API and the sweep.

There is deliberately no second code path. A sweep is this function called 276
times with a different thread id, which means the queue mode cannot silently
drift from the mode a grader inspects by hand.

The system is built once and cached. Specialists are stateless - each
invocation starts on a fresh message list - so rebuilding four agents and their
model clients per account would cost real time across a sweep and buy nothing.
Isolation comes from the fresh message list, not from a fresh object.
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass, field
from typing import Any

from langgraph.types import Command

from sentinel.agents import build_sentinel
from sentinel.messages import final_message_text
from sentinel.models import Disposition
from sentinel.tools.disposition_tools import load_disposition, set_approval_mode

_SYSTEM: dict[str, Any] = {}

# How many times to re-run a whole account that lost to a rate limit. The SDK
# already retries individual calls; this covers the case where a long agent run
# exhausts those retries partway through.
RATE_LIMIT_ATTEMPTS = 3


def _is_rate_limit(exc: Exception) -> bool:
    text = f"{type(exc).__name__} {exc}".lower()
    return "ratelimit" in text or "rate limit" in text or "429" in text


def get_system(*, human_in_the_loop: bool = True):
    """Build the supervisor once and reuse it. Keyed on the approval mode."""
    key = f"hitl={human_in_the_loop}"
    if key not in _SYSTEM:
        _SYSTEM[key] = build_sentinel(human_in_the_loop=human_in_the_loop)
    return _SYSTEM[key]


def reset_system() -> None:
    """Drop the cached system. Used by tests that change configuration."""
    _SYSTEM.clear()


@dataclass
class CaseResult:
    """The outcome of working one account."""

    account_id: str
    status: str  # completed | awaiting_approval | failed
    summary: str = ""
    disposition: Disposition | None = None
    findings: list[dict] = field(default_factory=list)
    interrupts: list = field(default_factory=list)
    thread_id: str = ""
    elapsed_seconds: float = 0.0
    error: str = ""

    @property
    def awaiting_approval(self) -> bool:
        return self.status == "awaiting_approval"


def thread_for(account_id: str, run: str = "single") -> str:
    """One conversation per account per run, so cases never share state."""
    return f"{run}:{account_id}"


def _final_text(result: dict) -> str:
    return final_message_text(result)


def _collect(account_id: str, result: dict, thread_id: str, elapsed: float) -> CaseResult:
    interrupts = list(result.get("__interrupt__") or [])
    status = "awaiting_approval" if interrupts else "completed"
    return CaseResult(
        account_id=account_id,
        status=status,
        summary=_final_text(result),
        disposition=load_disposition(account_id),
        findings=result.get("findings", []) or [],
        interrupts=interrupts,
        thread_id=thread_id,
        elapsed_seconds=elapsed,
    )


def run_case(
    account_id: str,
    *,
    human_in_the_loop: bool = True,
    approval_mode: str | None = None,
    run: str = "single",
) -> CaseResult:
    """Work one account end to end.

    `approval_mode` controls what an irreversible action does when it is
    reached. 'interactive' pauses for a human. 'defer' records the action as
    proposed and never executes it, which is what a 276-account unattended
    sweep uses.
    """
    set_approval_mode(approval_mode or ("interactive" if human_in_the_loop else "defer"))
    supervisor, _ = get_system(human_in_the_loop=human_in_the_loop)

    thread_id = thread_for(account_id, run)
    config = {"configurable": {"thread_id": thread_id}}

    started = time.time()
    last_error = ""
    for attempt in range(RATE_LIMIT_ATTEMPTS):
        try:
            result = supervisor.invoke(
                {"messages": [{"role": "user", "content": f"Work account {account_id}."}]},
                config=config,
            )
            return _collect(account_id, result, thread_id, time.time() - started)
        except Exception as exc:  # one bad account must never abort a sweep
            last_error = f"{type(exc).__name__}: {exc}"
            if not _is_rate_limit(exc) or attempt == RATE_LIMIT_ATTEMPTS - 1:
                break
            # The provider's ceiling is tokens per minute, so the useful wait is
            # long enough for the window to roll, with jitter so concurrent
            # workers do not all wake together and collide again.
            time.sleep(20 * (attempt + 1) + random.uniform(0, 8))

    return CaseResult(
        account_id=account_id,
        status="failed",
        thread_id=thread_id,
        elapsed_seconds=time.time() - started,
        error=last_error,
    )


def resume_case(
    account_id: str,
    decisions: dict,
    *,
    run: str = "single",
    human_in_the_loop: bool = True,
) -> CaseResult:
    """Resume a paused run with the human's decision.

    `decisions` maps interrupt id to a decision payload, e.g.

        {interrupt_id: {"decisions": [{"type": "approve"}]}}
        {interrupt_id: {"decisions": [{"type": "reject", "message": "why"}]}}

    Approving one gate often reveals the next, so callers loop while the
    result is still awaiting approval.
    """
    supervisor, _ = get_system(human_in_the_loop=human_in_the_loop)
    thread_id = thread_for(account_id, run)
    config = {"configurable": {"thread_id": thread_id}}

    started = time.time()
    try:
        result = supervisor.invoke(Command(resume=decisions), config=config)
    except Exception as exc:
        return CaseResult(
            account_id=account_id,
            status="failed",
            thread_id=thread_id,
            elapsed_seconds=time.time() - started,
            error=f"{type(exc).__name__}: {exc}",
        )

    return _collect(account_id, result, thread_id, time.time() - started)


def describe_interrupt(interrupt) -> dict:
    """Flatten an interrupt into something a CLI or an API can render.

    `args` is the important field: this is the last point at which the
    arguments are still editable, and it is what a human is actually approving.
    """
    requests = []
    value = getattr(interrupt, "value", {}) or {}
    for request in value.get("action_requests", []) or []:
        requests.append(
            {
                "tool": request.get("name"),
                "args": request.get("args"),
                "description": request.get("description", ""),
            }
        )
    return {"interrupt_id": getattr(interrupt, "id", None), "action_requests": requests}
