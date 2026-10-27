<div align="center">

<img src="logo.png" alt="Chaosfolk. AI users. Real browser evidence. Explore, break, replay." width="820">

**Simulated users break your web app in a real browser.<br>You get the bugs, the proof and a fix prompt for your coding agent.**

[![Tests](https://github.com/loukan42/chaosfolk/actions/workflows/tests.yml/badge.svg)](https://github.com/loukan42/chaosfolk/actions/workflows/tests.yml)
[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue)](https://www.python.org/)
[![MIT license](https://img.shields.io/badge/license-MIT-dcf78b)](LICENSE)

[Why](#why) · [How](#how) · [What it checks](#what-it-checks) · [What you get](#what-you-get) · [Install](#install) · [Try the demo](#try-the-demo) · [Use it on your app](#use-it-on-your-app) · [Keep what you found](#keep-what-you-found) · [Changelog](CHANGELOG.md)

</div>

### Watch the trailer

https://github.com/user-attachments/assets/500cdc82-94da-466b-bc26-2f85cfc8072d

## Why

Your tests cover the paths you wrote. Your users double-click Save, lose their
connection halfway through a form and come back an hour later in another tab.
You rarely do these things yourself, because you know how the app is supposed
to work.

An AI agent can explore the app for you, but its "this looks broken" may be
wrong. Chaosfolk reports a bug only after replaying it and seeing it fail again.

## How

Your coding agent runs simulated users. Each one has a goal and one of 16
behavior profiles (in a hurry, keyboard only, on mobile, distracted, unfamiliar
with jargon), drives its own Chromium context and can work through several of
your goals.

While they work, the engine injects the conditions real users meet: offline,
slow or failing requests, lost responses, full or corrupted storage, cleared
cookies, clock jumps and viewport changes.

Each tester also gets part of a catalog of 69 checks, each with test values and
the expected behavior, among them names in any script, phone numbers and postal
codes from 15 countries, extreme input, double submits, interrupted forms,
account enumeration and keyboard access. The engine reads each page's fields first, so
testers only get the checks that apply.

The agent turns each promising observation into a scenario with an explicit
assertion, and the engine replays it without a model. A finding is reproduced
when it fails three times with the fault and passes three control runs without
it. A "saved" message does not count: the replay reloads, reopens, clears local
storage or submits again before checking. Anything less stays labeled as an
observation.

## What it checks

These commands run without a model, alongside the exploration, and feed the
same report.

| Command | What it does | Example of a problem it finds |
| --- | --- | --- |
| `fields` | Classifies every field of a page and lists the checks that apply | A postal code in `type=number` loses its leading zero |
| `vary` | Replays a form once per test value of a field, for the countries you serve | `+44 7700 900123` refused because the rule only knows French numbers |
| `compare` | Replays two scenarios and compares their outcomes | Password reset says "no account for this email" |
| `audit` | Measures a page at several screen sizes, then tabs through it | The submit button leaves the screen at 320 px; keyboard focus gets stuck |
| `replay --persist` | Reloads, reopens, clears storage or retries before asserting | A success message with nothing saved; a duplicate after a retry |
| `campaign` | Keeps a project's findings across runs and replays the open ones | A fix that came back two campaigns later |

Test values cover several countries, because validation should follow the
user's country. Security checks are passive and use synthetic accounts. `audit`
reports WCAG signals such as contrast, target size, names and reflow; confirm
them by hand, they are not a conformance audit. See the
[QA checks guide](docs/checks.md).

You name each app with a project name instead of relying on `localhost:3000`.
Chaosfolk then remembers the journeys already explored, so the next testers go
elsewhere, and the findings of every campaign, so you check a fix by replaying
what failed. Testers can work on separate data, or on the same records with
different roles to find conflicts and permission gaps. See
[campaigns and sessions](docs/campaigns.md).

## What you get

A local HTML report in English or French.

### Findings, evidence and a fix prompt

The report gives a score out of 100, the findings by severity and the evidence
for each one: replay results, screenshots and the expected behavior. Tick the
findings you want fixed and copy the generated prompt into your coding agent.

![A finding opens to reveal its evidence, then selected findings are assembled into a fix prompt.](assets/audit-findings.gif)

### Synchronized session replay

Every tester's screen plays on one timeline. You can change the speed and jump
to the moments where something went wrong.

![Synchronized browser screens playing back a recorded session.](assets/audit-replay.gif)

Both recordings come from Chaosfolk auditing its own report with four simulated
users. The score is a [documented heuristic](docs/scoring.md) for one session,
not a measure of coverage.

## Install

One command installs the engine, its browser and the skill for each coding
agent found on your computer (Claude Code, Codex, Cursor, GitHub Copilot,
Gemini CLI, OpenCode and Windsurf). You don't need Python, Node.js or Git.

**macOS and Linux**

```bash
curl -LsSf https://raw.githubusercontent.com/loukan42/chaosfolk/main/install.sh | sh
```

**Windows**, in PowerShell

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://raw.githubusercontent.com/loukan42/chaosfolk/main/install.ps1 | iex"
```

Then restart your coding agent and ask it: `Run chaosfolk check and tell me if
anything is missing.` Run the same command again to update.

If your agent can start subagents, testers run in parallel. Otherwise the agent
plays them one after another, which takes longer and makes them less
independent.

<details>
<summary>What the installer does</summary>

1. Installs [uv](https://docs.astral.sh/uv/) if it is missing. uv downloads
   Python 3.12 or newer into its own folder when your computer has none.
2. Installs the Chaosfolk engine as a command-line tool, isolated from your other
   Python packages, and adds it to your PATH.
3. Runs `chaosfolk setup`, which downloads Chromium when no usable browser is
   found, copies the skill into each agent's skills folder and, for Claude Code,
   adds the simulated user definition. That definition runs testers on Sonnet
   with only the shell and file reading.

You can read [install.sh](install.sh) and [install.ps1](install.ps1) before
running them. Set `CHAOSFOLK_NO_MODIFY_PATH=1` to keep your PATH unchanged.

</details>

<details>
<summary>Other ways to install</summary>

- **Your agent was not detected**, or you want one agent only: run
  `chaosfolk setup --agent claude-code`. The other ids are `codex`, `cursor`,
  `github-copilot`, `gemini-cli`, `opencode`, `windsurf`, and `universal` for the
  shared `~/.agents/skills` folder.
- **With pipx or uv** you already use:
  `pipx install git+https://github.com/loukan42/chaosfolk.git`, or
  `uv tool install git+https://github.com/loukan42/chaosfolk.git`, then
  `chaosfolk setup`.
- **With the [Skills CLI](https://github.com/vercel-labs/skills)** for the skill:
  `npx skills add loukan42/chaosfolk --skill chaosfolk -g`. It does not install
  the engine: use one of the commands above for that.
- **Manual installation** and details for each agent: see the
  [agent guide](docs/agents.md).

</details>

<details>
<summary>Something went wrong?</summary>

- **`chaosfolk: command not found`**: open a new terminal; the installer added
  Chaosfolk to your PATH for new terminals only.
- **`chaosfolk check` shows a missing browser**: run `chaosfolk install-browser`.
  On Linux, `chaosfolk install-browser --with-deps` also installs the system
  libraries Chromium needs.
- **Your agent does not know Chaosfolk**: restart it, or run
  `chaosfolk setup --agent <id>` for the agent you actually use.
- **To uninstall**: run `uv tool uninstall chaosfolk`, then delete the
  `chaosfolk` folder from your agent's skills folder.

</details>

## Try the demo

The demo needs no AI agent or API key. It starts a small local app whose form
loses your draft when storage is full, runs real browser trials on the broken
and fixed versions, then writes the report.

```bash
chaosfolk demo --lang en
```

Open `.horde/demo/rapport.html` in the folder where you ran the command, and
keep it next to its screenshot folders. Use `--lang fr` for French; the report
has a language switch.

## Use it on your app

Start your app locally, open your coding agent in its project, and ask:

```text
Use Chaosfolk on my local test app at http://localhost:3000, project "shop-front".
Explore creating, finding and editing a project. Use the medium run size,
synthetic data and an English report. Do not send messages or make purchases.
Report what you find without changing the app.
```

For a QA pass, name the themes and what matters to you:

```text
Run Chaosfolk on project "shop-front" at http://localhost:3000 with the themes
functional, security and accessibility. Our customers are in France, Belgium and
Switzerland. Check every form field with the catalog, prove persistence after
reload, check the password reset for account enumeration with the test account
test@example.com, and audit the sign-up page on mobile and desktop.
```

After a fix, ask: `Replay the open Chaosfolk findings for shop-front and tell me
what is fixed.`

The themes are `functional`, `ux`, `accessibility`, `resilience`, `security`,
`performance` and `compatibility`, or `all`. The report shows which ones were
tested, partly tested or left out.

Three run sizes are available. Preview one with `chaosfolk plan --level medium`.

| Run size | Simulated users | Actions per user |
| --- | ---: | ---: |
| Low | 2 | 12 |
| Medium | 4 | 20 |
| High | 12 | 40 |

These numbers cap browser actions, not tokens. Model cost depends on your agent
host, your pages and the analysis. If the host exports its usage,
`chaosfolk usage` stops the next batch at a token or cost limit.

## Keep what you found

Once a finding is proven, you can keep it as a test that runs without a model:

```bash
chaosfolk regression export .horde/run/scenarios/h02-save.json --output tests/test_save_draft.py
chaosfolk regression run qa/scenarios/*.json --output qa-results
```

The first command writes a plain Playwright test for your repository. The
second replays saved scenarios in CI and writes JUnit results: exit code 1 is a
product failure, 2 means the run itself cannot be trusted. Visual comparison
and Firefox and WebKit are covered in [regression tests and CI](docs/regression.md).

Other commands:

- `chaosfolk planning changes` picks the journeys a pull request touches ([planning](docs/planning.md)).
- `chaosfolk privacy` makes a copy of a report you can share.
- `chaosfolk benchmark run` checks the harness on apps with known defects ([benchmark](docs/benchmark.md)).
- Optional adapters cover a Mailpit test mailbox, downloaded files, axe-core,
  k6, Appium and a read-only MCP server ([integrations](docs/integrations.md)).

## Limits

Chaosfolk is alpha software. Its users are fictional, so their reactions are
test hypotheses, not research with real people. Security checks are passive,
performance probes are small local smoke tests, accessibility signals
(including estimated contrast) are not a conformance audit, and mobile means
browser emulation. For more depth, you still need product knowledge, a
dedicated security test, a screen reader review and real devices.

Run it only on local apps or test environments you are allowed to test, with
synthetic data. Screenshots can contain sensitive content: review them before
sharing. See [SECURITY.md](SECURITY.md).

---

[Workflow and coverage](docs/workflow.md) · [QA checks](docs/checks.md) · [Campaigns and sessions](docs/campaigns.md) ·
[Fault injection](docs/faults.md) · [Replay format](docs/replay.md) · [Regressions and CI](docs/regression.md) ·
[Planning](docs/planning.md) · [Integrations](docs/integrations.md) · [Benchmark](docs/benchmark.md) · [Changelog](CHANGELOG.md) · [Contributing](CONTRIBUTING.md) · [MIT license](LICENSE)
