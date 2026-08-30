"""Find accounts whose alerts look identical, and see whether we called them apart.

The queue contains matched pairs: two accounts with the same rules firing, the
same device-age profile, the same geography shape - and opposite truths. One is
an account takeover; the other upgraded their phone. Nothing in the numbers
separates them. The only difference is in the text.

A00985 and A00782 are the canonical pair. Both fired R02 on a device registered
hours before a large spend. One has a note filed before the incident recording a
verified phone upgrade; the other has a note filed after it reporting a device
registration the customer did not perform.

This module builds a **deterministic signature** from the numeric facts alone -
deliberately no case notes, because the whole point is to group accounts that
the numbers cannot distinguish - and then reports where our verdicts diverge
inside a group. A divergence is only interesting if the reasoning names the
deciding record, so the report carries that too.
"""

from __future__ import annotations

import json
from collections import defaultdict

from sentinel.db import actions
from sentinel.repositories import alerts_repo, transactions_repo


def _bucket(value: float | None, edges: tuple) -> str:
    if value is None:
        return "na"
    for i, edge in enumerate(edges):
        if value < edge:
            return f"b{i}"
    return f"b{len(edges)}"


def signature(account_id: str) -> str:
    """A signature built only from numbers a rules engine could see.

    Two accounts sharing a signature are, as far as the arithmetic goes, the
    same case. Anything that separates them has to come from the file.
    """
    window = alerts_repo.incident_window(account_id)
    if not window:
        return "no-alerts"

    rules = "+".join(sorted((window["rules_fired"] or "").split(",")))
    velocity = transactions_repo.velocity(account_id, 24)
    baseline = transactions_repo.baseline(account_id)
    devices = transactions_repo.device_usage(account_id)

    youngest = min(
        (d["device_age_hours_at_incident"] for d in devices
         if d.get("device_age_hours_at_incident") is not None),
        default=None,
    )
    ratio = None
    if baseline.get("max_amount") and velocity.get("largest_amount"):
        ratio = velocity["largest_amount"] / baseline["max_amount"]

    return "|".join(
        [
            rules,
            f"txn:{_bucket(velocity.get('txn_count'), (2, 4, 6, 10))}",
            f"ctry:{_bucket(velocity.get('distinct_countries'), (2, 3, 5))}",
            f"night:{'y' if (velocity.get('night_txns') or 0) > 0 else 'n'}",
            f"newdev:{'y' if youngest is not None and youngest < 24 else 'n'}",
            f"ratio:{_bucket(ratio, (1, 5, 20, 100))}",
        ]
    )


def signature_groups(account_ids: list[str] | None = None) -> dict[str, list[str]]:
    """Group alerted accounts by identical signature."""
    accounts = account_ids or alerts_repo.queue()
    groups: dict[str, list[str]] = defaultdict(list)
    for account_id in accounts:
        groups[signature(account_id)].append(account_id)
    return {sig: ids for sig, ids in groups.items() if len(ids) > 1}


def _dispositions() -> dict[str, dict]:
    return {
        r["account_id"]: dict(r)
        for r in actions.query("SELECT * FROM dispositions")
    }


def _deciding_records(row: dict) -> list[str]:
    """The narrative records the reasoning actually leaned on."""
    refs = json.loads(row.get("evidence_json") or "[]")
    return [
        f"{r['kind']}:{r['ref_id']}"
        for r in refs
        if r["kind"] in ("case_note", "dispute", "prior_case")
    ]


def separated_pairs(min_group: int = 2) -> list[dict]:
    """Pairs sharing a signature where our verdicts diverge.

    These are the cases the assignment is built around: the numbers are
    identical and the answer is not. Each entry carries the narrative records
    each side rested on, because a divergence without a named reason is a coin
    flip rather than a reading.
    """
    verdicts = _dispositions()
    pairs = []
    for sig, accounts in signature_groups().items():
        scored = [a for a in accounts if a in verdicts]
        if len(scored) < min_group:
            continue
        for i, left in enumerate(scored):
            for right in scored[i + 1 :]:
                a, b = verdicts[left], verdicts[right]
                if a["verdict"] == b["verdict"]:
                    continue
                pairs.append(
                    {
                        "signature": sig,
                        "a": {
                            "account_id": left,
                            "verdict": a["verdict"],
                            "confidence": a["confidence"],
                            "deciding_records": _deciding_records(a),
                            "reasoning": a["reasoning"],
                        },
                        "b": {
                            "account_id": right,
                            "verdict": b["verdict"],
                            "confidence": b["confidence"],
                            "deciding_records": _deciding_records(b),
                            "reasoning": b["reasoning"],
                        },
                    }
                )
    # Pairs where both sides named a record are the strongest evidence that the
    # system read rather than counted, so surface those first.
    pairs.sort(
        key=lambda p: (bool(p["a"]["deciding_records"]) + bool(p["b"]["deciding_records"])),
        reverse=True,
    )
    return pairs


def summary() -> dict:
    groups = signature_groups()
    verdicts = _dispositions()
    pairs = separated_pairs()
    return {
        "alerted_accounts": len(alerts_repo.queue()),
        "accounts_disposed": len(verdicts),
        "distinct_signatures_with_collisions": len(groups),
        "accounts_in_collision_groups": sum(len(v) for v in groups.values()),
        "separated_pairs": len(pairs),
        "pairs_where_both_sides_cite_a_record": sum(
            1 for p in pairs if p["a"]["deciding_records"] and p["b"]["deciding_records"]
        ),
    }
