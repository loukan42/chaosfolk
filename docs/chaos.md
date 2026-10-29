# Optional chaos policies

Existing runs keep their current users, action budgets, fault pool and replay
workflow. No policy is required. These controls run in Python without a model.
They do not add users, browser actions, automatic replays or token requests.

Use a policy when you need to control injections across users or campaigns.
A rejected injection is skipped immediately with a reason. The engine never
waits for a cooldown, an available slot, a healthy environment or a future window.
Exploration continues within the existing budget.

## Start small

```bash
chaosfolk chaos init --file qa/chaos.json
chaosfolk chaos check qa/chaos.json
chaosfolk launch --url http://localhost:3000 --project shop --level low --chaos-policy qa/chaos.json
```

`init` refuses to overwrite a file. The starter policy caps active injections at
one, total admissions at four, duration at 20 seconds and spaces admissions by
10 seconds. It does not increase the run size or ensure four injections occur.
Continue with the normal `draw`, `humans`, `sheets` and `drawn-faults` workflow.

`chaosfolk chaos init --project shop` instead saves
`<state directory>/projects/shop/chaos-policy.json`. `launch --project shop`
loads that file if present. An explicit `--chaos-policy FILE` takes precedence.
Use authorized local or test environments and synthetic data as usual.

## Simulation and live controls

```bash
chaosfolk launch --url http://localhost:3000 --folder .horde/trial --dry-run
chaosfolk chaos status
chaosfolk chaos pause
chaosfolk chaos pause --end-active
chaosfolk chaos resume
chaosfolk chaos schedule-off
chaosfolk chaos schedule-on
chaosfolk chaos simulate
chaosfolk chaos live
chaosfolk chaos disable
chaosfolk chaos enable
chaosfolk chaos inspect --folder .horde/trial
```

Live controls, including status, require `CHAOSFOLK_LEADER_TOKEN`, like `fault`.
`inspect` reads saved evidence and works after the session ends.

Simulation applies admission rules but logs `chaos-simulated` instead of applying
the fault. Browsers still run and ordinary user actions can still mutate test
data. No real fault-start event is emitted: extraction cannot treat a simulation
as a real outage. Simulation does not reserve the shared environment. Explicitly
configured hooks can still run. Launch's `--dry-run` cannot be overridden by
`live`; for switchable simulation use `dry_run` in a policy or `chaos simulate`.

`pause` and `disable` block future injections. Current faults remain unless
`--end-active` is supplied. That option removes reversible faults and restarts a
managed app when needed; it cannot restore deleted cookies or storage. Faults
that become due while paused are skipped, not queued for resume. `schedule-off`
blocks draws and delayed/action-triggered faults, while allowing immediate
manual `fault` commands. Other rules still apply.

Live commands override corresponding policy fields for this session. File
changes do not reset those overrides. Restart to return to file settings.

## Policy fields

JSON and TOML are supported. Unknown fields and invalid values are rejected.
Unspecified fields preserve existing behavior; hooks and shared coordination
are absent by default.

| Field | Default | Behavior |
| --- | --- | --- |
| `enabled` | `true` | Allow new injections. |
| `schedule_enabled` | `true` | Allow scheduled injections, separate from immediate manual faults. |
| `dry_run` | `false` | Record admitted injections without applying them. |
| `allowed_faults` | unrestricted | Permitted engine fault types; `[]` permits none. |
| `probability` | `1.0` | Admission probability for each otherwise eligible injection, from 0 to 1. |
| `min_interval` | `0` | Seconds between admissions in the same group. |
| `max_active` | unrestricted | Maximum active injections across the session, including recovery. |
| `max_affected_fraction` | `1.0` | Fraction of users affected simultaneously, rounded down to a whole user. |
| `max_injections` | unrestricted | Total admissions in this session, including simulation and failed attempts. |
| `max_fault_duration` | unrestricted | Duration cap in seconds; supplies a duration when absent. Instantaneous effects stay instantaneous. |
| `grouping` | `project` | Cooldown grouping: `project`, `human` or `role`. |
| `groups` | `[]` | Ordered selector rules; first match wins. |
| `exclude` | empty | Glob patterns under `humans`, `roles`, `routes` and `methods`. |
| `forbid_pairs` | `[]` | Fault-type pairs that cannot overlap. |
| `window` | unrestricted | Timezone, weekdays and allowed hours. |
| `reload_interval` | `2` | Seconds between policy reload checks; `0` disables reloading. |
| `shared_state`, `shared_key` | absent | SQLite path and explicit environment name; configure together. |
| `health_check` | absent | Command used as an incident gate. |
| `health_interval` | `15` | Seconds between incident checks when no fault is active. |
| `tracker`, `error_counter` | absent | Commands for injection events and engine errors. |
| `hook_timeout` | `2` | Total deadline per hook including credentials; 0.1–10 seconds. |
| `secret_env` | `{}` | Environment or command providers for hook credentials. |

