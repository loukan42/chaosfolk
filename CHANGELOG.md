# Changelog

All notable changes to Chaosfolk are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and versions follow
[Semantic Versioning](https://semver.org/spec/v2.0.0.html). Chaosfolk is alpha
software: until 1.0, a minor version can change commands and file formats.
Each entry explains what the change helps you do and gives an example.

## [Unreleased]

## [0.7.0] - 2026-10-27

Control fault injection across users and test sessions, with optional limits
that keep the existing run budget intact.

### Added

- **Project chaos policies.** Configure allowed faults, probability, cooldowns,
  duration, total injections and simultaneous or affected users in JSON or TOML.
  For example, allow one outage at a time during a four-user checkout test.
- **Target groups and exclusions.** Group users by project, role or matching
  routes, exclude users, roles, routes or HTTP methods, and forbid combinations
  of faults. For example, protect `/payments/*` while injecting a 503 into the
  order API. Request exclusions remain in extracted replay scenarios.
- **Simulation and live controls.** Use `launch --dry-run` to record proposed
  injections without applying them. During exploration, a coordinator can pause,
  resume, enable or disable injections and stop reversible active faults. For
  example, pause new faults when a shared test environment needs attention.
  Browser actions still run during simulation and can change test data.
- **Independent scheduling controls and time windows.** Permit manual immediate
  faults while disabling scheduled ones, or limit injections to configured days,
  hours and a timezone. For example, allow scheduled faults on weekdays while
  the test team is available. Due faults outside a window are skipped.
- **Injection plan and metrics.** Record planned, applied, simulated, skipped and
  cancelled faults with reasons, plus engine and hook error counts. For example,
  use `chaos inspect --folder .horde/run` to see that a fault was skipped because
  another was active. A simulation never becomes real fault-start evidence.
- **Coordination between sessions.** Opt-in SQLite state shares active limits,
  cooldowns and forbidden combinations across processes using the same local
  database and environment key. For example, prevent two CI jobs from injecting
  an outage at the same time. User-fraction and total limits remain per session.
- **Policy reload and incident gate.** Reload changed policies during a session
  and optionally consult a bounded health command before admitting a fault. For
  example, block new injections when an independent test-environment incident
  signal reports an outage. Invalid policies block new injections until corrected.
- **Tracking and credentials for hooks.** Optional commands receive injection
  events or engine errors; credentials can come from environment variables or a
  command. For example, correlate a simulated outage with a test monitoring log.
  Hook output and credentials are excluded from the events Chaosfolk records.
- **Finite recurring jobs.** `chaos schedule` registers foreground commands with
  a maximum attempt count and timeout; an external scheduler calls `run-due`.
  For example, replay a saved checkout regression each weekday. Jobs start
  disabled unless explicitly enabled, and no OS schedule is installed for you.

The controls add no model calls, simulated users or automatic retries. A blocked
injection is skipped rather than waiting for a slot. Explicitly configured hooks
or scheduled commands can incur their own runtime or model costs. The existing
managed local-app fault remains available; cloud and Kubernetes termination
adapters are not included. See [chaos policies](docs/chaos.md).

## [0.6.0] - 2026-10-27

Keep confirmed findings as tests and replay them in CI.

### Added

- **Portable regression tests.** `regression export` turns a supported proven
  scenario into a plain Python Playwright test. For example, keep a reproduced
  lost-draft scenario in your repository and run it after future changes.
- **Regression runs in CI.** `regression run` replays saved scenarios without a
  model and writes JUnit results. For example, fail a pull request when a known
  bug returns; invalid or intermittent trials receive a separate exit code.
- **Change planning.** `planning changes` combines a Git diff, route mappings and
  a journey map to propose what to test. For example, changes to an order editor
  can suggest its editing journey for a focused run.
- **Coverage and triage.** `planning coverage` tracks planned and evidenced
  checks, while `planning triage` proposes groups of similar findings for review.
  For example, see that the reader-role check was skipped and group matching save
  errors without deleting their individual evidence.
- **Benchmark fixtures.** `benchmark run|serve|score` uses four apps with known
  defects and corrected variants to assess the harness or an exploration. For
  example, measure whether a run finds a deliberate duplicate submission.
- **Visual baselines.** `visual capture|compare|approve` compares screenshots,
  with masks and a reviewed approval step. For example, check whether a save
  button moved outside a baseline layout after a CSS change. Requires the
  optional `visual` extra.
- **Report privacy.** `privacy` creates a sanitized report copy, while screenshots
  mask password, card, one-time code and configured selectors. For example,
  prepare a report for a colleague without including browser state; review the
  copy because automatic redaction is incomplete.
- **Host-reported usage limits.** `usage` checks exported token and cost data
  before the next batch. For example, stop assigning more simulated users after
  the host reports that a configured cost limit has been reached.
- **Test integrations.** Mailpit, file checks, axe-core, k6 and Appium runners
  cover optional workflows. For example, inspect a password-reset message in a
  test mailbox or check that a downloaded CSV contains an expected column.
  PDF inspection uses the optional `pdf` extra.
- **Read-only MCP server.** Expose a project memory folder to an MCP client. For
  example, let a compatible client inspect recorded findings without changing them.
- **Firefox and WebKit.** Replays, regression runs and visual captures accept
  these engines as well as Chromium. For example, replay a saved form failure in
  Firefox; an explicitly requested engine never silently falls back to Chromium.
- **Isolated state directories.** `--state-dir DIR` separates engine state. For
  example, run two independent test sessions without sharing their active session.

## [0.5.1] - 2026-10-27

Install the engine, browser and agent skill with a single command.

### Added

- **One-command installers.** `install.sh` supports macOS and Linux, and
  `install.ps1` supports Windows. For example, a teammate without Python can
  install the engine and let uv provide Python when it is missing.
- **Agent and browser setup.** `chaosfolk setup` checks for a browser, installs
  the skill for detected coding agents and adds Claude Code's simulated-user
  definition. For example, run setup again after updating the engine to refresh
  its matching skill.

### Changed

- **Skill bundled with the wheel.** The installed engine carries `SKILL.md` and
  its guides. For example, a wheel installation can install the skill version that
  belongs to that engine without fetching a separate copy.
- **Shorter install guide.** The README leads with the one-command installers and
  retains pipx, uv and Skills CLI alternatives. For example, an existing uv user
  can choose the uv installation instructions.

## [0.5.0] - 2026-10-27

Add concrete QA checks, persistence proofs and memory across campaigns.

### Added

- **QA check catalog.** 69 checks provide test values, expected behavior and
  proof ideas across forms, persistence, search, passive security, UI and WCAG
  signals. For example, a tester can try a double submit and check for duplicates.
- **International test values.** Universal values and values for 15 countries
  can be selected with `--countries`. For example, test British and French phone
  numbers in the same form.
- **Field classification.** `fields` identifies fields in six languages, assigns
  relevant checks and flags structural problems. For example, find a password
  form sent using GET before trying its input values.
- **Form variations.** `vary` replays a form with each selected test value without
  a model. For example, check whether postal codes keep their leading zero.
- **Paired comparisons.** `compare` replays two scenarios to compare outcomes.
  For example, compare password-reset responses for known and unknown test
  accounts to check for account enumeration.
- **Page audit.** `audit` measures viewports and keyboard traversal, reporting
  signals such as overflow, target size, accessible names and focus traps. For
  example, find a submit button outside a 320-pixel viewport. These signals are
  not an accessibility conformance audit.
- **Persistence recipes and assertions.** `replay --persist` can reload, revisit,
  open a new tab, clear local state, go back or retry before checking a value. For
  example, detect a saved message when the record disappears after a reload.
- **Project memory and campaigns.** Named projects keep journey maps, findings
  and replayable scenarios across runs. For example, replay an open finding after
  a fix and revisit less-explored routes in the next campaign.
- **Coordinated sessions and roles.** Users can share test objects and replay a
  multi-user scenario. For example, have two editors change the same synthetic
  record to look for lost updates.
- **Browser installation command.** `install-browser` installs Chromium for the
  engine's Python. For example, repair a setup where `chaosfolk check` reports a
  missing browser.
- **Agent installation guide and trailer.** The guide covers Claude Code, Codex,
  Cursor, GitHub Copilot, Gemini CLI, OpenCode and Windsurf. For example, follow
  the Codex instructions when automatic agent detection misses it; the README
  trailer shows the product workflow.

### Changed

- **Lower-cost tester execution.** Simulated users use Sonnet in Claude Code or
  the lower-cost tier of other hosts, and can chain up to four obvious actions per
  shell call. For example, combine straightforward clicks and typing; a failed
  action stops the chain.
- **Shorter command traffic.** The default state directory uses a shorter command
  prefix, and `--say`/`--mood` are sent only on change. For example, repeated
  browser actions do not need the same mood argument each time.
- **QA checks on persona sheets.** Sheets include checks and variations, and ask
  testers to confirm success messages by reloading or reopening the record. For
  example, verify that a newly saved item remains visible after reload.

## [0.4.0] - 2026-10-26

Choose the scope and size of an exploratory run and inspect its evidence.

### Added

- **Test themes.** Choose functional, UX, accessibility, resilience, security,
  performance, compatibility or all. For example, request accessibility and
  resilience and see which themes were tested, partly tested or left out.
- **Run sizes.** Low uses 2 users and 12 actions each, medium 4 and 20, high 12
  and 40. For example, use `chaosfolk plan --level low` to preview a shorter pass.
  These are action caps, not token limits.
- **Additional drawn faults.** Include HTTP errors, lost responses, corrupted
  storage and cleared cookies. For example, drop a response after a write to
  examine whether retrying creates a duplicate.
- **Local browser probe.** `probe` opens several browsers in parallel without
  model calls as a small smoke test. For example, inspect page errors and timing
  while several synthetic clients open a local page.
- **Report and synchronized replay.** Watch tester screens on one timeline,
  select findings for a fix prompt and choose an English or French report. For
  example, jump to the moment a simulated user encounters a failed save.

### Changed

- **README and recordings.** The README explains why and how Chaosfolk works and
  shows recordings from its report. For example, a new user can inspect the
  evidence workflow before installing it.

## [0.3.0] - 2026-10-26

First public alpha for exploratory browser testing with simulated users.

### Added

- **Profiles, browser sessions and faults.** Seeded behavior profiles operate in
  isolated browser sessions with controlled faults. For example, compare how
  different simulated users navigate a form when a connection drops.
- **Replays and evidence reports.** Treatment and control trials reproduce a
  scenario, with reports in English or French. For example, check whether a
  failure appears with a fault and disappears in the control trials.
- **Local demo.** Run 12 real Chromium trials without a model or API key. For
  example, try the workflow on the included synthetic app before testing your own.
- **Python engine and agent skill.** Install the engine and skill separately. For
  example, use the engine to drive browsers while a compatible coding agent
  coordinates simulated users.

[Unreleased]: https://github.com/loukan42/chaosfolk/compare/v0.7.0...HEAD
[0.7.0]: https://github.com/loukan42/chaosfolk/compare/v0.6.0...v0.7.0
[0.6.0]: https://github.com/loukan42/chaosfolk/compare/v0.5.1...v0.6.0
[0.5.1]: https://github.com/loukan42/chaosfolk/compare/v0.5.0...v0.5.1
[0.5.0]: https://github.com/loukan42/chaosfolk/compare/v0.4.0...v0.5.0
[0.4.0]: https://github.com/loukan42/chaosfolk/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/loukan42/chaosfolk/releases/tag/v0.3.0
