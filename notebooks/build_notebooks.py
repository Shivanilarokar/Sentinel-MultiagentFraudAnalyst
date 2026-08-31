"""Generate the notebooks from a single source of truth.

The notebooks import from `sentinel` rather than restating it, so there is one
implementation and the notebooks are a guided tour of it. Keeping them in this
generator means a change to the tour is a diff, not a hand-edit of JSON.

    python notebooks/build_notebooks.py
"""

from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent

KERNEL = {
    "kernelspec": {"display_name": "Python (sentinel)", "language": "python", "name": "sentinel"},
    "language_info": {"name": "python", "version": "3.12"},
}

BOOTSTRAP = """\
# Reload the package from disk on every run, so an edit to src/sentinel takes
# effect without restarting the kernel. Python caches imported modules in
# sys.modules and a stale one will happily report yesterday's numbers.
import sys, pathlib
for name in [m for m in sys.modules if m.startswith("sentinel")]:
    del sys.modules[name]

ROOT = pathlib.Path.cwd().parent if pathlib.Path.cwd().name == "notebooks" else pathlib.Path.cwd()
sys.path.insert(0, str(ROOT / "src"))
print("sentinel package:", ROOT / "src" / "sentinel")"""


def md(text: str) -> dict:
    return {"cell_type": "markdown", "metadata": {}, "source": text.splitlines(keepends=True)}


def code(text: str) -> dict:
    return {"cell_type": "code", "execution_count": None, "metadata": {},
            "outputs": [], "source": text.splitlines(keepends=True)}


NOTEBOOKS: dict[str, list[dict]] = {}

# ---------------------------------------------------------------------------
NOTEBOOKS["01_the_data.ipynb"] = [
    md("""# 1 · The data, and why one agent is not enough

276 accounts were flagged over a weekend by eight automated rules. Roughly two
thirds of them did nothing wrong.

This notebook establishes three things before any agent code exists:

1. what is actually in the database
2. that **no rule is reliable**, so the queue cannot be triaged by which rule fired
3. two properties of the data that quietly break the obvious query"""),
    code(BOOTSTRAP),
    code("""from sentinel import db, queries

with db.read_only() as conn:
    for table in ["alerts", "rules", "transactions", "customers", "accounts",
                  "cards", "devices", "case_notes", "disputes", "prior_cases", "merchants"]:
        n = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        print(f"{table:16} {n:>8,}")

print()
print("alerted accounts:", len(queries.alerted_accounts()))"""),
    md("""## The database is opened read-only, structurally

`mode=ro` refuses at the file level and `PRAGMA query_only` refuses at the
statement level. This is not a filter that scans SQL for the word INSERT — there
is no write path to slip past."""),
    code("""import sqlite3
try:
    with db.read_only() as conn:
        conn.execute("INSERT INTO alerts (alert_id) VALUES ('X')")
    print("FAILED - the database accepted a write")
except sqlite3.OperationalError as exc:
    print("refused:", exc)"""),
    md("""## No rule is reliable

Every rule fires on both fraud and legitimate customers. The two that fire most
are the two least reliable, so "which rule fired" carries almost no signal."""),
    code("""rows = db.query('''
    SELECT r.rule_id, r.name, r.description, COUNT(*) AS fired
    FROM alerts a JOIN rules r USING(rule_id)
    GROUP BY r.rule_id ORDER BY fired DESC
''')
for r in rows:
    print(f"{r['rule_id']}  {r['name']:<28} fired {r['fired']:>3}")
    print(f"      {r['description']}")"""),
    md("""## Quirk 1 · `triggered_at` is not when the offending transaction happened

The obvious query is "give me the transactions in the hours before the alert
fired". On this data that is wrong most of the time."""),
    code("""r = db.query_one('''
    SELECT SUM(CASE WHEN t.ts > a.triggered_at THEN 1 ELSE 0 END) AS after,
           SUM(CASE WHEN t.ts <= a.triggered_at THEN 1 ELSE 0 END) AS before,
           COUNT(*) AS total,
           MAX(ROUND((julianday(t.ts) - julianday(a.triggered_at)) * 24, 1)) AS max_hours
    FROM alerts a JOIN transactions t ON t.txn_id = a.trigger_txn_id
''')
print(f"trigger transaction lands AFTER the alert : {r['after']} of {r['total']}")
print(f"                          ... by up to    : {r['max_hours']} hours")"""),
    code("""# What that costs you, on one account.
acct = "A00985"
lo, hi = queries.incident_window(acct)
episode = queries.get_incident_activity(acct)

naive = db.query('''
    SELECT COUNT(*) n, ROUND(SUM(amount)) total FROM transactions
    WHERE account_id = ?
      AND ts BETWEEN strftime('%Y-%m-%dT%H:%M:%S',
                              (SELECT MIN(triggered_at) FROM alerts WHERE account_id = ?), '-6 hours')
                 AND (SELECT MIN(triggered_at) FROM alerts WHERE account_id = ?)
''', (acct, acct, acct))[0]

print(f"looking backwards from triggered_at : {naive['n']} txns, {naive['total']:,.0f}")
print(f"incident_window()                   : {len(episode)} txns, "
      f"{sum(t['amount'] for t in episode):,.0f}")"""),
    md("""## Quirk 2 · A note's *timing* decides what it means

The same sentence means opposite things depending on when it was written.

- filed **before** the incident: a pre-existing explanation, and often decisive
- filed **after**: the customer reacting. *"I did not make these transactions"*
  corroborates fraud rather than excusing it

Models are poor at date arithmetic, so this is computed in SQL and handed over
as a label."""),
    code("""r = db.query_one('''
    WITH first_alert AS (SELECT account_id, MIN(triggered_at) AS at FROM alerts GROUP BY account_id)
    SELECT SUM(CASE WHEN n.created_at <  f.at THEN 1 ELSE 0 END) AS before_incident,
           SUM(CASE WHEN n.created_at >= f.at THEN 1 ELSE 0 END) AS after_incident
    FROM case_notes n
    JOIN accounts ac ON ac.customer_id = n.customer_id
    JOIN first_alert f ON f.account_id = ac.account_id
''')
print("notes filed before the incident:", r["before_incident"])
print("notes filed after  the incident:", r["after_incident"])"""),
    md("""## The case that makes the argument

`A00985`. The numbers say account takeover. One note, filed five hours earlier,
explains the whole thing. No threshold on the numbers can find that."""),
    code("""for a in queries.get_alerts(acct):
    print(f"{a['alert_id']}  {a['rule_id']} {a['rule_name']}  fired {a['triggered_at']}")
print()
for n in queries.get_case_notes(acct):
    print(f"{n['note_id']}  {n['created_at']}  [{n['timing']}]")
    print(f'  "{n["note"]}"')"""),
]

