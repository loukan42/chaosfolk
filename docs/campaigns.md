# Campaigns, journey map and coordinated sessions

## Name the project

Several applications can answer on `http://localhost:3000` at different times.
Chaosfolk therefore identifies an app by an explicit project name, never by its
address:

```bash
chaosfolk launch --url http://localhost:3000 --folder .horde/run --project shop-front
```

The name is kept in the session's `config.json`. Its memory lives in
`<state directory>/projects/shop-front/` (by default `~/.chaosfolk/projects/`).
Addresses are stored as attributes, so the same project keeps its history when
it moves to another port.

## Map the journeys

```bash
chaosfolk map --folder .horde/run --project shop-front
```

`map` turns the journal into routes and transitions. Identifiers become `:id`
and query values are dropped, so `/orders/42?tab=2` and `/orders/7?tab=5` are the
same route. It prints how often each route was used, failed actions, the most
repeated transitions and the routes to explore next: links recorded by
`fields --save` that nobody visited, then the least visited routes.

With `--project`, the map is merged into the project's memory. The next draw can
then send each user towards different, less explored routes:

```bash
chaosfolk draw --level medium --seed 7 --objectives "Order a product" --project shop-front --folder .horde/run2
```

Each user receives three other routes to visit before its goals, which widens
exploration from one campaign to the next and reduces repetition.

Repeated merges of the same session replace its previous route and transition
counts. Running `map` before `campaign record` therefore counts the session once.
The map keeps compact per-session counters in `_campaigns` for this purpose.
Maps created before this tracking was added retain their aggregate totals;
historical duplicates cannot be reconstructed or removed automatically.

## Record and compare campaigns

After writing `constats.json` and generating the report:

```bash
chaosfolk campaign record --folder .horde/run --project shop-front --label before-fix
chaosfolk campaign compare --project shop-front
chaosfolk campaign status --project shop-front
```

`record` stores the campaign with its findings, proofs, coverage and the git
revision of the current folder (`--repo` for another one). Each finding gets a
fingerprint from its check id, route and title words. When the same finding is
described with another title, set `"fingerprint"` in `constats.json` to the value
shown by `campaign status`. The proven scenarios are copied into the project's
memory, so they stay replayable after the session folder is deleted.

Project updates use a local SQLite lock and replace each JSON file atomically.
Concurrent commands wait up to ten seconds for the current update, then report
that the project is busy. Keep this state on a local filesystem. Before publishing
a recorded campaign, Chaosfolk stages its scenarios, history, findings and map in
`.campaign-pending.json`. If a write fails or the process stops between file
replacements, the next campaign or map command finishes that publication under
the lock before reading project memory. An already recovered label remains
recorded; it is not counted again.

The pending batch is limited to 64 MiB and 10,003 JSON files, including the three
project indexes. Oversized batches are rejected before publication. Keep a pending
journal when investigating an error: removing it discards the recovery snapshots.
Serialization enforces this byte limit while writing UTF-8. Files are flushed
and synchronized before replacement; directory entries are synchronized on
POSIX filesystems that support it. A pending transaction must be recovered
before another can be published.
This mechanism handles interrupted publication on the local filesystem. It does
not guarantee recovery from storage failure, lost filesystem caches or corrupted
files after a power loss; back up project memory when it must survive those events.

`compare` lists new findings, findings still present and findings not seen again
between the last two campaigns (or `--before` and `--after`). A finding that was
not seen again is not fixed until a replay proves it.

## Replay what matters without starting over

```bash
chaosfolk campaign select --project shop-front --limit 10
chaosfolk campaign select --project shop-front --replay --url http://localhost:5173
```

`select` ranks recorded scenarios: open findings first, then by severity, how
often they were seen and how recently. `--replay` runs each one three times in
sequence, with `--url` when the app moved, and updates its status: three passes
mark it `fixed`, three failures keep it `open`, anything else is recorded as
inconclusive. Scenarios without an assertion are skipped. This is the existing
replay engine, chosen automatically; nothing is re-explored.

Replays release the project lock while the browser runs. If another campaign or
replay changes a selected finding before completion, `select` preserves that
newer state, reports the conflict and returns a nonzero exit code. The replay
evidence remains in the project's `replays` folder for review.

## Independent and coordinated sessions

| Mode | What it tests |
| --- | --- |
| Independent (default) | Each user keeps distinct data, so users do not interfere by accident. Every user is asked to add its id, such as H02, to the name of everything it creates and to change only its own records. |
| Coordinated | Several users work on the same test objects on purpose, to explore conflicts, lost updates and collaboration. |

```bash
chaosfolk draw --level medium --seed 4 --objectives "Edit the project plan" --sessions coordinated --shared "Project Alpha;Budget 2026" --folder .horde/run
```

In coordinated mode every user is told which objects are shared and to report
changes that are lost, hidden or conflicting, and the coordinated checks join the
pool. Create the shared objects before the run, in synthetic test data.

Roles give each user a saved authenticated state:

```bash
chaosfolk draw ... --roles "editor=etats/editor.json;reader=etats/reader.json"
```

Users receive the roles in turn, with their state and an instruction to try what
the role should and should not be allowed to do. Save each state first with
`save-state` (see the workflow guide); the files contain credentials and stay
private.

## Prove a conflict between sessions

```bash
chaosfolk extract h01,h03 --output .horde/run/scenarios/conflict.json --folder .horde/run
```

Extracting several users merges their actions in journal order. Each step keeps
its `session`, and `sessions` records each user's state and device. The replay
opens one isolated browser context per session, so two users with different
accounts or roles act in the same trial. Assertions take an optional `session`
to be checked in that user's tab:

```json
{"type": "field-value", "session": "h01", "field": "Note", "value": "Text written by h01"}
```

Faults are not carried into a multi-session scenario, because their anchor
would be ambiguous. Use `--sequential` when trials share backend data, and reset
the shared objects between trials.
