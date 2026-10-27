# Replay and evidence

Replays follow recorded browser actions without asking a model. Supply an explicit
expected outcome. The app and its initial data must be available for each trial.
For shared backend state, use `--sequential` and reset or isolate test data.
Use `--environment` to automate preparation and verification before every trial.

## English input format

```json
{
  "url": "http://localhost:3000/",
  "device": "desktop",
  "steps": [
    {"n": 1, "action": "type", "target": {"role": "textbox", "name": "Project name"}, "args": {"text": "Weekend project"}},
    {"n": 2, "action": "click", "target": {"role": "button", "name": "Save project"}, "args": {}}
  ],
  "faults": [{"type": "storage-full", "start_action": 1}],
  "expect": [{"type": "text-visible", "text": "Project saved"}]
}
```

This example describes an assertion, not a promise that an arbitrary app should
save successfully under a full disk. Adjust it to the product's intended behavior,
such as retaining the draft and showing an error. The bundled demo does that.

`start_action` applies the fault **after** the numbered source action, before the
next replay step. `end_action` removes it after the last step at or below that
source number. Keep original step numbers when minimizing a scenario.

Targets support `testid`, `role` + `name`, `placeholder`, `css` and stored text.
Prefer accessible names or test IDs. Ambiguous targets are rejected. Devices are
`desktop`, `laptop`, `tablet` and `mobile`; the latter presets emulate viewports
and input capabilities in Chromium, not a physical device.

| Assertion | Required fields | Meaning |
| --- | --- | --- |
| `text-visible` | `text` | At least one matching visible node |
| `text-absent` | `text` | No matching visible node |
| `count` | `text`, at least one of `equals`, `min`, `max` | Visible match count, with optional `exact: true` |
| `no-page-error` | none | No JavaScript page error recorded during the trial |
| `page-not-blank` | none | Body has visible text content |
| `storage` | `key`, optional `contains`, `json` | localStorage value exists and matches the checks |
| `url-contains` | `text` | Current URL contains the supplied text |
| `field-value` | `field`, and `value` (exact) or `contains` | The input labelled `field` holds this value; a missing field makes the trial invalid |
| `js` | `expression`, optional `description` | Trusted JavaScript expression evaluates truthy |

Any assertion can take `session` in a scenario with several sessions (see below).

Run:

```bash
chaosfolk replay scenario.json --times 3 --with-control
chaosfolk replay scenario.json --times 3 --fail-on-bug
```

`--control` runs only the no-fault series. `--with-control` adds a no-fault series
to the treatment. It cannot control a user gesture such as double-clicking:
write a separate single-click scenario for that comparison.

## Clean data before every trial

A fresh browser context does not reset server data. Supply an environment file
when repeated trials write to a shared backend:

```json
{
  "data_id": "checkout-fixture-v3",
  "app_version": "build-2026-10-27",
  "app_repo": "..",
  "prepare": {"command": ["python", "reset_fixture.py"], "timeout": 30},
  "verify": {"command": ["python", "verify_fixture.py"], "timeout": 10}
}
```

```bash
chaosfolk replay scenario.json --times 5 --with-control --environment qa/environment.json
```

Commands run from the environment file's directory, as argument lists without
shell expansion. Use the executable available in your environment (`python3`
where appropriate). Both commands must exit zero. The verification command must
print a JSON object with `"ready": true` and the same `data_id`; it should check
the actual fixture contents, not just echo the configured identity. Timeouts
default to 30 seconds and cannot exceed 300 seconds per command. Timed-out
commands and their remaining child processes are killed.

With preparation configured, every trial and divergence retry runs sequentially,
after preparation and verification. This applies to control trials too. A failed
command, timeout, malformed response or fixture mismatch makes the trial invalid
and prevents its browser actions. Hook output and commands are not included in
the evidence. Configure credentials through the local environment rather than
putting them in command arguments.

Each trial records `preparation.status`: `reset-verified`, `browser-only`, or
`invalid`. Without preparation, existing scenarios continue to run in isolated
browser contexts and no claim is made about clean backend data. Serial execution
coordinates trials in this replay invocation; use a dedicated backend or an
external lock if other processes can write to the same fixture.

