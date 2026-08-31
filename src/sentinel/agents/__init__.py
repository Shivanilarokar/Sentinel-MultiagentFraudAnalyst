"""Assembling the three layers.

    Layer 3   supervisor        routes at the domain level. No database access.
    Layer 2   four specialists  natural language in, natural language out
    Layer 1   SQLite tools      exact arguments, real rows

One module per agent, because each one is a prompt plus a toolset and those are
the two things anybody ever wants to change. Editing the context specialist's
three narrative tests should not mean scrolling past the behaviour analyst.

    python -m sentinel.agents
"""

from __future__ import annotations

from functools import lru_cache

from langchain.chat_models import init_chat_model
from langchain_core.rate_limiters import InMemoryRateLimiter

from sentinel.agents import behaviour, context, disposition, network, supervisor
from sentinel.config import (
    REQUESTS_PER_SECOND,
    SPECIALIST_MODEL,
    SUPERVISOR_MODEL,
    require_openai_key,
)

# One limiter, shared by every agent in the process.
#
# The account's ceiling is tokens per minute, and a sweep spends it from several
# worker threads at once. Retries alone do not help: each worker backs off
# independently, they collide again on the way back up, and a burst of 429s
# kills accounts that were halfway through. A limiter in front of the model
# paces the whole process instead, so the ceiling is never reached.
_LIMITER = InMemoryRateLimiter(
    requests_per_second=REQUESTS_PER_SECOND,
    check_every_n_seconds=0.1,
    max_bucket_size=4,          # a small burst is fine; a sustained one is not
)


@lru_cache(maxsize=8)
def _model(name: str):
    """One instance per model name, so they share the limiter above.

    Building a fresh model per account would give each its own limiter, which is
    the same as having none.
    """
    return init_chat_model(
        name, model_provider="openai", max_retries=8, rate_limiter=_LIMITER,
    )


def build_system(
    *,
    human_in_the_loop: bool = True,
    checkpointer: object | None = None,
    specialist_model: str | None = None,
    supervisor_model: str | None = None,
):
    """Assemble the whole system and return `(supervisor, parts)`.

    Two model tiers. The specialists run four times per account across 276
    accounts, so they carry the cheaper one; the supervisor and the disposition
    officer weigh conflicting evidence and write the text that ends up in the
    record.

    Args:
        human_in_the_loop: When True, `block_card` and `escalate_case` pause for
            a person. Set False for the queue sweep, where there is nobody to
            ask — irreversible actions are then proposed and queued rather than
            executed.
        checkpointer: Where a paused run lives while it waits. Goes on the
            supervisor, because that is the run being frozen and thawed; the
            approval middleware goes on the disposition subagent, because that
            is where the irreversible tools are. Getting those two the wrong way
            round gives you nested persistence and an interrupt with nowhere to
            live.

    Returns:
        supervisor: the agent to invoke.
        parts: the individual pieces, so a notebook can inspect or swap one
            layer without rebuilding the rest.
    """
    require_openai_key()
    fast = _model(specialist_model or SPECIALIST_MODEL)
    strong = _model(supervisor_model or SUPERVISOR_MODEL)

    specialists = {
        "behaviour": behaviour.build(fast),
        "context": context.build(fast),
        "network": network.build(fast),
        "disposition": disposition.build(strong, human_in_the_loop=human_in_the_loop),
    }

    agent, tools = supervisor.build(strong, specialists, checkpointer=checkpointer)

    parts = {
        **{f"{name}_agent": a for name, a in specialists.items()},
        "supervisor_tools": tools,
        "human_in_the_loop": human_in_the_loop,
    }
    return agent, parts


def main() -> None:
    """Print the assembled shape without calling a model."""
    from sentinel.tools import READ_TOOLS, TOOLSETS

    print("\nTHE THREE LAYERS")
    print("=" * 66)
    print("\nLayer 3  supervisor")
    for name in ("consult_behaviour_analyst", "consult_context_specialist",
                 "consult_network_analyst", "consult_disposition_officer"):
        print(f"           {name}")
    print(f"\n         database tools held: 0")

    print("\nLayer 2  specialists")
    for domain, tools in TOOLSETS.items():
        print(f"           {domain:<12} {len(tools)} tools")

    print(f"\nLayer 1  {sum(len(t) for t in TOOLSETS.values())} tools, "
          f"{len(READ_TOOLS)} of them read-only")
    print()


if __name__ == "__main__":
    main()
