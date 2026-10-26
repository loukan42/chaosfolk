<div align="center">

<img src="logo.png" alt="Chaosfolk. AI users. Real browser evidence. Explore, break, replay." width="820">

**Simulated users break your web app in a real browser.<br>You get the bugs, the proof and a fix prompt for your coding agent.**

[![Tests](https://github.com/loukan42/chaosfolk/actions/workflows/tests.yml/badge.svg)](https://github.com/loukan42/chaosfolk/actions/workflows/tests.yml)
[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue)](https://www.python.org/)
[![MIT license](https://img.shields.io/badge/license-MIT-dcf78b)](LICENSE)

[Why](#why) · [How](#how) · [What you get](#what-you-get) · [Try the demo](#try-the-demo) · [Use it on your app](#use-it-on-your-app)

</div>

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

**Proof before verdict.** The agent turns each promising observation into a
scenario with an explicit assertion. The engine replays it without a model:
three failing trials with the fault and three passing controls without it mark a
finding as reproduced. Anything weaker stays labeled as an observation.

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

## Try the demo

No AI agent or API key needed. The demo starts a small local app with a
deliberate bug: a form that loses your draft when storage is full. It runs real
browser trials on the broken and fixed versions, then writes the report.

Requirements: Python 3.12+ and Git.

```bash
git clone https://github.com/loukan42/chaosfolk.git
cd chaosfolk
python -m venv .venv
```

Activate the environment:

```bash
# macOS / Linux
source .venv/bin/activate
```

```powershell
# Windows PowerShell
.\.venv\Scripts\Activate.ps1
```

Install the engine and run the demo:

```bash
python -m pip install .
python -m playwright install chromium
chaosfolk demo --lang en
```

Open `.horde/demo/rapport.html`, keeping it next to its screenshot folders. Use
`--lang fr` for French; the report has a language switch.

## Use it on your app

Install the engine as above, then add the skill to your coding agent (requires
Node.js and npm):

```bash
npx skills add loukan42/chaosfolk --skill chaosfolk
```

The installer asks which agent you use. Otherwise follow the
[manual installation guide](docs/agents.md). Your agent host needs shell
access, file access and subagents, and it supplies the model.

Then ask your agent:

```text
Use Chaosfolk on my local test app at http://localhost:3000.
Explore creating, finding and editing a project. Use the medium run size,
synthetic data and an English report. Do not send messages or make purchases.
Report what you find without changing the app.
```

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
performance probes are small local smoke tests, accessibility checks are not a
conformance audit, and mobile means browser emulation. Use dedicated tools and
real devices to go deeper.

Run it only on local apps or test environments you are allowed to test, with
synthetic data. Screenshots can contain sensitive content, so review them before
sharing. See [SECURITY.md](SECURITY.md).

---

[Workflow and coverage](docs/workflow.md) · [Fault injection](docs/faults.md) ·
[Replay format](docs/replay.md) · [Contributing](CONTRIBUTING.md) · [MIT license](LICENSE)