`app_version` and `app_repo` are optional metadata and can be supplied without
preparation commands. `app_repo` resolves relative to the environment file and
records the Git commit and whether the working tree has changes. Unknown build
metadata remains null. A dirty commit alone cannot reconstruct the app: retain
the source changes or the tested build separately.

## Reference journey matrix

Supply a reference scenario reviewed by your team to run four series:

```bash
chaosfolk replay observed.json --baseline reference.json --times 5 --environment qa/environment.json --output .horde/run/reproductions
```

| Journey | Without faults | With faults |
| --- | --- | --- |
| Observed | Recorded actions, no injection | Recorded actions and injections |
| Reference | Team's reference actions, no injection | Reference actions and injections |

Both scenarios need explicit assertions and a reachable fault schedule. They
must describe the same fault conditions and parameters, but their start/end
action anchors can differ to match each journey. Chaosfolk does not copy action
numbers between journeys or generate a reference. Each journey keeps its own
expected outcomes; choose assertions that describe acceptable behavior with and
without the fault, such as a draft retained on failure or a successful save.

`--baseline` accepts one observed scenario and cannot be combined with `--control`.
It automatically includes controls; `--with-control` is redundant. `--persist`
produces a separate matrix per recipe. Without this override, both journeys must
use the same persistence recipe. Four series of five trials cost twenty
trials, before any existing divergence retry. They do not call a model.

The result directory contains the four series and `matrix.json` (or
`matrix-persist-<recipe>.json`). Each summary embeds all four series and counts,
with status `all-pass`, `failures-observed`, `intermittent` or `inconclusive`.
When saved in the session's `reproductions/`, matrices also appear in the HTML
report. A matrix identifies differences in observed outcomes; product review
still determines whether a failure is a bug, and how severe it is. An unusual
journey can expose a valid defect.

## Reproduction manifests and rates

Every replay writes a uniquely named `manifests/<run>-<index>.json` and links it
from the result's `manifest` field. It includes the normalized scenario snapshot
and hashes of that scenario and its original file, the seed and generated profile
definitions when available, original profile/catalog/template fingerprints,
engine, Playwright and browser versions, application metadata, browser-state
fingerprints, fixture identity, and the configured fault schedule. New draws
record profile and agent/persona template hashes; older sessions explicitly lack
this provenance. Extracted scenarios also retain the original fault events.
Individual trials record the injections actually applied, removed, or ended by
context closure, with step anchors and elapsed milliseconds.

Browser-state contents and fixture command output are excluded from manifests.
Keep the original scenario, private browser-state files, fixture scripts and
backend snapshot with the evidence in order to replay elsewhere. Manifests record
identity and provenance; they do not bundle or restore an application or database.
Missing metadata stays null. A seed repeats a draw under the same catalog and
parameters, not an agent's decisions. Replays follow recorded actions and fault
anchors rather than promising identical network races or wall-clock timing.

Result JSON adds `reproducibility` with `requested`, `valid`, `failures`, `invalid`
and `failure_rate` (0 to 1, or null when no trial is valid). CLI and bilingual HTML
reports show failures / valid trials, percentage, invalid count and requested
count, including series with fewer than three valid trials. For example, one
failure in four valid trials out of five requested is `1/4 (25.0%)`, with one
invalid trial. Invalid trials never count as successes. Small or incomplete
series remain visible without acquiring a reproduced badge. The measured rate
describes these trials; severity stays separate.

## Persistence recipes

A success message does not prove persistence. `--persist` verifies the scenario's
assertions after a recipe, with one series per recipe:

```bash
chaosfolk replay scenario.json --times 3 --persist reload,revisit,new-tab,local-only,back,retry
```

`reload` reloads, `revisit` opens the start address again, `new-tab` opens the
current address in a new tab, `local-only` clears local and session storage then
reloads, `back` presses Back and `retry` replays the last successful step. Series
are named `<scenario>-persist-<recipe>`. A scenario can also set `"recipe"`
itself. The [QA checks guide](checks.md) maps each recipe to the problem it
exposes: false success, data loss, duplicates after a retry, out-of-sync views.

## Several sessions in one trial