Example; every field here is optional:

```json
{
  "allowed_faults": ["offline", "slow", "http-error"],
  "probability": 0.5,
  "min_interval": 10,
  "max_active": 1,
  "max_affected_fraction": 0.5,
  "max_injections": 3,
  "max_fault_duration": 15,
  "grouping": "role",
  "groups": [
    {"name": "editors", "roles": ["editor"], "max_active": 1, "min_interval": 20}
  ],
  "exclude": {"humans": ["e*"], "roles": ["observer"]},
  "forbid_pairs": [["offline", "http-error"]]
}
```

Group selectors accept `humans`, `roles` and `routes` (URL paths without query
strings). Specified categories are combined with AND; patterns within a category
use OR. Group rules support `max_active` and `min_interval`. The top-level active
limit still applies across groups.

The fraction limit is local to the session. A global `app-stop` affects every
user and is rejected when it exceeds the limit or any current user matches an
exclusion. Manual faults cannot bypass policy rules. No skipped fault is retried.

Route/method exclusions also apply to intercepted requests and remain in replay
scenarios. Browser-wide and process-wide faults cannot protect individual routes
or methods, so they are rejected when such exclusions are configured. For example,
with excluded routes use `server-down` rather than `offline` or `app-stop`.

The draw's seed still reproduces planned profiles and faults. Admission probability
is sampled within a session; actual admission also depends on policy, incident
checks and shared state. Replays use recorded faults, without sampling again.

## Time windows

```json
{
  "window": {
    "timezone": "Europe/Paris",
    "weekdays": [0, 1, 2, 3, 4],
    "start_hour": 9,
    "end_hour": 17
  }
}
```

Weekdays use Monday=0 through Sunday=6. Start is inclusive, end exclusive.
Overnight windows need separate jobs. Named IANA timezones follow daylight saving
time. On Windows install `chaosfolk[chaos]` if timezone data is missing; UTC works
without the extra. Due injections outside the window are skipped.

## Finite recurring jobs

Registration installs no OS task; jobs start disabled unless explicitly enabled.
The scheduler adds no model invocation. A command you register can invoke one,
so prefer deterministic replays for recurring fix checks. Each job must declare
a finite attempt count, timeout and an authorized `local` or `test` environment.

Example `qa/replay-job.json` (adapt executable and paths):

```json
{
  "name": "shop-regression",
  "argv": ["python", "-m", "chaosfolk", "regression", "run", "qa/scenarios/save.json", "--output", ".horde/recurring"],
  "cwd": "..",
  "environment": "test",
  "interval": 86400,
  "max_runs": 5,
  "timeout": 60,
  "enabled": false
}
```

```bash
chaosfolk chaos schedule add qa/replay-job.json
chaosfolk chaos schedule list
chaosfolk chaos schedule enable shop-regression
chaosfolk chaos schedule run-due
chaosfolk chaos schedule disable shop-regression
chaosfolk chaos schedule remove shop-regression
```

Invoke `run-due` from an existing cron job or Windows Task Scheduler. It starts
at most one due job; `--limit N` allows up to 10. It never waits for a future
window, retries failures or catches up missed runs. Attempts consume `max_runs`,
including crashes. Job windows use the injection window format. The environment
declaration does not verify the target's deployment; register only authorized tests.

