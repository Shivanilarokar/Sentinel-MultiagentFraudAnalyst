"""Checks that run over recorded results rather than over the model's prose.

A specialist's final message is a *claim*. These modules are what tell a claim
from a fact: `evidence_check` resolves every citation back to a database row,
`lookalikes` finds accounts with identical signatures and compares their
verdicts, and `token_model` turns the measured sweep cost into a comparison
with the single-agent alternative.
"""
