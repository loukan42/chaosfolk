# Replay and evidence

Replays follow recorded browser actions without asking a model. Supply an explicit
expected outcome. The app and its initial data must be available for each trial.
For shared backend state, use `--sequential` and reset or isolate test data.

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
