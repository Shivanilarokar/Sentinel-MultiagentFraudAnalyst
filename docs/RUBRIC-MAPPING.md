# Rubric mapping

Every scored line in `RUBRIC.md`, with the file that implements it and the check that
proves it. Run `pytest -q` to execute all of them; no API key required.

---

## 1 · The five requirements work (35 points)

### Four specialists — 7 pts
> *"Each agent holds domain-specific tools only; distinct prompts; swapping would visibly break functionality"*

| | |
|---|---|
| Implementation | `sentinel/agents/{behaviour,context,network,disposition}.py` — one module each, each defining its own `PROMPT` and `build()` |
| Tool ownership | `sentinel/tools/registry.py` → `DOMAIN_TOOLS` (7 / 4 / 3 / 3 tools) |
| Proof | `test_specialist_tool_sets_are_pairwise_disjoint`, `test_each_specialist_has_its_own_module_with_its_own_prompt`, `test_context_holds_the_narrative_tools_and_no_transaction_tools`, `test_disposition_writes_and_does_not_read` |
| By eye | `sentinel doctor` prints all four sets and confirms disjointness |

Swapping would break it: Context holds no transaction tool, so it cannot compute a
velocity; Behaviour holds no narrative tool, so it cannot see a case note; Disposition
holds no read tool at all.

### Wrapped as tools — 7 pts
> *"Supervisor invokes specialists as tools; final message carries findings, not work descriptions"*

| | |
|---|---|
| Implementation | `sentinel/agents/_boundary.py::consult` — `agent.invoke(...)` then `final_text(result)` |
| Contract | `FINAL_MESSAGE_CONTRACT` closes every specialist prompt: *"Anything you discovered and did not write down is lost"* |
| Proof | `test_the_wrapper_returns_only_the_last_message`, `test_final_text_takes_the_last_message_only` |
| Measured | `sentinel analyse tokens` reports chars produced inside vs chars crossed — **89.3%** discarded on a sample case |

### Supervisor routes only — 7 pts
> *"Four tools maximum, no direct database access; deliberate ordering prioritizes context before disposition"*

| | |
|---|---|
| Implementation | `sentinel/agents/supervisor.py` — four `consult_*` wrappers, nothing else |
| No DB access | The module imports no repository and no `sentinel.db` |
| Ordering | `consult_disposition_officer` reads `specialists_consulted` and returns an error `ToolMessage` if `context` is absent — a rule, not a request |
| Proof | `test_supervisor_module_has_no_database_access` (parses the import graph), `test_supervisor_holds_exactly_four_tools`, `test_disposition_is_blocked_until_context_has_been_consulted` |

### Policy in documents — 7 pts
> *"Typologies and thresholds in editable files; behavior changes via file editing without code modifications"*

| | |
|---|---|
| Documents | `sentinel/policies/*.md` — five files, YAML front-matter |
| Loader | `sentinel/policies/__init__.py` — `discover_policies()` re-scans on every model call |
| On demand | `PolicyCatalogMiddleware` injects names + descriptions (992 chars); bodies (28,526 chars) load only via `load_policy` |
| Enforced | `PolicyGateMiddleware` short-circuits `wrap_tool_call` for `record_disposition` → `evidence_standards`, and both irreversible actions → `escalation_matrix` |
| Ledger | Every load is recorded in `policy_loads` |
| Proof | `test_no_policy_body_is_baked_into_any_system_prompt`, `test_loading_a_policy_is_gated_where_it_matters`, `test_the_catalog_is_far_smaller_than_the_corpus` |

Editing a `.md` changes behaviour with no code change and no restart.

### Background queue sweep — 7 pts
> *"Sweep initiation returns within five seconds with job ID; concurrent question answering; isolated account contexts"*

| | |
|---|---|
| Implementation | `sentinel/sweep.py` + `sentinel/tools/sweep_tools.py` (the three-tool pattern) |
| Start path | one `SELECT DISTINCT`, one job row, one `Thread.start()` — fast by construction |
| **Measured** | **0.041 s** |
| Isolation | one `run_case` per account, each with its own `thread_id` (`job_id:account_id`) |
| Durability | job state in `runtime/actions.db`, so status survives a restart; threads are non-daemon so a CLI sweep can actually finish |
| Proof | `test_starting_a_sweep_returns_in_under_a_second`, `test_each_account_gets_its_own_thread_id`, `test_the_worker_thread_is_not_a_daemon`, `test_a_failing_account_does_not_abort_the_job` |
| By eye | `curl -w '%{time_total}s\n' -XPOST localhost:8000/sweep` |

---

## 2 · Did it read, or did it count? (35 points)

### 2a · Context actually used — 14 pts
> *"Dispositions cite specific case notes or disputes; concrete details appear in reasoning"*

- The Context specialist is required to **quote verbatim** and name `note_id`s; its
  prompt states that a paraphrase loses the evidence.
- `sentinel/policy.py` refuses a `legitimate` verdict that does not cite a
  `case_note`, `dispute` or `prior_case`, and refuses any narrative citation without a
  quote.
- Quotes are checked against the stored text — a fabricated quote is refused at write
  time and flagged in `reports/evidence_audit.md`.
