# Architecture

Three views: the system as the assignment draws it, the static structure, and what
happens on one case.

---

## 1 · The system

![architecture](architecture.png)

Rendered from the assignment README's own mermaid source, unchanged.

```
Layer 3   supervisor           routes; four tools; no database access
Layer 2   four specialists     natural language in, natural language out
Layer 1   SQLite-backed tools  exact arguments, real rows
```

Two documented deviations from that drawing:

1. **Network also loads policy.** The arrow is missing in the brief, but
   mule-ring-versus-family-tablet is a policy judgement.
2. **The three sweep tools sit on the operator surface, not the supervisor.**
   `RUBRIC.md` caps the supervisor at four tools. The sweep *drives* the supervisor —
   one isolated invocation per account — rather than being called by it.

---

## 2 · Static structure

```mermaid
classDiagram
    direction LR

    class Settings {
        +Path DB_PATH
        +Path ACTIONS_DB
        +str SPECIALIST_MODEL
        +str SUPERVISOR_MODEL
        +int SWEEP_WORKERS
        +float REQUESTS_PER_SECOND
        +date_context() str
        +require_openai_key()
    }

    class ReadOnlyDB {
        -str uri
        +connect() Connection
        +query(sql, params) list
        +scalar(sql, params)
        +sha256() str
        +verify_integrity() tuple
    }

    class ActionsDB {
        +cursor() Cursor
        +query(sql, params) list
        +log(actor, action, detail)
        +reset()
    }

    class Queries {
        <<module - all SQL, no LLM>>
        +incident_window(id) dict
        +alerts_for(id) list
        +trigger_transactions(id) list
        +queue() list
        +profile(id) dict
        +incident_transactions(id) list
        +velocity(id, hours) dict
        +baseline(id) dict
        +geo_pattern(id) list
        +device_usage(id) list
        +limit_utilisation(id) dict
        +case_notes(id) list
        +disputes(id) list
        +prior_cases(id) list
        +shared_devices(id) list
        +device_peers(id) list
        +merchant_overlap(id) list
    }

    class Policy {
        +str name
        +str description
        +str content
    }
    class PolicyCatalogMiddleware {
        +wrap_model_call(request, handler)
    }
    class PolicyGateMiddleware {
        -dict required
        +wrap_tool_call(request, handler)
    }
    class HardRules {
        +ID_PATTERNS
        +ALLOWED_ACTIONS
        +check_disposition(...) str
        +requires_approval(action) bool
    }

    class BehaviourAgent {
        +PROMPT
        +build(model)
    }
    class ContextAgent {
        +PROMPT
        +build(model)
    }
    class NetworkAgent {
        +PROMPT
        +build(model)
    }
    class DispositionAgent {
        +PROMPT
        +build(model, human_in_the_loop)
    }
    class Supervisor {
        +PROMPT
        +build_sentinel() tuple
    }
    class Boundary {
        +consult(agent, name, account_id, question, tool_call_id) Command
        +final_text(result) str
    }
    class SupervisorState {
        +account_id
        +findings
        +specialists_consulted
    }

    class CaseRunner {
        +run_case(account_id) CaseResult
        +resume_case(account_id, decisions) CaseResult
        +describe_interrupt(interrupt) dict
    }
    class SweepRunner {
        +start_queue_sweep(limit, workers) dict
        +check_sweep_status(job_id) dict
        +collect_sweep_results(job_id) dict
    }

    class Disposition {
        +verdict
        +confidence
        +reasoning
        +action
        +evidence
        +information_required
    }
    class EvidenceRef {
        +kind
        +ref_id
        +quote
        +detail
    }

    class EvidenceAuditor {
        +check_ref(account_id, ref) RefCheck
        +refusal_for(account_id, refs) str
        +audit_all() dict
    }
    class LookalikeFinder {
        +signature(account_id) str
        +separated_pairs() list
    }
    class TokenModel {
        +source_material(account_id) dict
        +single_agent_estimate() dict
    }
    class UsageLedger {
        <<in db.py - primitives only>>
        +record_usage(account_id, agent, ...) None
        +usage_totals() dict
    }

    Queries --> ReadOnlyDB

    BehaviourAgent --> Queries : via @tool
    ContextAgent --> Queries : via @tool
    NetworkAgent --> Queries : via @tool
    DispositionAgent --> HardRules
    DispositionAgent --> EvidenceAuditor : validates citations
    DispositionAgent --> ActionsDB : writes

    BehaviourAgent --> PolicyCatalogMiddleware
    ContextAgent --> PolicyCatalogMiddleware
    NetworkAgent --> PolicyCatalogMiddleware
    DispositionAgent --> PolicyGateMiddleware
    PolicyCatalogMiddleware --> Policy
    PolicyGateMiddleware --> Policy

    Supervisor --> Boundary
    Boundary --> BehaviourAgent
    Boundary --> ContextAgent
    Boundary --> NetworkAgent
    Boundary --> DispositionAgent
    Boundary --> UsageLedger
    Supervisor --> SupervisorState

    CaseRunner --> Supervisor
    SweepRunner --> CaseRunner
    SweepRunner --> ActionsDB

    Disposition "1" --> "*" EvidenceRef
    EvidenceAuditor --> ReadOnlyDB
    LookalikeFinder --> Queries
    TokenModel --> UsageLedger
```

