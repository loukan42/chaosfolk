<div align="center">

<img src="logo.png" alt="Chaosfolk. AI users. Real browser evidence. Explore, break, replay." width="820">

**Simulated users break your web app in a real browser.<br>You get the bugs, the proof and a fix prompt for your coding agent.**

[![Tests](https://github.com/loukan42/chaosfolk/actions/workflows/tests.yml/badge.svg)](https://github.com/loukan42/chaosfolk/actions/workflows/tests.yml)
[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue)](https://www.python.org/)
[![MIT license](https://img.shields.io/badge/license-MIT-dcf78b)](LICENSE)

[Why](#why) · [How](#how) · [What it checks](#what-it-checks) · [What you get](#what-you-get) · [Install](#install) · [Try the demo](#try-the-demo) · [Use it on your app](#use-it-on-your-app) · [Changelog](CHANGELOG.md)

</div>

### Watch the trailer

https://github.com/user-attachments/assets/500cdc82-94da-466b-bc26-2f85cfc8072d

## Why

Your tests check the paths you wrote. Your users take other paths. They
double-click Save, lose their connection halfway through a form, come back an
hour later in another tab. You rarely try these things yourself, because you
know how the app is supposed to work.

AI agents can explore an app for you, but "this looks broken" is an opinion.
You need to know whether the bug is real before you spend time on it.

Chaosfolk lets a small team test like a crowd of strangers, and only calls
something a bug when it can show it happening again.

## How

**Users with habits, in a real browser.** Your coding agent runs simulated
users, each with a goal and one of 16 behavior profiles: in a hurry,
keyboard-only, on mobile, distracted, unfamiliar with jargon. Each one drives
its own Chromium context and can work through several of your goals.

**Chaos on purpose.** While they work, the engine injects the conditions real
users meet: offline, slow or failing requests, lost responses, full or corrupted
storage, cleared cookies, clock jumps and viewport changes.

**The checks a QA team would run.** Each tester also carries a share of a catalog
of 69 concrete checks, with test values and the expected behavior: names in any
script, phone numbers and postal codes from 15 countries, extreme input, double
submits, interrupted forms, account enumeration, keyboard access and more. The
engine reads each page's fields first, so testers get the checks that apply.

**Proof before verdict.** The agent turns each promising observation into a
scenario with an explicit assertion. The engine replays it without a model:
three failing trials with the fault and three passing controls without it mark a
finding as reproduced. A "saved" message is not proof: replays reload, reopen,
clear local storage or submit again before checking. Anything weaker stays
labeled as an observation.

## What it checks

Random exploration finds what nobody planned. These deterministic commands run
next to it, without a model, and their results feed the same report.

| Command | What it does | Example of a problem it finds |
| --- | --- | --- |
| `fields` | Classifies every field of a page and lists the checks that apply | A postal code in `type=number` loses its leading zero |
| `vary` | Replays a form once per test value of a field, for the countries you serve | `+44 7700 900123` refused because the rule only knows French numbers |
| `compare` | Replays two scenarios and compares their outcomes | Password reset says "no account for this email" |
| `audit` | Measures a page at several screen sizes, then tabs through it | The submit button leaves the screen at 320 px; keyboard focus gets stuck |
| `replay --persist` | Reloads, reopens, clears storage or retries before asserting | A success message with nothing saved; a duplicate after a retry |
| `campaign` | Keeps a project's findings across runs and replays the open ones | A fix that came back two campaigns later |

Test values are international: validation should follow the user's country,
never one national pattern. Security checks stay passive and use synthetic
accounts. `audit` reports WCAG signals such as contrast, target size, names and
reflow; they are measurements to confirm, not a conformance audit. See the
[QA checks guide](docs/checks.md).

Each app is identified by an explicit project name, not by `localhost:3000`.
Its memory keeps a map of the journeys already explored, so the next testers
start where earlier ones did not go, and the findings of every campaign, so a
fix is checked by replaying what failed instead of starting over. Testers can
work on separate data or on the same records on purpose, with different roles,
to find conflicts and permission gaps. See [campaigns and sessions](docs/campaigns.md).

## What you get

A local HTML report, in English or French, built around what to fix.

### Findings, evidence and a fix prompt

A score out of 100, the findings with their severity, and the evidence behind
each one: replay results, screenshots and the expected behavior. Tick the
findings you want fixed and copy a ready-made prompt for your coding agent.

![A finding opens to reveal its evidence, then selected findings are assembled into a fix prompt.](assets/audit-findings.gif)

### Synchronized session replay

Watch every tester's screen on one timeline, change the speed and jump straight
to the moments where something went wrong.

![Synchronized browser screens playing back a recorded session.](assets/audit-replay.gif)

Both recordings come from Chaosfolk auditing its own report with four simulated
users. The score is a [documented heuristic](docs/scoring.md) for one session,
not a measure of total coverage.

## Install

One command installs everything: the engine, its browser, and the skill for
each coding agent found on your computer (Claude Code, Codex, Cursor, GitHub
Copilot, Gemini CLI, OpenCode and Windsurf). You don't need Python, Node.js or
Git first.

**macOS and Linux**

```bash
curl -LsSf https://raw.githubusercontent.com/loukan42/chaosfolk/main/install.sh | sh
```

**Windows**, in PowerShell

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://raw.githubusercontent.com/loukan42/chaosfolk/main/install.ps1 | iex"
```

Then **restart your coding agent** and ask it: `Run chaosfolk check and tell me
if anything is missing.` To update later, run the same command again.

Chaosfolk works best when your agent can start subagents, so testers run in
parallel. Without subagents, the agent plays them one after another: the run
takes longer and the testers are less independent.

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

No AI agent or API key needed. The demo starts a small local app with a
deliberate bug: a form that loses your draft when storage is full. It runs real
browser trials on the broken and fixed versions, then writes the report.

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

For a QA-style pass, say so and name what matters:

```text
Run Chaosfolk on project "shop-front" at http://localhost:3000 with the themes
functional, security and accessibility. Our customers are in France, Belgium and
Switzerland. Check every form field with the catalog, prove persistence after
reload, check the password reset for account enumeration with the test account
test@example.com, and audit the sign-up page on mobile and desktop.
```

After a fix, ask: `Replay the open Chaosfolk findings for shop-front and tell me
what is fixed.`

**Pick what to test.** Name one or more themes, or ask for `all`:
`functional`, `ux`, `accessibility`, `resilience`, `security`, `performance`,
`compatibility`. The report shows which themes were tested, partly tested or
left out.

**Pick a run size.** Preview one with `chaosfolk plan --level medium`.

| Run size | Simulated users | Actions per user |
| --- | ---: | ---: |
| Low | 2 | 12 |
| Medium | 4 | 20 |
| High | 12 | 40 |

These cap browser actions, not tokens. Model cost depends on your agent host,
your pages and the analysis; check it there.

## Limits

Chaosfolk is alpha software and its users are fictional: their reactions are
test hypotheses, not research with real people. Security checks are passive,
performance probes are small local smoke tests, accessibility signals (including
estimated contrast) are not a conformance audit, and mobile means browser
emulation. The catalog replaces neither product knowledge nor a dedicated
security test, a screen reader review or real devices: use them to go deeper.

Run it only on local apps or test environments you are allowed to test, with
synthetic data. Screenshots can contain sensitive content, so review them before
sharing. See [SECURITY.md](SECURITY.md).

---

[Workflow and coverage](docs/workflow.md) · [QA checks](docs/checks.md) · [Campaigns and sessions](docs/campaigns.md) ·
[Fault injection](docs/faults.md) · [Replay format](docs/replay.md) · [Changelog](CHANGELOG.md) · [Contributing](CONTRIBUTING.md) · [MIT license](LICENSE)
