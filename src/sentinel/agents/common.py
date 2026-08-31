"""What every specialist shares.

Only two things, kept here so that changing either changes all four at once: the
sentence that tells a specialist its final message is the whole interface, and
the middleware stack it runs under.
"""

from __future__ import annotations

from sentinel.middleware import PolicyMiddleware

# The single most important instruction in the system. A specialist that
# summarises what it *did* instead of what it *found* silently deletes the
# evidence, and nothing downstream can tell the difference between "there was
# nothing" and "it forgot to say".
FINAL_MESSAGE_RULE = (
    "\n\nYOUR FINAL MESSAGE IS THE ONLY THING THAT REACHES THE SUPERVISOR. "
    "Everything you read dies with this conversation. State your finding in "
    "full: the actual numbers, the actual identifiers, the actual words. A "
    "summary of what you did instead of what you found is a failure — "
    "'I reviewed the transaction history' tells the supervisor nothing."
)


def specialist_middleware() -> list:
    """Read-only specialists see the policy catalog and can load from it.

    They get no gate, because a gate exists to protect a write and they do not
    write anything.
    """
    return [PolicyMiddleware()]