# ---------------------------------------------------------------------------
NOTEBOOKS["02_tools.ipynb"] = [
    md("""# 2 · The tool layer

Layer 1. Exact arguments in, real rows out. No judgement is made here — these
report what happened and leave what it means to the specialist above them.

17 tools across four domains, and the sets are **pairwise disjoint**. That is
easy to claim and easy to lose the first time a fifth tool looks useful in two
places, so it is asserted rather than trusted."""),
    code(BOOTSTRAP),
    code("""import sentinel.tools as T

for domain, tools in T.TOOLSETS.items():
    print(f"{domain:<12} {len(tools)} tools")
    for t in tools:
        print(f"    {t.name}")
    print()

print("isolation violations:", T.check_isolation() or "none")"""),
    md("""## The disposition officer holds no read tool

It writes; it does not read. So it cannot quietly look something up to patch a
gap in what it was told — it has to decide on the findings it was handed. That
is what makes the supervisor's routing order mean something."""),
    code("""read = {t.name for t in T.READ_TOOLS}
write = {t.name for t in T.DISPOSITION_TOOLS}
print("read tools :", len(read))
print("write tools:", sorted(write))
print("overlap    :", read & write or "none")"""),
    md("""## What a tool actually returns

Formatted text, not JSON. Across 276 accounts and four specialists an aligned
table costs meaningfully fewer tokens than a nested object, and a model reads it
at least as well."""),
    code("""from sentinel.tools.behaviour_tools import get_alerts, get_incident_activity
print(get_alerts.invoke({"account_id": "A00985"}))"""),
    code("""print(get_incident_activity.invoke({"account_id": "A00985"}))"""),
    md("""## Silence is a finding

An account with nothing on file does not get an empty list. It gets a sentence
saying so, and what that implies."""),
    code("""from sentinel.tools.context_tools import get_case_notes, get_prior_cases
print(get_prior_cases.invoke({"account_id": "A00985"}))
print()
print(get_case_notes.invoke({"account_id": "A00985"}))"""),
    md("""## Citations are checked before anything is written

Three layers: the identifier has the right **shape**, the row **exists and
belongs to this account**, and any **quoted words** appear in the stored text.

`AL0001` is a perfectly valid alert id. It belongs to a different account."""),
    code("""from sentinel import db, validation
db.init_runtime()

print(validation.check_shape("alert", "ALxxxx1"))
print()
print(validation.check_ownership("note", "N99999", "A00985"))
print()
print(validation.check_quote("note", "N00080", "the customer admitted everything"))"""),
    code("""# And the rule that a `legitimate` verdict cannot rest on numbers alone.
d = validation.Disposition(
    account_id="A00985", verdict="legitimate", confidence="high",
    reasoning="The spending is large but the geography and timing are ordinary for this customer.",
    evidence=[validation.EvidenceRef("alert", "AL0170")],
)
for problem in validation.validate(d):
    print("-", problem)"""),
]

