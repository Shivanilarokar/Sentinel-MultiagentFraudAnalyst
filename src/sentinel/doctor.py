"""Environment and data health check.

Run this first, and run it again whenever something behaves oddly. It answers
the four questions that account for most wasted debugging time:

    Is the model key actually loaded?
    Is the source database present, intact, and refusing writes?
    Does the incident window find the episode, or silently return nothing?
    Does the note timing come back labelled?

The last two are the ones that matter. Both failure modes return zero rows
rather than raising, so nothing tells you they are broken except a check that
looks at the numbers.

    python -m sentinel.doctor
"""

from __future__ import annotations

import os

from sentinel import config, queries
from sentinel.db import init_runtime, read_only, source_hash

# A00985 is the clearest example of the problem in the whole queue: the numbers
# say account takeover, and one case note filed five hours earlier explains it.
SAMPLE = "A00985"


def line(label: str, value: str) -> None:
    print(f"  {label:<22} {value}")


def main() -> None:
    print("\nSENTINEL DOCTOR")
    print("=" * 66)

    # -- 1. environment ----------------------------------------------------
    print("\n1. Environment")
    key = os.getenv("OPENAI_API_KEY", "")
    line("OPENAI_API_KEY", f"loaded, {len(key)} chars" if key else "MISSING")
    line("specialist model", config.SPECIALIST_MODEL)
    line("supervisor model", config.SUPERVISOR_MODEL)
    line("frozen clock", config.today_str())

    # -- 2. the source database -------------------------------------------
    print("\n2. Source database (must be read-only)")
    with read_only() as conn:
        alerts = conn.execute("SELECT COUNT(*) FROM alerts").fetchone()[0]
        accounts = conn.execute(
            "SELECT COUNT(DISTINCT account_id) FROM alerts").fetchone()[0]
        txns = conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
        notes = conn.execute("SELECT COUNT(*) FROM case_notes").fetchone()[0]
    line("alerts", f"{alerts} on {accounts} accounts")
    line("transactions", f"{txns:,}")
    line("case notes", str(notes))
    line("sha256", source_hash()[:16] + "...")

    try:
        with read_only() as conn:
            conn.execute("INSERT INTO alerts (alert_id) VALUES ('X')")
        line("write attempt", "FAILED - the database accepted a write")
    except Exception as exc:
        line("write attempt", f"refused ({exc})")

    init_runtime()
    line("runtime db", str(config.ACTIONS_DB.name) + " ready")

    # -- 3. the incident window -------------------------------------------
    # A window built with SQLite's datetime() returns a space-separated
    # timestamp, while `ts` uses a 'T'. The comparison then matches nothing
    # and reports zero transactions without erroring. This is that check.
    print(f"\n3. Incident window on {SAMPLE}")
    lo, hi = queries.incident_window(SAMPLE)
    activity = queries.get_incident_activity(SAMPLE)
    total = sum(t["amount"] for t in activity)
    line("window", f"{lo}  ->  {hi}")
    line("transactions found", f"{len(activity)}, totalling {total:,.0f}")
    if not activity:
        line("VERDICT", "BROKEN - window matched nothing")
    else:
        for t in activity:
            print(f"      {t['txn_id']}  {t['ts']}  {t['amount']:>10,.0f}  "
                  f"{t['ip_country']}  {t['channel']}")

    # -- 4. the narrative, with its timing label --------------------------
    # Whether a note was filed before or after the incident is the single
    # distinction that decides roughly a third of the queue.
    print(f"\n4. Narrative on {SAMPLE}")
    for n in queries.get_case_notes(SAMPLE):
        line(n["note_id"], f"{n['created_at']}  [{n['timing']}]  by {n['author']}")
        print(f'      "{n["note"]}"')

    alerts_fired = queries.get_alerts(SAMPLE)
    for a in alerts_fired:
        line(a["alert_id"], f"{a['rule_id']} {a['rule_name']}, fired {a['triggered_at']}")

    print("\n" + "=" * 66)
    print("The numbers say account takeover. The note, filed before the alert,")
    print("says phone upgrade verified by video KYC. Closing that gap is the job,")
    print("and no threshold on the numbers can do it.\n")


if __name__ == "__main__":
    main()
