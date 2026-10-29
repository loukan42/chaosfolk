# Product audits

A product audit uses a persistent selection, a task queue, and a local live dashboard.
The Python CLI and browser engine read the same SQLite session. The dashboard does
not call a model or launch agents itself: it controls the run coordinated by the skill.
Commands without an audit session retain the existing free-exploration behavior.

## Choose depth and budget

| Depth | Default QA checks before application discovery | Default actions | Default active time |
| --- | ---: | ---: | ---: |
| Rapide (`quick`) | 27 P1 | 80 | 10 minutes |
| Standard (`standard`) | 57 P1 + P2 | 200 | 20 minutes |
| Approfondi (`deep`) | 69 P1 + P2 + P3 | 600 | 45 minutes |

These are stop limits, not duration estimates or promises of completion. Discovery,
scout reads, user actions and replay steps consume the shared action/time allowance.
Tool invocations through `execute` also consume an action. One deterministic tool
invocation can perform multiple internal operations; this is not a count of HTTP requests.
Changing depth updates untouched default time/action limits and preserves customized
limits. No token limit is assumed. Users can set one when their host provides usage.

The complete checklist has 178 entries: 116 configurable test definitions (including
the 69 QA checks), plus 62 exploration methods, profiles, assertion methods and
execution controls. Methods are tools for the audit; their availability is not
counted as successful execution. P1/P2/P3 classify importance, not bug severity.
The canonical runtime catalog is `chaosfolk/audit_catalog.json`; the repository's
`docs/audit-priorities.json` is its identical readable reference.

```bash
chaosfolk audit-run init --folder .horde/product-audit --depth standard
chaosfolk audit-run dashboard --folder .horde/product-audit
chaosfolk audit-run start --folder .horde/product-audit
chaosfolk launch --url http://localhost:3000 --folder .horde/product-audit --budget 20
```

Open the URL returned by `dashboard` in the host's browser panel before starting
workers. The user can change depth and uncheck tests; those choices survive reloads
and future waves. Tests above the selected level are disabled until that level is
chosen. Reset restores the current level's defaults. Excluded tests keep any earlier
evidence, with a separate `excluded-by-user` status. They never count as coverage of
the selected scope. Disabling a running task prevents its next browser action;
an action already in progress finishes or reaches its normal tool timeout.

The dashboard binds only to loopback and uses a per-session access token. Do not
share `audit-dashboard.json` or its URL outside the local user session.

## Discover the actual product

Follow the reconnaissance and authentication commands in [workflow.md](workflow.md).
Inspect key routes and roles, navigation, forms, files and saved data. Save
`fields e0 --save .horde/product-audit/fields.json` on each meaningful page/state.
This refreshes the queue automatically. Reusing a page's URL updates its inventory;
if multiple states at one URL have different controls, merge their kinds/features
into the inventory and retain the source observations as evidence.

The queue uses detected control kinds and page features, plus explicit prerequisites.
Without sufficient discovery, a missing matching control stays `needs-discovery`.
Only declare discovery complete after accounting for all known product routes and
roles. Inaccessible screens remain blocked or undiscovered, never silently absent.

```bash
chaosfolk audit-run configure --folder .horde/product-audit --input context.json
chaosfolk audit-run refresh --folder .horde/product-audit --complete
```

Example `context.json` (replace the evidence path with a real, nonempty file inside
the audit folder, and enable capabilities only when available and authorized):

```json
{
  "capabilities": ["test-account", "data-api"],
  "promotions": {"iban-checksum": "P1"},
  "applicability": {
    "iban-checksum": {
      "state": "eligible",
      "reason": "The product creates bank mandates; IBAN validation is a core journey.",
      "evidence": ["audit-evidence/product-context.json"]
    }
  }
}
```

Use `not-applicable` only for an established absence, with a reason and evidence.
Use `blocked` for missing access or an unavailable dependency. Explicit eligibility
does not bypass prerequisites. Configuration objects replace the corresponding
saved map/list; include earlier decisions you intend to retain. Context can raise
priority, never lower it to hide unfinished work. Scope decisions remain independent
of user exclusions. Missing test accounts, two accounts, mailbox, data API, managed
app, coordinated sessions, another browser, visual baseline, downloads, PDF, axe,
k6 or Appium stay visible. Login throttling additionally requires the capability
`login-throttling-authorized` after the requested authorization has been established.

## Execute the queue

One task identifies one test on one relevant page, or one product-wide scenario.
Unassigned work remains queued. Claims are transactional, so concurrent workers
cannot receive the same task. Do not start one model agent per check.

```bash
chaosfolk draw --count 3 --budget 20 --seed 42 --objectives "Create and find a project;Change settings" --url http://localhost:3000 --folder .horde/product-audit
chaosfolk humans .horde/product-audit/personas.json
chaosfolk sheets --folder .horde/product-audit --budget 20
```

The saved selection determines agent checks, regardless of legacy theme defaults.
Each wave has new ids (`h00101`, `h00201`, ...); prior personas remain in the session.
Start agents only for the new ids printed by `draw`. Their sheets carry exact tasks,
routes and expected outcomes. Workers choose a task with `check-start TASK_ID`,
exercise it, then use `check-result TASK_ID passed|failed|blocked|inconclusive "..."`.
Results include a local observation record. A failed result still needs the normal
reproduction/control process before it can become a confirmed defect.