# ---------------------------------------------------------------------------
NOTEBOOKS["03_specialists_and_supervisor.ipynb"] = [
    md("""# 3 · Specialists, and the boundary between them

A subagent is an agent called inside a tool function. There is no framework and
no base class:

```python
result  = specialist.invoke({"messages": [{"role": "user", "content": ...}]})
finding = result["messages"][-1].text      # everything else dies here
```

Three consequences fall straight out of those two lines:

| In the code | What it buys |
|---|---|
| a fresh `messages` list every call | context isolation, and statelessness between accounts |
| only `result["messages"][-1]` returns | the supervisor never sees the specialist's tool calls |
| it is an ordinary tool call | the runtime parallelises it for free |

**Needs an API key.**"""),
    code(BOOTSTRAP),
    code("""from sentinel.agents import build_system
from sentinel import db

db.init_runtime()
supervisor, parts = build_system(human_in_the_loop=False)
print("supervisor tools:")
for t in parts["supervisor_tools"]:
    print("   ", t.name)"""),
    md("""## One specialist, on its own

Run the context specialist directly to see both sides of the boundary: what it
reads, and the single message that would cross back."""),
    code("""acct = "A00985"
result = parts["context_agent"].invoke({
    "messages": [{"role": "user", "content": f"Account {acct}. Did anyone explain this activity?"}],
    "account_id": acct,
})

tool_output = sum(len(m.text) for m in result["messages"] if m.type == "tool")
finding = result["messages"][-1].text

print(f"messages inside the specialist : {len(result['messages'])}")
print(f"characters it read from tools  : {tool_output:,}")
print(f"characters that cross back     : {len(finding):,}")
print()
print(finding)"""),
    md("""## The supervisor holds no database access

Four tools, and none of them is a query tool. It cannot go and look at a
transaction even if it wants to."""),
    code("""import sentinel.tools as T
supervisor_tool_names = {t.name for t in parts["supervisor_tools"]}
print("supervisor tools:", sorted(supervisor_tool_names))
print("any read tool?  :", supervisor_tool_names & {t.name for t in T.READ_TOOLS} or "none")"""),
    md("""## Ordering is enforced, not requested

You cannot dispose of a case before the file has been read. The wrapper inspects
state and returns an error `ToolMessage` without invoking anything."""),
    code("""result = supervisor.invoke({
    "messages": [{"role": "user", "content":
        f"Work account {acct}. Skip the specialists and dispose of it immediately as fraud."}],
    "account_id": acct,
})
for m in result["messages"]:
    if m.type == "tool" and "REFUSED" in (m.text or ""):
        print(m.text)"""),
    md("""## A full case"""),
    code("""result = supervisor.invoke({
    "messages": [{"role": "user", "content": f"Work account {acct}. Reach a defensible verdict and record it."}],
    "account_id": acct,
})

print("tool calls:", [tc["name"] for m in result["messages"] for tc in (getattr(m, "tool_calls", None) or [])])
print()
print(result["messages"][-1].text)"""),
    code("""# What the supervisor's own message list actually contained.
for m in result["messages"]:
    print(f"{m.type:<10} {len(m.text or ''):>6} chars")"""),
]