```json
{
  "url": "http://localhost:3000/plan",
  "sessions": {"editor": {"state": "etats/editor.json"}, "reader": {"state": "etats/reader.json", "device": "mobile"}},
  "steps": [
    {"n": 1, "session": "editor", "action": "type", "target": {"role": "textbox", "name": "Title"}, "args": {"text": "Plan B"}},
    {"n": 2, "session": "editor", "action": "click", "target": {"role": "button", "name": "Save"}, "args": {}},
    {"n": 3, "session": "reader", "action": "reload", "args": {}}
  ],
  "expect": [{"type": "text-visible", "session": "reader", "text": "Plan B"}]
}
```

Each session opens its own isolated context at its first step. Assertions without
`session` are checked in the last session that acted. Faults apply to the first
session only. `extract h01,h02` builds such a scenario from a coordinated run;
see [campaigns.md](campaigns.md).

## Data variations and differential replays

`vary` replays one scenario once per test value of a field, and `compare`
replays two scenarios in pairs to check whether their outcomes match, which is
how account enumeration is proven. Both use this replay engine and write result
files in the same format. See the [QA checks guide](checks.md).

## Evidence states

| Observation | Evidence required |
| --- | --- |
| Reproduced fault-related bug | At least 3 valid treatment trials, all failing, and an equally complete control series, all passing |
| Reproduced unconditional bug | At least 3 valid failures without an injected condition |
| Fix passes | At least 3 valid passes after the change; controls continue passing |
| Causal fix check | Removing the change brings back the same failure in at least 3 valid trials |
| Inconclusive | Any requested trial is invalid or missing |

Browser startup failures, unavailable pages and uncheckable assertions are invalid
trials. A replay that blocks at the same step on its one retry can count as a
failure; compare the control before attributing the cause. A different blocking
step on retry remains inconclusive. A series failing only some trials is intermittent.

With `--fail-on-bug`, exit `0` means the checked outcomes held; `1` means a failure;
`2` means incomplete or invalid execution. An empty assertion set is rejected for
this gate. Without the flag, a completed diagnostic replay can exit `0` even when
it reproduced a bug: inspect its result JSON.

## Stored format

Existing traces use stable French field names. Public English inputs are mapped
on load; their free text is never translated.

| Public input | Stored key |
| --- | --- |
| `steps`, `expect`, `faults` | `etapes`, `attendu`, `pannes` |
| `device`, `start`, `state`, `session_dir` | `appareil`, `depart`, `etat`, `dossier_horde` |
| `target`, target `name` | `cible`, `nom` |
| `text`, `key`, `contains`, `equals` in assertions | `texte`, `cle`, `contient`, `egal` |
| `start_action`, `end_action` | `debut_n`, `fin_n` |

Replay results use `demandes` (requested trials), `fois` (valid trials), `casses`
(failed trials), `essais` (individual results) and `mode` (`traitement` or `temoin`).
Each trial's `ok` is `true`, `false` or `null` for invalid. Keep the result files as
the source of evidence; do not hand-edit their counts.

## Report contract

Write `constats.json` in the session directory. Text values may be in any language.
The schema retains stored keys for compatibility:

```json
{
  "titre": "Project editor: session results",
  "application": "Project editor",
  "resume": "Four simulated users explored project creation and editing. One candidate was reproduced.",
  "constats": [{
    "id": "CF-001",
    "titre": "The draft disappears when saving fails",
    "gravite": "bloquant",
    "statut": "reproduit",
    "condition": "storage-full",
    "resume": "The form clears before its storage write completes.",
    "evenements": [{"h": "h01", "n": 8}],
    "preuves": {
      "avant": "reproductions/save-traitement.json",
      "temoin": "reproductions/save-traitement-temoin.json"
    },
    "correctif": {
      "consigne": "Clear the draft only after a successful save; preserve it when saving fails.",
      "attendu": "A failed save leaves the typed draft available."
    }
  }]
}
```

This is a format example, not measured evidence. Replace every count, event and
proof path with your session's results. Omit `condition` only for an unconditional
bug. Severity values are `bloquant`, `genant`, `mineur` (English equivalents are
also displayed). Proof keys `apres` and `demontee` capture the fixed and removed-fix
series. The renderer derives its reproduced badge from resolved trial evidence,
not the free-form `statut` label.
