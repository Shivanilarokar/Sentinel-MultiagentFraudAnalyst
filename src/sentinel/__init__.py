"""Sentinel — multi-agent fraud triage.

Three layers, one responsibility each:

    Layer 3   agents.supervisor      routes at the domain level, holds no SQL
    Layer 2   agents.{behaviour,context,network,disposition}
                                     natural language in, natural language out
    Layer 1   tools/*                SQLite-backed, exact arguments, real rows

The one architectural move that creates this shape is `@tool` wrapping an
agent's `.invoke()`. Everything else is prompt and plumbing.
"""

__version__ = "2.0.0"
