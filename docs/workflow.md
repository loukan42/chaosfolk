# Run an exploration

Use a local app or an explicitly authorized test target. These commands assume
the virtual environment is active and the application is already running on port
3000. Exclude `.horde/` from the application's git repository before collecting data.

Choose `low` (2 users × 12 actions), `medium` (4 × 20) or `high` (12 × 40).
`chaosfolk plan --level low` shows the settings without launching a run. Pass the
same `--level` to `launch`, `draw` and `sheets`. Explicit `--count` and `--budget`
override the preset. The action budget does not cap tokens, model cost, scout work
or runtime; the agent host must measure usage if it exposes it.

Run `chaosfolk themes` to see the available subjects. Pass `--themes functional,ux`
or `--themes all` to `draw`. The selected focus is added to every user's sheet;
it is not one agent per theme. Record which checks actually ran. A small action
budget can leave goals unfinished, especially with `all`.

## Prepare and start

```bash
chaosfolk check
chaosfolk launch --url http://localhost:3000 --folder .horde/run --level medium
```

`launch` prints the leader token. Set it in the coordinator shell, replacing the
placeholder with the token from your local run:

```bash
# POSIX shell
export CHAOSFOLK_LEADER_TOKEN='<token printed by launch>'
```

```powershell
# PowerShell
$env:CHAOSFOLK_LEADER_TOKEN = '<token printed by launch>'
```

To let the engine manage a development server, add
`--app-command "npm run dev -- --port 3000" --app-folder /path/to/app`.
Only use a startup command you trust. The engine stops only apps it starts.

For reconnaissance, create a `scout.json` file containing
`{"humains":[{"id":"e0","nom":"Scout"}]}`, then run `chaosfolk humans scout.json`,
`chaosfolk e0 look` and `chaosfolk network`. A scout has no default action cap;
the coordinator should keep this pass short and end it with `e0 done "..."`.

## Authenticated test session

If the test app requires login, start the engine with `--visible`. Create the
scout as above, then sign in yourself in its browser window. With the same leader
session and working directory, save its state inside the session folder:

```bash
chaosfolk save-state e0 .horde/run/etats/auth.json
chaosfolk draw --count 4 --budget 20 --seed 42 --objectives "Create a project;Find a project" --url http://localhost:3000 --folder .horde/run
```

Before running `humans`, add `"etat": "etats/auth.json"` to every object in
`.horde/run/personas.json` under `humains`. The path is relative to that file.
Then run `humans`, `drawn-faults` and `sheets` as below, without drawing again.
The saved state can contain credentials: keep the session private, never commit
it, and remove it when the authorized test session is over.

## Draw users and faults

```bash
chaosfolk draw --level medium --seed 42 --objectives "Create a project;Find a project;Edit its name" --app-name "My app" --url http://localhost:3000 --folder .horde/run
chaosfolk humans .horde/run/personas.json
chaosfolk drawn-faults .horde/run/tirage.json
chaosfolk sheets --folder .horde/run --level medium --data "Synthetic project names only" --forbidden "Messages, purchases, real accounts"
```

The output includes each sheet path in `fiches/`. Delegate one sheet per subagent,
with at most three active users. Use `--shell posix` for Bash or `--shell powershell`
for PowerShell. Each user runs its generated command, sees current element
references and chooses actions. The engine does not create or call an AI model.

Profiles contain a stable `profil_id` and `skin` index. The report shows the same
companion with the profile's expression and accessory. A seed reproduces the draw
within this catalog version, including the skins, but not a model's future choices.
The action budget is also part of that deterministic input. Pass the same budget
to `launch`, `draw` and `sheets`; `draw` schedules faults before the budget ends.

For a small concurrency check against an authorized local app, without a model:

```bash
chaosfolk probe http://127.0.0.1:3000/ --clients 4 --rounds 3 --output .horde/probe
```

Read `probe.json` for individual navigation results, page errors, elapsed times
and simple accessibility and HTTP-header review signals. Header presence alone
does not establish a security defect or guarantee protection. The probe limits clients and rounds,
blocks non-GET browser requests and other origins, and uses a fresh context per
trial. It does not infer a performance threshold or prove an accessibility defect.
State-changing GET routes can still run; use an isolated test environment. Run a
dedicated load tool or accessibility audit for broader coverage.

Useful manual browser commands:

```bash
chaosfolk h01 look
chaosfolk h01 type r7 "Weekend project"
chaosfolk h01 click r12
chaosfolk h01 flag "Saving cleared the draft without confirming success" --severity blocking
chaosfolk h01 done "I could not save the project."
```

`r7` and `r12` are examples. Read the current screen and use its actual references.
Commands return a nonzero exit status when the engine rejects the action. Do not
retry the same failure more than once. Authorized fixture uploads must be inside
`.horde/run/uploads/`.

## Extract evidence

```bash
chaosfolk stop --keep-app
chaosfolk analyze --folder .horde/run
chaosfolk trace h01 --around 8 --folder .horde/run
chaosfolk extract h01 --up-to 8 --folder .horde/run --output .horde/run/scenarios/save.json --expect expectation.json
chaosfolk replay .horde/run/scenarios/save.json --times 3 --with-control
```

Create `expectation.json` first, for example:

```json
{"type": "text-visible", "text": "Project saved"}
```

The assertion must match the product's expected behavior. A success message alone
does not establish persistence: reload or check storage when that matters.
See [replay.md](replay.md) for more assertions and the report contract.

## Write and inspect the report

Create `.horde/run/constats.json` using the contract in the replay guide. Record
the coverage actually reviewed in `.horde/run/coverage.json`:

```json
{
  "results": [
    {"theme": "functional", "status": "tested", "summary": "Created and found a project in Chromium."},
    {"theme": "accessibility", "status": "partial", "summary": "Keyboard path checked; screen reader not tested."},
    {"theme": "security", "status": "not-tested", "summary": "Dedicated security review not run."}
  ]
}
```

Statuses are `tested`, `partial`, `not-tested` and `not-reported`. These describe
the specific actions recorded in the summary, never complete coverage of a theme.
For bilingual reports, an entry may add `"translations": {"fr": {"summary": "..."}}`.
Selections absent from this file appear as “not documented”, not as passed checks.
Add only observations supported by the session, probe or external evidence. Then:

```bash
chaosfolk report --folder .horde/run --lang en
chaosfolk stop-app --folder .horde/run
```

Open `.horde/run/rapport.html`. Check that the named findings refer to real
screenshots and that proof counts match their replay files. The report includes
the cast, finding filters and an action timeline. Keep its `assets/`, `captures/`
and `reproductions/` folders with it when sharing a reviewed copy.

The coordinator asks the user whether the report should open in English or
French when no preference was given. Pass `--lang en` or `--lang fr`. An
interactive terminal prompts if it is omitted; automated calls must specify it.
Both language files are written, and the user can switch language in the report.

Always clean up after an interrupted run: `chaosfolk stop`, then
`chaosfolk stop-app --folder .horde/run`. Preserve evidence on failure. Never
commit a private session folder merely to share a report.
