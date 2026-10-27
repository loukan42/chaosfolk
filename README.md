<div align="center">

<img src="logo.png" alt="Chaosfolk. AI users. Real browser evidence. Explore, break, replay." width="820">

**Simulated users break your web app in a real browser.<br>You get the bugs, the proof and a fix prompt for your coding agent.**

[![Tests](https://github.com/loukan42/chaosfolk/actions/workflows/tests.yml/badge.svg)](https://github.com/loukan42/chaosfolk/actions/workflows/tests.yml)
[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue)](https://www.python.org/)
[![MIT license](https://img.shields.io/badge/license-MIT-dcf78b)](LICENSE)

[Test checklist](#test-checklist) · [Why](#why) · [How](#how) · [What it checks](#what-it-checks) · [What you get](#what-you-get) · [Install](#install) · [Try the demo](#try-the-demo) · [Use it on your app](#use-it-on-your-app) · [Control fault injection](#control-fault-injection) · [Keep what you found](#keep-what-you-found) · [Changelog](CHANGELOG.md)

</div>

## Test checklist

A check means the capability is available, not that every run executes it.
The 69 catalog checks guide simulated users; replay assertions and audit commands
verify the corresponding evidence. Some checks need test accounts, a mailbox,
coordinated users, project assertions or an explicitly configured integration.
Country-dependent test values cover 15 countries, according to the product's scope.

| What Chaosfolk can test | Supported |
| --- | :---: |
| **QA catalog: all 69 checks** | |
| First names: alphabets, accents, punctuation and saved values <!-- check:first-name-formats --> | ✓ |
| Family names: particles, apostrophes, case and saved values <!-- check:last-name-formats --> | ✓ |
| Single names, multiple family names and non-Western name order <!-- check:name-structure --> | ✓ |
| Email formats, plus addressing, case, whitespace and invalid addresses <!-- check:email-formats --> | ✓ |
| Sign-in with uppercase emails and surrounding spaces (test account) <!-- check:email-case-and-trim --> | ✓ |
| International and national phone formats, normalization and mobile keypad <!-- check:phone-formats --> | ✓ |
| Postal codes by country, letters, spaces and leading zeros <!-- check:postal-code-formats --> | ✓ |
| International addresses, town names and keyboard address suggestions <!-- check:address-formats --> | ✓ |
| Birth dates: invalid dates, future dates, age rules and timezone shifts <!-- check:birth-date-rules --> | ✓ |
| Date ranges: reversed dates, year boundaries and daylight-saving changes <!-- check:date-ranges --> | ✓ |
| Amounts: locale separators, currency precision, rounding and limits <!-- check:amount-formats --> | ✓ |
| Quantities: empty, zero, negative, decimal, oversized values and steppers <!-- check:quantity-bounds --> | ✓ |
| IBAN: checksum, country length, spaces, case and masked display <!-- check:iban-checksum --> | ✓ |
| Company registration numbers and country-specific validation <!-- check:company-id-formats --> | ✓ |
| Web addresses: schemes, saved links and unsafe URL schemes <!-- check:url-formats --> | ✓ |
| Password rules, passphrases, paste, show/hide and confirmation <!-- check:new-password-rules --> | ✓ |
| Free text: Unicode, emoji, line breaks, RTL, CJK and literal markup <!-- check:free-text-content --> | ✓ |
| Search: accents, case, symbols, whitespace, empty and unmatched queries <!-- check:search-inputs --> | ✓ |
| Uploads: file type, size, empty files, names, removal and replacement <!-- check:file-upload-rules --> | ✓ |
| Form validation: required fields, precise errors, focus and retained values <!-- check:form-errors-keep-data --> | ✓ |
| Duplicate records after double-clicking or pressing Enter twice <!-- check:double-submit --> | ✓ |
| Duplicate submissions after reload, Back and Forward <!-- check:reload-after-submit --> | ✓ |
| Saved values after reload and opening a new tab <!-- check:persistence-new-tab --> | ✓ |
| Cancellation of edits and recovery of unsaved work <!-- check:edit-cancel --> | ✓ |
| Delete confirmation, cancellation, persistence and undo when available <!-- check:delete-safety --> | ✓ |
| Lists: empty states, pagination bounds, stable sorting and combined filters <!-- check:list-edges --> | ✓ |
| Conflicting edits to the same record in two tabs <!-- check:two-tabs-conflict --> | ✓ |
| Private deep links while signed out and return after sign-in (test account) <!-- check:deep-link-auth --> | ✓ |
| Account enumeration through password-reset responses (test account) <!-- check:reset-enumeration --> | ✓ |
| Account enumeration through sign-in errors (test account) <!-- check:login-enumeration --> | ✓ |
| Account enumeration through sign-up responses (product review) (test account) <!-- check:signup-enumeration --> | ✓ |
| Throttling after repeated wrong passwords (six attempts, explicit approval) (test account) <!-- check:login-throttling --> | ✓ |
| Password masking, paste, password-manager support and URL exposure <!-- check:password-field-hygiene --> | ✓ |
| Passwords, session tokens and personal data exposed in URLs <!-- check:secrets-in-url --> | ✓ |
| Sign-out, Back, private-page reloads and session invalidation across tabs (test account) <!-- check:logout-session --> | ✓ |
| HTML-like input rendered as literal text <!-- check:html-escaping --> | ✓ |
| Technical details exposed in error pages <!-- check:error-leaks --> | ✓ |
| Access to another authorized test account's records (two test accounts) <!-- check:object-access-control --> | ✓ |
| Password-reset links: expiry and single use (test mailbox) <!-- check:reset-token-lifecycle --> | ✓ |
| Masking of sensitive data after saving (test account) <!-- check:sensitive-display --> | ✓ |
| Field labels, required indicators and accessible error associations <!-- check:field-labels-and-errors --> | ✓ |
| Completing a whole form using the keyboard <!-- check:keyboard-form --> | ✓ |
| Autocomplete purpose and mobile input attributes <!-- check:autocomplete-attributes --> | ✓ |
| Reflow at 320 CSS pixels and 200% zoom <!-- check:small-screen-reflow --> | ✓ |
| Feedback and recovery during slow or failed saves <!-- check:slow-submit-feedback --> | ✓ |
| Clear, actionable error messages in the application language <!-- check:error-message-quality --> | ✓ |
| Pasting values, automatic formatting and caret behavior <!-- check:paste-and-formatting --> | ✓ |
| Text inputs: empty, whitespace-only, long and special-character values <!-- check:text-input-extremes --> | ✓ |
| Numeric inputs: zero, negative, decimal and announced boundaries <!-- check:number-extremes --> | ✓ |
| Retrying a submission after an error <!-- check:submit-retry-after-error --> | ✓ |
| Interrupted forms: reload, Back/Forward, tab closure and reopening <!-- check:interrupted-form --> | ✓ |
| Search/filter races, reset and state retained after navigation <!-- check:search-filter-behavior --> | ✓ |
| Success messages checked against actual saved data <!-- check:false-success --> | ✓ |
| Unedited fields and attachments retained after another field changes <!-- check:data-loss-on-edit --> | ✓ |
| Consistency between lists, detail views, counters, badges and tabs <!-- check:ui-desync --> | ✓ |
| Controls reachable on phone, tablet and desktop viewports <!-- check:responsive-controls --> | ✓ |
| Horizontal overflow, clipped forms and unreachable submit buttons <!-- check:layout-overflow --> | ✓ |
| Tab order, focus visibility, hidden focus targets and modal focus traps <!-- check:keyboard-reachability --> | ✓ |
| Accessible names for controls, informative images and frames <!-- check:accessible-names --> | ✓ |
| Estimated text contrast (review signal) <!-- check:color-contrast --> | ✓ |
| Pointer-target dimensions and spacing (WCAG signal) <!-- check:target-size --> | ✓ |
| Page language, title, heading order, duplicate IDs, tabindex and zoom <!-- check:page-structure --> | ✓ |
| Live-region markup for results, success messages and errors <!-- check:status-messages --> | ✓ |
| Session-timeout warnings, extension and retained work (test account) <!-- check:time-limits --> | ✓ |
| Broken images and failed same-site styles, scripts, fonts and resources <!-- check:broken-resources --> | ✓ |
| Unhandled JavaScript errors and promise rejections during interactions <!-- check:javascript-errors --> | ✓ |
| Conflicting edits by two users on the same record (coordinated users) <!-- check:concurrent-edit-two-users --> | ✓ |
| Editor/reader permissions, direct URLs and visibility of changes (coordinated users) <!-- check:role-permissions --> | ✓ |
| Changes or deletions made by another user while a screen stays open (coordinated users) <!-- check:shared-object-notifications --> | ✓ |
| **Additional field and page inspection** | |
| Password forms submitted with GET or served over plain HTTP outside localhost | ✓ |
| Session-like cookies readable by JavaScript (review signal) | ✓ |
| Numeric field types that lose phone prefixes or postal-code zeros | ✓ |
| Labels provided only by disappearing placeholders | ✓ |
| Overly short maxlength limits for names, emails and addresses | ✓ |
| Controls covered by sticky bars, banners or other elements | ✓ |
| Clipped text in buttons, links, labels and headings | ✓ |
| Clickable-looking elements unreachable from the keyboard | ✓ |
| Focusable elements inside aria-hidden regions | ✓ |
| Generic link names such as "click here" | ✓ |
| Focus escaping a modal, landing on hidden elements or lacking a visible indicator | ✓ |
| **Fault injection and recovery** | |
| Offline browser context (`offline`) | ✓ |
| Slow matching requests (`slow`) | ✓ |
| Aborted application requests (`server-down`) | ✓ |
| Stop/restart of a local application managed by Chaosfolk (`app-stop`; replay uses request failure) | ✓ |
| HTTP error responses, including selected routes and methods (`http-error`) | ✓ |
| Backend writes whose responses are lost (`lost-response`) | ✓ |
| localStorage write failures from simulated quota exhaustion (`storage-full`) | ✓ |
| Cleared local/session storage (`storage-empty`) | ✓ |
| Corrupted browser-storage values (`storage-corrupt`) | ✓ |
| Page-clock advances (`clock`) | ✓ |
| Viewport changes during a journey (`window`) | ✓ |
| Cleared browser cookies (`cookies-cleared`) | ✓ |
| **Replay assertions and persistence** | |
| Expected text visible, absent or present a specified number of times | ✓ |
| Expected field value, exact or containing a substring | ✓ |
| Expected localStorage key/value or JSON content | ✓ |
| Expected URL substring | ✓ |
| No recorded JavaScript page errors | ✓ |
| Page body contains visible text | ✓ |
| Custom JavaScript assertions defined by the project | ✓ |
| Persistence after reload (`--persist reload`) | ✓ |
| Persistence after reopening the start address (`--persist revisit`) | ✓ |
| Persistence in a new tab (`--persist new-tab`) | ✓ |
| Persistence after clearing local/session storage (`--persist local-only`) | ✓ |
| Behavior after Back (`--persist back`) | ✓ |
| Duplicates and recovery after retrying the last successful action (`--persist retry`) | ✓ |
| All supplied field values, with separate acceptance/rejection assertions (`vary`) | ✓ |
| Equivalent or different final outcomes from two scenarios (`compare`) | ✓ |
| Repeated treatment/control trials with and without injected faults | ✓ |
| Observed/reference journey comparison with and without faults (2×2 matrix) | ✓ |
| Fixture preparation and identity verification before every trial and retry (project commands) | ✓ |
| Failure rates with valid, invalid and requested trial counts | ✓ |
| Whether saved findings still fail or pass after a fix or in a later campaign | ✓ |
| Saved scenario assertions in CI, with JUnit results (`regression run`) | ✓ |
| **Browser journeys and compatibility** | |
| Project-defined create, read, edit, delete and multi-step journeys | ✓ |
| Navigation, links, Back/Forward, tabs and browser dialogs | ✓ |
| Journey comprehension, labels, discoverability and feedback through simulated users | ✓ |
| Assigned behavior profiles, including hurried, distracted, keyboard and mobile users | ✓ |
| Independent users and coordinated users with separate roles on shared records | ✓ |
| Desktop, laptop, tablet and mobile viewport/input emulation | ✓ |
| Chromium, Firefox and WebKit scenario replays (installed browser engines) | ✓ |
| Pixel differences against reviewed screenshot baselines (optional visual extra) | ✓ |
| **Performance signals and optional integrations** | |
| Observed responsiveness and delays during user journeys | ✓ |
| Bounded local concurrent page-load smoke tests: HTTP errors, median and p95 timings (`probe`) | ✓ |
| Presence of CSP, X-Content-Type-Options, X-Frame-Options, Referrer-Policy and HSTS headers (local probe) | ✓ |
| Email subject, recipient and body content (Mailpit test mailbox) | ✓ |
| Downloaded CSV files: required columns, row-count bounds and expected content | ✓ |
| Downloaded text files: expected content | ✓ |
| Downloaded PDF files: PDF parsing and expected text (optional PDF extra) | ✓ |
| Automated axe-core accessibility rules (locally supplied axe-core script) | ✓ |
| External k6 load-test results (configured k6 executable and script) | ✓ |
| External Appium test results, including native mobile suites (configured Appium runner and script) | ✓ |

Accessibility and security rows describe checks and review signals, not compliance
certification or a penetration test. Mobile viewports are browser emulation;
native-device tests require the external Appium runner. Local performance probes
do not establish production capacity.

Details: [QA catalog](docs/checks.md), [faults](docs/faults.md),
[replay and evidence](docs/replay.md), [regressions and visual checks](docs/regression.md),
[optional integrations](docs/integrations.md).

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

**With the [Skills CLI](https://github.com/vercel-labs/skills)** ([skills.sh](https://skills.sh))

```bash
npx skills add loukan42/chaosfolk --skill chaosfolk -g
```

The Skills CLI installs the skill, not the engine it drives. Run the macOS and
Linux or Windows command above as well.

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

## Control fault injection

Existing runs keep their users, action budgets and fault pool. Optional chaos
policies let you limit simultaneous faults, the fraction of affected users,
injection probability, frequency and duration. You can group users by role or
journey, exclude targets and prevent certain faults from overlapping.

The engine applies these rules without a model. A blocked injection is skipped
with a recorded reason; it never waits for a slot or retries to fill a quota.
Policies add no simulated users, exploration steps or automatic replays.

To create a policy and use it for a short run:

```bash
chaosfolk chaos init --file qa/chaos.json
chaosfolk chaos check qa/chaos.json
chaosfolk launch --url http://localhost:3000 --project shop-front --folder .horde/run --level low --chaos-policy qa/chaos.json
```

Continue with the usual exploration workflow. The generated policy allows at
most one active injection, four admissions per session and 20 seconds per fault,
with at least 10 seconds between admissions. These are caps, not targets.
Edit the JSON or use TOML for your own rules. `chaos init --project shop-front`
saves a policy that future sessions of that named project load automatically.

Add `--dry-run` to `launch` to record injections without applying them. Simulated
injections never count as real fault evidence. Browser exploration still runs,
and ordinary user actions can still change test data.

During a session, the coordinator can run:

```bash
chaosfolk chaos pause --end-active
chaosfolk chaos resume
chaosfolk chaos inspect --folder .horde/run
```

Pause and resume require `CHAOSFOLK_LEADER_TOKEN`. `--end-active` removes reversible
faults; it cannot restore cleared cookies or storage. `inspect` reads the saved
injection plan, its statuses and skip reasons, including after the session ends.

Time windows, coordination between runs sharing a test environment, and incident,
tracking and credential hooks are opt-in. Recurring jobs start disabled unless
explicitly enabled, require a finite attempt budget and timeout, and run through
an external scheduler. Prefer saved scenario replays for recurring fix checks.
Commands or hooks you configure can add runtime and model costs of their own.
See [chaos policies and recurring jobs](docs/chaos.md) for configuration and limits.

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
[Fault injection](docs/faults.md) · [Chaos policies](docs/chaos.md) · [Replay format](docs/replay.md) · [Regressions and CI](docs/regression.md) ·
[Planning](docs/planning.md) · [Integrations](docs/integrations.md) · [Benchmark](docs/benchmark.md) · [Changelog](CHANGELOG.md) · [Contributing](CONTRIBUTING.md) · [MIT license](LICENSE)
