# Changelog

All notable changes to Chaosfolk are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/spec/v2.0.0.html). Chaosfolk is alpha
software: until 1.0, a minor version can change commands and file formats.

## [Unreleased]

## [0.6.0] - 2026-10-27

Confirmed findings can now be kept as tests and replayed in CI.

### Added

- `regression export` writes a portable Python Playwright test from a proven
  scenario, and refuses what it cannot reproduce faithfully. `regression run`
  replays saved scenarios without a model and writes JUnit results; exit code 1
  is a product failure, 2 an invalid or intermittent run.
- `planning changes` proposes journeys from a Git diff and the journey map,
  `planning coverage` tracks planned, passed, failed and untested checks, and
  `planning triage` groups findings that look alike for review.
- `benchmark run|serve|score`: four apps with a known defect and a corrected
  variant, to check the harness and score an exploration (recall, precision
  bounds, host-reported cost).
- `visual capture|compare|approve` for screenshot baselines, with masks and a
  reviewed approval step (optional `visual` extra).
- `privacy` exports a sanitized copy of a report. Password, card and one-time
  code fields are masked in screenshots, plus `CHAOSFOLK_MASK_SELECTORS`.
- `usage` gates the next batch on host-reported tokens and cost.
- `integrations mailpit|file|axe|external`: test mailbox, CSV/text/PDF downloads
  (optional `pdf` extra), a local axe-core bundle, k6 and Appium runners.
- `mcp`: a read-only MCP server over one project memory folder.
- Replays, regression runs and visual captures accept `firefox` and `webkit`.
  An explicit engine never falls back to Chromium.
- `--state-dir DIR` before any command isolates the engine state.

## [0.5.1] - 2026-10-27

Chaosfolk now installs with one command, with nothing to install first.

### Added

- One-command installers for macOS and Linux (`install.sh`) and Windows
  (`install.ps1`). Python, Node.js and Git are no longer needed first: uv
  provides Python when it is missing.
- `chaosfolk setup` makes sure a browser is available, copies the skill into
  every coding agent found and adds Claude Code's simulated user definition.
  Run it again after an update.

### Changed

- The wheel bundles the skill (`SKILL.md` and its guides), so the skill always
  matches the installed engine.
- The README install section is down to one command. pipx, uv and the Skills
  CLI remain documented as alternatives.

## [0.5.0] - 2026-10-27

Random exploration now comes with the checks a QA team would run, and replays
prove persistence instead of trusting success messages.

### Added

- A catalog of 69 QA checks with test values, expected behavior and how to prove
  it: field formats, extreme input, form behavior, persistence, search, passive
  security, UI and WCAG signals. `chaosfolk checks` lists it, and `draw --checks`
  hands each simulated user a share.
- International test values: universal values plus 15 countries, selected with
  `--countries`. A single national pattern applied to every user is a finding.
- `chaosfolk fields` classifies a page's fields in six languages, lists the
  checks that apply and reports structural problems such as a password form sent
  with GET or a session cookie readable by JavaScript.
- `chaosfolk vary` replays a form once per test value of a field, without a model.
- `chaosfolk compare` replays two scenarios in pairs to prove account enumeration
  on sign-in, sign-up and password reset pages.
- `chaosfolk audit` measures a page at several viewports and tabs through it:
  overflow, controls out of reach, target size, accessible names, estimated
  contrast, broken resources, focus traps and JavaScript errors.
- `replay --persist` recipes (`reload`, `revisit`, `new-tab`, `local-only`,
  `back`, `retry`) and the `field-value` assertion, to catch false success, data
  loss, duplicates after a retry and out-of-sync views.
- Project memory: `launch --project` names the app explicitly, `chaosfolk map`
  maps the journeys explored, and `chaosfolk campaign record|compare|select|status`
  compares campaigns and replays open findings to verify fixes.
- Independent or coordinated sessions with roles (`draw --sessions --shared
  --roles`), and scenarios that replay several users in one trial
  (`extract h01,h02`).
- `chaosfolk install-browser` installs Chromium for the engine's Python.
- A step-by-step install guide for Claude Code, Codex, Cursor, GitHub Copilot,
  Gemini CLI, OpenCode and Windsurf, and the trailer video in the README.

### Changed

- Simulated users run on Sonnet in Claude Code, or the lower-cost tier of other
  hosts, and can chain up to four obvious actions per shell call. A failed action
  stops the chain.
- Shorter command prefix with the default state directory; `--say` and `--mood`
  are sent only when they change.
- Persona sheets list the user's QA checks and the variations to try, and ask
  users to confirm every success message by reloading or reopening the record.

## [0.4.0] - 2026-10-26

### Added

- Test themes: `functional`, `ux`, `accessibility`, `resilience`, `security`,
  `performance`, `compatibility` or `all`. The report shows which themes were
  tested, partly tested or left out.
- Run sizes: low (2 users, 12 actions each), medium (4 users, 20) and high
  (12 users, 40), previewed with `chaosfolk plan`.
- More faults drawn automatically, including HTTP errors, lost responses,
  corrupted storage and cleared cookies.
- `chaosfolk probe` opens several local browsers in parallel without model calls,
  as a small smoke test.
- Report: synchronized replay of every tester's screen on one timeline, findings
  with a selectable fix prompt, and an explicit English or French choice.

### Changed

- README rewritten around why, how and what, with recordings of the real report.

## [0.3.0] - 2026-10-26

First public alpha.

### Added

- Seeded behavior profiles with isolated browser sessions and controlled faults.
- Scenario replay with treatment and control trials, and evidence reports in
  English or French.
- A local demo with 12 real Chromium trials and no model or API key.
- The Python engine and a separate agent skill.

[Unreleased]: https://github.com/loukan42/chaosfolk/compare/v0.6.0...HEAD
[0.6.0]: https://github.com/loukan42/chaosfolk/compare/v0.5.1...v0.6.0
[0.5.1]: https://github.com/loukan42/chaosfolk/compare/v0.5.0...v0.5.1
[0.5.0]: https://github.com/loukan42/chaosfolk/compare/v0.4.0...v0.5.0
[0.4.0]: https://github.com/loukan42/chaosfolk/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/loukan42/chaosfolk/releases/tag/v0.3.0