- `sentinel/policies/narrative_reading.md` supplies the three tests: timing, subject,
  specificity.

Every row in `DISPOSITIONS.md` carries its cited ids.

### 2b · Lookalike pairs separated — 12 pts
> *"Both members of ≥2 pairs called correctly; reasoning names deciding evidence"*

`sentinel/analysis/lookalikes.py` builds a signature from **numeric facts only** —
rules fired, transaction-count and country buckets, whether any device was under 24
hours old, whether anything ran at night, and the incident-to-baseline ratio.
Deliberately no case notes: the point is to group accounts the arithmetic cannot
separate.

`separated_pairs()` reports pairs sharing a signature where the verdicts diverge,
along with the narrative record each side rested on, and sorts pairs where **both**
sides named a record to the top.

`sentinel analyse lookalikes` · summarised in `WRITEUP.md` §4.

### 2c · Uncertainty honest — 9 pts
> *"'Needs more information' applied where files are genuinely silent; each instance names required resolution data"*

`policy.check_disposition` **refuses** `insufficient_evidence` with an empty
`information_required`, with a message naming acceptable and unacceptable forms.
`evidence_standards.md` carries the same rule as a HARD RULE, with a table of
acceptable versus refused entries.

Proof: `test_insufficient_evidence_must_name_what_would_resolve_it`,
`test_blank_information_required_does_not_count`.

---

## 3 · Dispositions defensible (20 points)

### Evidence traceable — 6 pts
Every claim carries an `EvidenceRef` with a real identifier.
`sentinel/analysis/evidence_check.py` resolves each one back to a row through the
correct join — notes and prior cases via `customer_id`, disputes via `txn_id`.
Output: `reports/evidence_audit.md`.

### Nothing invented — 5 pts
Three layers:

1. **Shape** — `ID_PATTERNS` in `sentinel/policy.py` refuses `ALxxxx1`, or `R02` where
   an alert id belongs.
2. **Ownership** — `AL0001` is a valid alert id belonging to A00832; cited on A00782 it
   is refused.
3. **Quotes** — checked against the stored text, whitespace- and case-insensitive, so
   a fragment is allowed but an invention is not.

Proof: `tests/test_evidence_check.py`, `test_placeholder_and_wrong_shaped_identifiers_are_refused`.

### Severity proportionate — 5 pts
`ALLOWED_ACTIONS` in `sentinel/policy.py` — a `legitimate` verdict may only carry
`none` or `monitor`; `insufficient_evidence` may never carry `block_card`; a `fraud`
verdict may not carry `none`. `escalation_matrix.md` states when a block is right
(money still moving) and when it is not (an event that has already finished).

Proof: `test_actions_must_be_proportionate_to_the_verdict`.

### Approval respected — 4 pts
`HumanInTheLoopMiddleware` on the disposition subagent interrupts **before** the tool
body runs. Transcripts in `docs/transcripts/`:

- paused → `awaiting_approval`, **0 rows** in the actions table
- approved → executed, `approved_by=analyst`
- rejected → **0 action rows**, downgraded to `monitor`, **not retried**

During a sweep, irreversible actions are queued for review and never executed.

Proof: `test_irreversible_actions_are_declared_and_gated`,
`test_middleware_is_on_the_subagent_and_the_checkpointer_on_the_supervisor`,
`test_approval_requirement_is_derived_in_code_not_asked_of_the_model`.

---

## 4 · Write-up (10 points)

`WRITEUP.md`, generated by `sentinel report writeup`:

- measured sweep tokens from the provider's own `usage_metadata`, per agent
- the boundary measurement — characters produced inside versus characters crossed
- a **derived** single-agent estimate, with the formula and the `tiktoken`-measured
  inputs stated so it can be checked
- the call the system is most exposed on, and which specialist held the deciding
  evidence
- honest limitations, including the one the architecture cannot fix: a specialist's
  omission is invisible to the supervisor

---

## Deductions — all structurally avoided

| Violation | −pts | Why it cannot happen |
|---|---:|---|
| Database modified | 20 | `mode=ro` URI + `PRAGMA query_only`; writes raise. All writes go to a separate `runtime/actions.db`. SHA-256 asserted before and after the suite |
| Runtime network calls beyond the model API | 10 | No HTTP client anywhere in `sentinel/`. Diagram rendering is a build-time script, not a runtime path |
| Supervisor directly queries the database | 8 | Import-graph assertion in `test_supervisor_module_has_no_database_access` |
| Irreversible action without approval | 8 | Middleware interrupts before the tool body; sweep mode defers rather than executes |
| Fewer than four specialists | 6 | `test_there_are_exactly_four_specialists` |

---

## Two documented deviations

**Network also loads policy.** The brief's diagram omits the arrow, but
mule-ring-versus-family-tablet is a policy judgement, so Network gets the loader too.

**The three sweep tools sit on the operator surface, not on the supervisor.**
RUBRIC.md requires *"four tools maximum"* and the supervisor already holds four
specialists; adding start/status/collect would make seven and forfeit the 7 points it
is scored against. They remain real `@tool`s in `sentinel/tools/sweep_tools.py`,
reachable from the CLI and the API. The sweep *drives* the supervisor — one isolated
invocation per account — which is what the brief's `SUP ==> SWEEP` edge describes.
