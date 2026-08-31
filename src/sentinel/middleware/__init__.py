"""Everything that wraps an agent without changing what it is.

Three concerns, three modules, because they fire at different moments:

    state       the shape every agent and middleware agrees on
    disclosure  wrap_model_call — puts the policy catalog in the prompt
    gate        wrap_tool_call  — refuses a write until its policy was read
    approval    wrap_tool_call  — freezes the run until a person decides

    python -m sentinel.middleware
"""

from sentinel.middleware.approval import approval_middleware
from sentinel.middleware.disclosure import (
    Policy,
    PolicyMiddleware,
    disclosure_stats,
    discover_policies,
    load_policy,
    policy_catalog,
)
from sentinel.middleware.gate import POLICY_GATES, PolicyGateMiddleware
from sentinel.middleware.state import PolicyState, SupervisorState

__all__ = [
    "POLICY_GATES",
    "Policy",
    "PolicyGateMiddleware",
    "PolicyMiddleware",
    "PolicyState",
    "SupervisorState",
    "approval_middleware",
    "disclosure_stats",
    "discover_policies",
    "load_policy",
    "main",
    "policy_catalog",
]


def main() -> None:
    """Show what is disclosed, what is gated, and prove the catalog is not cached.

        python -m sentinel.middleware
    """
    from sentinel.config import POLICIES_DIR
    from sentinel.tools.disposition_tools import IRREVERSIBLE

    print("\nPOLICY: PROGRESSIVE DISCLOSURE")
    print("=" * 72)

    print("\nLEVEL 1 - names and descriptions, in every system prompt:\n")
    print(policy_catalog())

    stats = disclosure_stats()
    print(f"\n{'-' * 72}")
    print(f"  {stats['documents']} documents")
    print(f"  level 1 catalog : {stats['catalog_chars']:,} chars, always present")
    print(f"  level 2 bodies  : {stats['body_chars']:,} chars, loaded only on request")
    print(f"  withheld        : {stats['withheld_pct']}% of the corpus is absent from")
    print("                    a prompt until an agent actually asks for it")

    print("\nGATED - these tools will not run until the policy is read:")
    for tool_name, policy_name in POLICY_GATES.items():
        print(f"  {tool_name:<20} requires  {policy_name}")

    print("\nAPPROVAL - these freeze the run until a person decides:")
    for tool_name in IRREVERSIBLE:
        print(f"  {tool_name:<20} approve / reject only, no edit")

    # The catalog is re-scanned on every model call, so a file written now is
    # visible on the very next one. No restart, no rebuild.
    print(f"\n{'-' * 72}")
    print("HOT RELOAD - adding a document with the process already running:\n")
    before = {p["name"] for p in discover_policies()}
    probe = POLICIES_DIR / "_demo_probe.md"
    probe.write_text(
        "---\n"
        "name: _demo_probe\n"
        "description: A document created while this process was running.\n"
        "---\n\n"
        "If you can read this line, the catalog was re-scanned, not cached.\n",
        encoding="utf-8",
    )
    try:
        added = {p["name"] for p in discover_policies()} - before
        print(f"  wrote {probe.name}")
        print(f"  next discover_policies() sees: {sorted(added) or 'NOTHING - cached!'}")
        body = next(p for p in discover_policies() if p["name"] == "_demo_probe")
        print(f'  load_policy would return: "{body["content"]}"')
    finally:
        probe.unlink(missing_ok=True)
    print(f"  removed {probe.name}, catalog back to {len(discover_policies())} documents")

    print("\n" + "=" * 72)
    print("Edit any file in src/sentinel/policies/ and behaviour changes on the")
    print("next model call. No code change, no restart, no redeploy.\n")