Note what the diagram does *not* contain: an edge from `Supervisor` to `Queries` or
to either database. That absence is the requirement, and `tests/test_architecture.py`
asserts it two ways - by parsing the supervisor module's import graph, and by reading
which tool objects the supervisor is actually handed.

---

## 3 · One case

```mermaid
sequenceDiagram
    autonumber
    participant U as Analyst
    participant S as Supervisor
    participant B as Behaviour
    participant C as Context
    participant N as Network
    participant D as Disposition
    participant H as Human

    U->>S: Work account A00985
    S->>B: is this spending normal for this customer?
    activate B
    Note over B: 7 tool calls, hundreds of rows,<br/>all on its own message list
    B-->>S: FINDING only (~1,300 chars)
    deactivate B
    Note over S: numbers say fraud

    S->>C: did anyone already explain this?
    activate C
    Note over C: reads notes via customer_id,<br/>loads narrative_reading policy
    C-->>S: FINDING only - note N00080, filed before the incident
    deactivate C
    Note over S: context says legitimate

    S->>N: is the account acting alone?
    N-->>S: FINDING only - isolated

    S->>D: dispose, with all three findings
    activate D
    Note over D: gate: evidence_standards must be loaded<br/>before record_disposition will run
    D->>D: record_disposition(...)
    Note over D: shape + ownership + quote checks
    D-->>H: interrupt BEFORE block_card executes
    deactivate D
    Note over S: whole run frozen in the checkpointer<br/>nothing written
    H-->>D: Command(resume={id: approve})
    D-->>S: executed, approved_by=analyst
    S-->>U: verdict, with the evidence on both sides
```

**Order matters and is enforced.** `consult_disposition_officer` reads
`specialists_consulted` from state and refuses while `context` is absent — a verdict
written before anyone looked for an explanation is the exact failure this desk exists
to prevent.

---

## 4 · Where the saving comes from

```
supervisor messages: [ system,
                       human("Work A00985"),
                       ai(tool_call behaviour), tool("FINDING: ...")   <- ~1,300 chars
                       ai(tool_call context),   tool("FINDING: ...")   <- ~1,100 chars
                       ai(tool_call network),   tool("FINDING: ...")   <-   ~460 chars
                       ai(tool_call disposition), tool("FINDING: ...")
                       ai(final answer) ]
```

Each specialist's tool results — the actual database rows — never appear in that list.
They live on the specialist's own message list, which is discarded when
`consult()` returns.

Measured on one case: **45,317 characters produced inside, 4,833 crossed, 89.3%
discarded.** `sentinel analyse tokens` reports it for any run;
`WRITEUP.md` carries the figure for the full sweep alongside the derived
single-agent comparison.

---

## 5 · Control points

Every guarantee in this system is code, not prompt. In the order they fire:

| Point | Mechanism | File |
|---|---|---|
| Source data cannot be written | `mode=ro` URI + `PRAGMA query_only` | `db.py` |
| Supervisor cannot query | no repository import exists | `agents/supervisor.py` |
| Specialists cannot cross domains | `DOMAIN_TOOLS`, asserted disjoint | `tools/__init__.py` |
| Context before disposition | state check → error `ToolMessage` | `agents/supervisor.py` |
| Policy read before a verdict | `PolicyGateMiddleware` short-circuits the call | `agents/disposition.py` |
| Verdict internally consistent | `check_disposition` | `policy.py` |
| Identifiers well formed | `ID_PATTERNS` | `policy.py` |
| Citations real and owned | `analysis.refusal_for` | `analysis.py` |
| Nothing irreversible unapproved | `HumanInTheLoopMiddleware` before the tool body | `agents/disposition.py` |
| Sweep never acts unattended | `approval_mode="defer"` | `tools/disposition_tools.py` |