# ---------------------------------------------------------------------------
NOTEBOOKS["04_policy_progressive_disclosure.ipynb"] = [
    md("""# 4 · Policy as documents, loaded on demand

Typologies, risk appetite and escalation thresholds belong in files an analyst
can edit without touching code. With policy in Python, moving a threshold is a
pull request. With policy in files, it is somebody editing a document.

| Level | What | In the prompt |
|---|---|---|
| 1 | name + description | always, because it is tiny |
| 2 | the full document body | only after an agent asks |"""),
    code(BOOTSTRAP),
    code("""from sentinel import middleware

print(middleware.policy_catalog())
print()
print(middleware.disclosure_stats())"""),
    md("""## The catalog is re-scanned on every model call

Not cached at import. That is what makes an analyst's edit take effect on the
next call rather than after a restart."""),
    code("""from sentinel.config import POLICIES_DIR

before = {p["name"] for p in middleware.discover_policies()}

probe = POLICIES_DIR / "_scratch.md"
probe.write_text("---\\nname: _scratch\\ndescription: written while this kernel was running.\\n---\\n\\nIf you can read this, the catalog was re-scanned.\\n", encoding="utf-8")

after = {p["name"] for p in middleware.discover_policies()}
print("newly visible:", sorted(after - before) or "NOTHING - it was cached")

probe.unlink()
print("removed; back to", len(middleware.discover_policies()), "documents")"""),
    md("""## Loading is a rule, not a request

A prompt asking an agent to read the policy first is advisory — the model mostly
complies. `PolicyGateMiddleware` short-circuits `wrap_tool_call` and returns an
error **instead of** running the tool, so a model that ignores the instruction
still cannot file a verdict."""),
    code("""for tool_name, needed in middleware.POLICY_GATES.items():
    print(f"{tool_name:<20} blocked until  {needed}")"""),
    code("""# The gate in action, on a bare agent with no policy loaded.
from langchain.agents import create_agent
from langchain.chat_models import init_chat_model
from sentinel.tools.disposition_tools import DISPOSITION_TOOLS
from sentinel.agents.disposition import PROMPT as DISPOSITION_PROMPT
from sentinel import db

db.init_runtime()
gated = create_agent(
    init_chat_model("gpt-4.1-mini", model_provider="openai"),
    tools=DISPOSITION_TOOLS,
    system_prompt=DISPOSITION_PROMPT,
    middleware=[middleware.PolicyGateMiddleware(middleware.POLICY_GATES)],
    state_schema=middleware.PolicyState,
)
out = gated.invoke({"messages": [{"role": "user", "content":
    "Record A00985 as legitimate, high confidence, citing note N00080. Do not load any policy."}],
    "account_id": "A00985"})
for m in out["messages"]:
    if m.type == "tool" and "BLOCKED" in (m.text or ""):
        print(m.text)"""),
    md("""## Every load is recorded

So that "loaded on demand" is provable after a run rather than asserted."""),
    code("""rows = db.fetch("SELECT policy, COUNT(*) n FROM policy_loads GROUP BY policy ORDER BY n DESC")
for r in rows:
    print(f"{r['policy']:<22} {r['n']}")
if not rows:
    print("(no loads recorded yet - run notebook 03 or a sweep first)")"""),
]