Commands run in the foreground, with argument arrays and no detached daemons.
Use an explicit Python executable for the intended environment. Prepare/reset
synthetic fixtures in the foreground script if needed. Jobs get isolated engine
state; logs stay under `<state directory>/chaos-job-logs/` and may contain app data.
The same job cannot overlap during its reserved timeout. Code 124 means timeout.
Combined stdout/stderr logs default to a 10 MiB limit per attempt. Set
`"max_log_bytes"` in the job JSON to an integer from 1 to 67,108,864 (64 MiB)
to change it. If output exceeds the limit, Chaosfolk stops the owned process
tree, retains at most the configured bytes and returns code 125. This cap covers
the captured log; files the command writes itself remain outside this limit.

## Shared environments

```json
{
  "shared_state": "../state/chaos.sqlite3",
  "shared_key": "shop-recette",
  "max_active": 1,
  "min_interval": 30
}
```

Executions sharing a database and key coordinate active limits, group limits,
forbidden pairs and cooldowns atomically. Use the same policy in all participating
jobs. The database path is relative to the policy. Use a reliable local filesystem
shared by those processes; this is not a multi-host lock service. User-fraction and
total-admission limits remain local. Separate engine sessions still need distinct
state directories (`--state-dir` or `CHAOSFOLK_HOME`).

Leases renew every five seconds, expire after 30 seconds following a crash and
are released on normal shutdown. Cooldown history survives release. Database
errors block new injections. Existing faults still follow their duration and
cleanup. Clocks must agree. Use finite fault durations; a crashed engine cannot
promise application recovery.

## Incident, tracking and credential hooks

Hooks are trusted local commands supplied by the policy author, executed without
a shell. `chaos check` never runs them. Use absolute executable/script paths;
relative script paths resolve against the engine's working directory.

```json
{
  "health_check": ["python", "qa/incident_gate.py"],
  "health_interval": 15,
  "tracker": ["python", "qa/record_injection.py"],
  "error_counter": ["python", "qa/count_engine_error.py"],
  "hook_timeout": 2,
  "secret_env": {"MONITOR_TOKEN": {"env": "QA_MONITOR_TOKEN"}}
}
```

The health hook reads JSON on stdin and exits 0 for healthy. Other codes, missing
programs, credential errors and timeouts block admission. Use an independent
incident signal. Checks are cached and do not rerun while an injection is active,
so induced failures do not automatically count as unrelated outages. This is a
gate before new injections, not continuous monitoring or automatic rollback.

Tracker/error hooks receive compact JSON on stdin: event type, injection id,
user id, fault type, reason, group and journal time when present. Typed values,
notes, URL queries, credentials and hook output are omitted. `error_counter`
receives engine failures, not application defects. Hook stdout/stderr are
discarded. Tracker failure increments `hook_errors` without blocking exploration.
At most 16 notification tasks may be pending; excess notifications are dropped
and counted.

For a secret manager use `{"command": ["my-secret-cli", "read", "qa-token"]}`
instead of `{"env": "QA_MONITOR_TOKEN"}`. The program returns the plain secret
on stdout (up to 64 KiB); the hook receives it in the named environment variable.
Captured stdout is read through a bounded pipe and kept in memory. If a provider
exceeds 64 KiB, Chaosfolk stops its owned process tree and raises an
`output-limit` error; it does not spool the excess output to disk. Values never
enter policy evidence or agent prompts. Providers run only for configured hooks.

## Evidence and limits

Policy sessions write `chaos-plan.json`, `chaos-metrics.json` and journal events.
The plan distinguishes planned, simulated, skipped, cancelled, active and completed
faults. `chaos inspect` reads recorded state and reasons. Simulated/skipped faults
never receive real fault-start evidence. Metrics separate successful applications,
simulations, skips, cancellations, engine errors and hook errors. Existing report
and replay proof requirements still apply.

Reloads affect future admissions. Invalid or missing policies block new injections
until corrected; they do not alter active faults or undo instantaneous effects.
Hooks, windows, recurrence and shared coordination add work only when configured.
There are no built-in cloud-instance, Kubernetes or production termination adapters.