`done` and `giveup` requeue unreported tasks. Recover an interrupted worker with
`audit-run release --owner ID --folder ...` only after that worker is stopped.
Do not reclaim an active worker's task or repeatedly retry a known blocker.

The remaining executors are obtained with:

```bash
chaosfolk audit-run next --folder .horde/product-audit --owner coordinator --executor coordinator --limit 5
chaosfolk audit-run next --folder .horde/product-audit --owner inspection --executor audit --limit 5
```

| Work | Executor and execution path |
| --- | --- |
| User journeys and applicable input checks | Agent sheet, browser actions, `check-result`; [checks.md](checks.md) for variations |
| Field structure | `fields` per page; saves measurements automatically |
| Page layout, keyboard and accessibility signals | `audit` per page, appropriate viewports and `--keyboard`; saves measurements automatically |
| Fault scenarios | Coordinator builds an applicable journey and explicit expected outcome; `replay` treatment/control with the selected fault from [faults.md](faults.md) |
| Persistence scenarios | `replay --persist` with reload, revisit, new-tab, local-only, back or retry; inspect actual saved data |
| Account comparison / coordinated access | `compare` or multi-user `extract` then `replay`, using authorized synthetic accounts |
| Browser / visual compatibility | `replay --channel` or `visual`, with installed engines and a real baseline |
| Mailbox, downloaded files, PDF, axe, k6, Appium | Configured `integrations` command from [integrations.md](integrations.md); report unavailable prerequisites as blocked |
| Console / network signals | Read existing browser evidence and apply the relevant assertion to the journey |

Group deterministic inspection by route and reuse its evidence for relevant checks.
Do not launch the same inspection per catalog row. Tool signals enter `measured`,
and the coordinator queue offers them for review. A tool exiting successfully does
not make all its checks pass. Evaluate each expected behavior and untested variant.

Run coordinator test commands through the monitored wrapper:

```bash
chaosfolk audit-run execute --folder .horde/product-audit --task TASK_ID -- replay .horde/product-audit/scenarios/save.json --times 3 --output .horde/product-audit/reproductions/save
```

The task must already be claimed. `execute` records the command output, checks the
shared stop state every 200 ms and terminates only its owned tool process tree on
stop or exclusion. It accepts `fields`, `audit`, `replay`, `vary`, `compare`, `probe`,
`integrations`, `visual` and `regression`. Keep output paths inside the session.
An interrupted tool is inconclusive. It cannot terminate an unrelated server or
an active host model request. Direct tool calls outside this wrapper do not all
have the same stop guarantee; use the wrapper in product audits.

Record the reviewed outcomes in a JSON object or array with `task_id`, `status`,
`summary`, and `evidence` (session-relative paths). Pass the claimed `owner` and
`claim` when recording on behalf of a worker. Passed/failed/measured statuses require
real, nonempty local files; blocked/inconclusive outcomes need a factual summary.

```bash
chaosfolk audit-run record --folder .horde/product-audit --input results.json
chaosfolk audit-run status --folder .horde/product-audit --details
```

Repeat bounded agent waves and coordinator batches while selected tasks remain and
the run permits work. If there are no agent tasks, `draw` refuses to create idle
users. The queue does not auto-install integrations, invent product assertions or
run destructive scenarios merely to clear a row. Use the documented scope and
record a blocker when a selected test cannot run.

Ordinary CLI responses contain only counts, limits and state. To inspect unfinished
work, use `status --pending --limit 25` and then its `next_offset` with `--offset`.
Reserve `--details` for an explicit full export or debugging; do not repeatedly load
the full ledger into the model context. Worker claims already include the instructions
for their tasks.

## Live usage, stop and final report

The dashboard polls once per second (five seconds in a hidden tab), sends a revision
number and receives no payload when unchanged. It reads grouped task counts rather
than the browser journal or full evidence. Time is displayed locally between updates.
Host usage imports are incremental and deduplicated by request id:

```bash
chaosfolk audit-run usage --folder .horde/product-audit --input host-usage.jsonl --complete
chaosfolk audit-run stop --folder .horde/product-audit
```

Usage events use the [integrations usage contract](integrations.md): stable `id`,
`source: "host"`, input/output token counts and optional measured cost/currency.
`--complete` asserts that the import includes every coordinator and worker request
through this observation. Without it, known usage is a lower bound, not a total.
When a token limit is set, absent, incomplete or stale measurements stop new work.
This checks measured usage, not a reservation of future tokens; active host requests
can exceed the threshold. Set host-level request limits where available.

Stop scheduling immediately on a stopped state. Ask the host to interrupt active
agents where that capability exists, let evidence flush, then close the engine and
owned application using the ordinary cleanup commands. Starting the dashboard does
not create a monitoring agent. A CLI `start` or the resume button is required to
continue; a user stop never triggers an automatic retry.

Generate `report` as usual. It includes selected scope, exclusions and unresolved
tests, and writes `audit-coverage.json` with individual task results/evidence.
Completion applies to the discovered, selected scope only. Deep with exclusions,
missing prerequisites or an exhausted budget must not be described as an exhaustive
product certification. Assertion, reproduction and proof standards are identical
at every depth.