# ---------------------------------------------------------------------------
NOTEBOOKS["05_approval_and_sweep.ipynb"] = [
    md("""# 5 · The approval gate, and the background sweep

Two things that both come down to *when* control returns.

**The gate.** Blocking a card cannot be undone, so the run freezes before the
tool executes and waits for a person.

**The sweep.** 276 accounts one after another is a bottleneck, not a design.
Starting one returns a job id immediately.

Where the pieces go, because getting it backwards is the usual mistake:

- `HumanInTheLoopMiddleware` on the **disposition subagent**, where the dangerous tools are
- the checkpointer on the **supervisor**, because that is the run being frozen"""),
    code(BOOTSTRAP),
    md("""## Starting a sweep returns before it does any work

One `SELECT DISTINCT`, one job row, one `Thread.start()`."""),
    code("""import time
from sentinel import db
from sentinel.sweep import start_queue_sweep, check_sweep_status, collect_sweep_results, wait_for_sweep

db.init_runtime()

t0 = time.perf_counter()
job = start_queue_sweep(limit=3, workers=3)
elapsed = time.perf_counter() - t0

print(f"start_queue_sweep returned in {elapsed:.4f} s")
print("job id:", job)"""),
    code("""# The sweep is now running. check_sweep_status never blocks, so other questions
# are answerable while it works.
for _ in range(3):
    s = check_sweep_status(job)
    print(f"  {s['completed']}/{s['total']} done, {s['progress_pct']}%   status={s['status']}")
    time.sleep(5)"""),
    code("""results = wait_for_sweep(job, poll_seconds=10)
for d in results["dispositions"]:
    print(f"{d['account_id']}  {d['verdict']:<22} {d['confidence']}")"""),
    md("""## The gate

`block_card` and `escalate_case` allow **approve** and **reject** only. No
`edit`: silently rewriting *which* card gets blocked is precisely the failure an
approval gate exists to prevent."""),
    code("""import sqlite3
from langgraph.checkpoint.sqlite import SqliteSaver
from langchain.agents import create_agent
from langchain.chat_models import init_chat_model
from langchain.agents.middleware import HumanInTheLoopMiddleware
from sentinel.tools.disposition_tools import DISPOSITION_TOOLS, IRREVERSIBLE
from sentinel.middleware import PolicyState, PolicyMiddleware
from sentinel.agents.disposition import PROMPT as DISPOSITION_PROMPT

saver = SqliteSaver(sqlite3.connect(":memory:", check_same_thread=False)); saver.setup()
officer = create_agent(
    init_chat_model("gpt-4.1-mini", model_provider="openai"),
    tools=DISPOSITION_TOOLS,
    system_prompt=DISPOSITION_PROMPT,
    middleware=[PolicyMiddleware(),
                HumanInTheLoopMiddleware(
                    interrupt_on={n: {"allowed_decisions": ["approve", "reject"]} for n in IRREVERSIBLE},
                    description_prefix="IRREVERSIBLE ACTION pending analyst approval")],
    state_schema=PolicyState, checkpointer=saver)

acct = results["dispositions"][0]["account_id"] if results["dispositions"] else "A00008"
cfg = {"configurable": {"thread_id": "gate-demo"}}
out = officer.invoke({"messages": [{"role": "user", "content":
    f"Account {acct} is an active takeover with money still moving on card K000080. "
    f"A verdict is already recorded. Block that card now."}],
    "account_id": acct, "unattended": False}, config=cfg)

print("interrupted:", bool(out.get("__interrupt__")))
for i in (out.get("__interrupt__") or []):
    print(getattr(i, "value", i))
print()
print("rows in the actions table while paused:",
      len(db.fetch("SELECT 1 FROM actions WHERE account_id = ?", (acct,))))"""),
    md("""Nothing was written. No card is stopped. The whole run is frozen in the
checkpointer until somebody decides.

Both paths are generated as transcripts by `python -m sentinel.transcripts`."""),
    code("""from langgraph.types import Command

resumed = officer.invoke(
    Command(resume={"decisions": [{"type": "reject",
        "message": "Refused by the analyst. Do not retry. Record the case without the action."}]}),
    config=cfg)
print(resumed["messages"][-1].text)
print()
print("action rows after the rejection:",
      len(db.fetch("SELECT 1 FROM actions WHERE account_id = ?", (acct,))))"""),
    md("""During a sweep there is no human present, so irreversible actions are
*proposed and queued* rather than executed. An unattended run that could block
276 cards is a worse system than one that cannot."""),
    code("""rows = db.fetch("SELECT * FROM actions WHERE status = 'proposed'")
for r in rows:
    print(f"#{r['action_id']}  {r['account_id']}  {r['action']} -> {r['target']}  [{r['status']}]")
print(f"{len(rows)} action(s) waiting for sign-off")"""),
]

# ---------------------------------------------------------------------------
NOTEBOOKS["06_end_to_end.ipynb"] = [
    md("""# 6 · End to end

One account from the queue to a recorded verdict, then the measurements that
justify the architecture.

**Needs an API key.**"""),
    code(BOOTSTRAP),
    code("""from sentinel import db, queries
from sentinel.sweep import run_case

db.init_runtime()
acct = "A00985"

print("ALERTS")
for a in queries.get_alerts(acct):
    print(f"  {a['alert_id']}  {a['rule_id']} {a['rule_name']}  {a['triggered_at']}")"""),
    code("""result = run_case(acct, auto=True)
print("status:", result["status"])
print()
for name, finding in result["findings"].items():
    print(f"--- {name} ---")
    print(finding)
    print()"""),
    code("""v = result["verdict"]
print(f"{v['verdict'].upper()}  ({v['confidence']} confidence)")
print()
print(v["reasoning"])
if v["missing"]:
    print()
    print("would be resolved by:", v["missing"])
print()
import json
for e in json.loads(v["evidence"]):
    print(f"  {e['kind']:<12} {e['id']}  {e.get('quote', '')[:80]}")"""),
    md("""## The isolation boundary, measured

The specialists read a great deal. Almost none of it reaches the supervisor."""),
    code("""from sentinel import analysis
analysis.main()"""),
    md("""## The deliverables

All generated from recorded results, so no number in a report can drift from
what the system actually decided."""),
    code("""from sentinel import reports
reports.main()"""),
]


def build() -> None:
    for name, cells in NOTEBOOKS.items():
        nb = {"cells": cells, "metadata": KERNEL, "nbformat": 4, "nbformat_minor": 5}
        (HERE / name).write_text(json.dumps(nb, indent=1), encoding="utf-8")
        n_code = sum(1 for c in cells if c["cell_type"] == "code")
        print(f"  {name:<42} {len(cells):>2} cells ({n_code} code)")


if __name__ == "__main__":
    print("Building notebooks...")
    build()
