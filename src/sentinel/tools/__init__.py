"""The tool registry, and the isolation it guarantees.

Four specialists, each holding only the tools for its own domain. That is easy
to claim and easy to get wrong the first time a fifth tool looks useful in two
places.

So the four sets are declared here in one place, and `check_isolation()` proves
they are pairwise disjoint, `tests/test_architecture.py` asserts it, and
`python -m sentinel.tools` prints it.

    behaviour     7 tools   reads transactions, devices, geography
    context       4 tools   reads case notes, disputes, prior cases
    network       3 tools   reads shared devices, merchant overlap
    disposition   3 tools   writes only. Holds no read tool at all.

The supervisor appears nowhere in this file, because it holds none of these
tools. It holds four wrappers, one per specialist, and no database access at
all.

    python -m sentinel.tools
"""

from __future__ import annotations

from itertools import combinations

from sentinel.tools.behaviour_tools import BEHAVIOUR_TOOLS
from sentinel.tools.context_tools import CONTEXT_TOOLS
from sentinel.tools.disposition_tools import DISPOSITION_TOOLS, IRREVERSIBLE
from sentinel.tools.network_tools import NETWORK_TOOLS

TOOLSETS = {
    "behaviour": BEHAVIOUR_TOOLS,
    "context": CONTEXT_TOOLS,
    "network": NETWORK_TOOLS,
    "disposition": DISPOSITION_TOOLS,
}

# Every tool that reads the bank's database. The disposition officer holds none
# of these, and the supervisor holds none of them either.
READ_TOOLS = BEHAVIOUR_TOOLS + CONTEXT_TOOLS + NETWORK_TOOLS


def names(tools: list) -> set[str]:
    """The tool names in a set, for comparison and printing."""
    return {t.name for t in tools}


def check_isolation() -> list[str]:
    """Return a list of isolation violations. Empty means the split holds."""
    problems = []

    for a, b in combinations(TOOLSETS, 2):
        overlap = names(TOOLSETS[a]) & names(TOOLSETS[b])
        if overlap:
            problems.append(f"{a} and {b} share tools: {sorted(overlap)}")

    # The disposition officer writes. If it could also read, it would paper over
    # a routing failure by looking things up itself, and the supervisor's
    # ordering would stop meaning anything.
    leaked = names(DISPOSITION_TOOLS) & names(READ_TOOLS)
    if leaked:
        problems.append(f"disposition holds read tools: {sorted(leaked)}")

    return problems


def main() -> None:
    print("\nTOOL ISOLATION")
    print("=" * 66)
    for domain, tools in TOOLSETS.items():
        print(f"\n{domain:<12} {len(tools)} tools")
        for t in tools:
            marker = "  [IRREVERSIBLE]" if t.name in IRREVERSIBLE else ""
            print(f"    {t.name}{marker}")

    total = sum(len(t) for t in TOOLSETS.values())
    print(f"\n{total} tools across {len(TOOLSETS)} domains")

    problems = check_isolation()
    print("\n" + "=" * 66)
    if problems:
        for p in problems:
            print(f"  VIOLATION: {p}")
    else:
        print("  Pairwise disjoint: no tool appears in two domains.")
        print("  Disposition holds no read tool.")
        print("  Each specialist can only ask its own domain's questions.")
    print()


if __name__ == "__main__":
    main()
