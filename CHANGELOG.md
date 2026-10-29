# Changelog

All notable changes to Chaosfolk are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and versions follow
[Semantic Versioning](https://semver.org/spec/v2.0.0.html). Chaosfolk is alpha
software: until 1.0, a minor version can change commands and file formats.
Each entry explains what the change helps you do and gives an example.

## [Unreleased]

## [0.8.0] - 2026-10-29

Read the [French release note on audit controls and report privacy](docs/release-notes/audit-reliability.fr.md)
for the changes visible to users.

### Added

- Choose Quick, Standard or Deep for a full-product scan, uncheck individual
  tests and keep those choices when changing depth or reopening the dashboard.
  Deep selects every test; the app's features and available accounts/tools
  determine which ones can run. See the release notes in
  [English](docs/release-notes/product-audit-scans.md) or
  [French](docs/release-notes/product-audit-scans.fr.md).
- Follow tests and elapsed time in the local dashboard, set limits and stop new
  work. AI usage appears when the coding tool provides measurements. A model
  request already in progress may continue consuming after the stop.
- Keep unfinished tests across agent batches and record each outcome with
  evidence. Reports show tests the user removed, blocked checks and work still
  to do. The [audit guide](docs/audit-runs.md) covers the commands.

- Release a finished user's browser with `release h01` after coordinated checks
  are complete. Cookies and local storage are saved first; traces and counters
  remain available while other users continue.
- Use `usage --dedup-storage disk` for large exports with many unique requests.
  A temporary SQLite index preserves exact duplicate checks while reducing RAM
  use. The default memory mode remains faster for small exports.
- Verified fixture preparation before every replay trial and divergence retry.
  Configure bounded preparation and verification commands with `--environment`;
  trials run sequentially, and an unavailable or mismatched fixture is invalid.
  For example, restore the same checkout dataset before each of five attempts.
- Reproduction manifests link results to the scenario snapshot, seed, generated
  profiles, catalog/template fingerprints, application build or Git revision,
  browser and engine versions, initial browser-state hashes and fault schedule.
  Missing metadata stays explicit; browser-state contents remain private.
- Optional 2x2 reference comparison with `replay --baseline reference.json`.
  Replay the observed and reference journeys with and without the same fault
  conditions, keeping each journey's own assertions and action anchors. The
  four series and their summary are available in JSON and the session report.

### Changed

- Open large reports with a compact event index and load full event and proof
  details from local files when needed. Reports still work directly from
  `file://`; the detail cache retains at most four chunks and 1 MiB of serialized
  data. Small reports keep their inline format.
- Spill large live error, request and message collections to private SQLite
  files. Small collections stay in memory; larger ones keep exact counts,
  ordering and values while trading disk writes for lower RAM use.
- Index fault windows once per affected user instead of scanning each journey
  again for every fault. Report generation uses a disk index with a bounded page
  cache; the scoring rules remain unchanged.
- Record campaign journals in one pass and retain only referenced action URLs.
  Serialize recovery snapshots progressively and reuse the validated snapshots
  during publication.
- Generate English and French reports progressively through a temporary SQLite
  journal index. Analysis rereads indexed sections, and multi-user extraction
  reads the source journal once while retaining replay evidence.
- Index playback counters, per-user positions, screenshots and finding times.
  Seeking through long reports no longer rescans all preceding events; imported
  journals with unordered timestamps keep their recorded event references.
- Reports separate confirmed defects from reproducible behaviors awaiting an
  expectation, product decisions and suggestions. Findings need
  `qualification: defect` and a sourced `expected_basis` before confirmation or
  default fix selection. Older findings await review. Complete passing replays
  and raw flags no longer add defect penalties.
- Repeated replay action failures remain invalid instead of counting as product
  failures. Page audits exclude inert and disabled controls from keyboard
  signals, check several points for covered controls, and correct small-target
  spacing measurements.
- Resume sessions, filter user traces and export redacted journals progressively,
  avoiding whole-file copies. Campaign recording shares one event index across
  findings. Reproducible CPU and memory comparisons are available in `scripts/`.
- Bound captured hook output to 64 KiB and scheduled job logs to 10 MiB per
  attempt by default. Jobs accept `max_log_bytes` and return 125 on overflow.
- Replay large reports without passing every timestamp as a JavaScript function
  argument. Chronological playback locates visible events with binary search
  and reuses the current view between events. Page audits reuse geometry within
  each synchronous inspection.
- Run all Pyflakes checks in Ruff, audit dependencies in CI, and cancel obsolete
  CI runs when a newer revision is pushed to the same branch or pull request.
- Generate both report languages and the default copy from one escaped JSON
  body, and project scoring fields and playback summaries once when the journal
  is indexed. Report generation reads each event once and no longer reopens a
  freshly written report to copy it. The `usage` summary totals cost in its single
  ingestion pass.
- Accept Pillow 13 for the `visual` extra; Pillow 12.3 carries known
  vulnerabilities that the dependency audit in CI rejects.
- Replay results, CLI and English/French reports show failures / valid trials,
  percentage, invalid trials and requested trials, including small and incomplete
  series. For example, distinguish `1/5` from `5/5` without treating execution
  errors as successful trials. Severity and reproduced-badge rules stay separate.

See [the replay guide](docs/replay.md) and [issue #13](https://github.com/loukan42/chaosfolk/issues/13).

### Fixed

- Preserve concurrent page discoveries and evidence already claimed for review.
  Stop tools whose original claim has been replaced, and reject a delayed dashboard
  start after a newer Stop. Keep Stop reachable while saving or reading the list.
- Preserve unsaved budget edits through request failures and reloads; submit only
  changed limits so another tab's changes survive. Clear recovered connection errors.
- Block redirects in the read-only probe and axe adapter before they can reach
  an unauthorized origin. Redirects require a final URL and remain inconclusive.
- Refuse portable exports containing recognized authentication URLs or sensitive
  controls, including French password labels and OTP autocomplete metadata.
  Omit raw replay diagnostics and observations from public proofs.
- Keep incomplete audit scores provisional and leave the numerical score empty
  until a check has a result. Reject links inside private session folders.
- Recheck stop and exclusions after asynchronous fault admission, before applying
  a fault. An explicit resume requeues interrupted tools and retains their earlier
  evidence; ordinary inconclusive results stay available for review.
- Keep concurrent dashboard checkbox edits from replacing one another. Rejected
  requests receive a stable HTTP response on Windows.
- Preserve audit depth, exclusions and coverage in sanitized reports without
  copying database files, dashboard credentials or worker claims.
- Terminate external test descendants on success, failure and timeout. Close the
  dashboard server explicitly or after 15 minutes without authenticated activity.
- Release finished independent users before opening another wave and enforce a
  configurable open-browser limit, default six. Coordinated users remain available
  until released. Limit queue reads to the requested batch.
- Restrict private session file access on Windows and Unix, including existing
  files. Refuse repository roots and hard-linked session files when securing state.

- Fail report generation with a clear error when evidence contains `NaN` or
  `Infinity` instead of writing a report whose JSON cannot be parsed and
  displays nothing.
- Redact credentials in any URL scheme (`wss://`, `postgres://`, `redis://`)
  and in signature, key, OTP, SAML and OAuth query parameters during privacy
  exports, without swallowing the closing quote or bracket after a value.
- Return a hook's or external runner's own result as soon as it exits, even
  when a descendant it started keeps standard output open; the previous
  behavior reported a timeout and lost the attempt.
- Keep `save-state` from waiting behind a gesture in progress: it reports the
  busy user after ten seconds. `network` lists the other users when one user's
  evidence storage failed, and an action is journaled before its evidence
  flush can fail. A released user's saved state is recorded before the browser
  closes, so a failed close is retried without a second state file.
- Report an unusable campaign lock file or a read-only project folder as a
  command error instead of a traceback, keep the file mode of replaced project
  files on POSIX, and tolerate a map aggregate missing a recorded route.
- Score fault windows from the disk index when a journey carries integer
  timestamps beyond SQLite's range, instead of failing with an overflow error.
- Parse report data as JSON so a supplied `__proto__` field cannot inject
  inherited qualification or replay proof fields into the displayed finding.
  Inline and progressively loaded evidence both preserve that field as data.
- Publish privacy exports only after report generation succeeds. Relocate
  summarized proof sources and reviewed captures under generated filenames,
  and exclude private live-evidence paths from the public copy.
- Synchronize campaign files before replacement and retain pending recovery
  snapshots until publication completes. Clean up command processes when their
  identity lookup fails, and avoid blocked wait threads after hook cancellation.
- Keep MCP registry reads consistent with interrupted campaign recovery. Reject
  usage output paths that are hard links to their input and journal symlinks
  that escape the source folder during privacy export.
- Close browser contexts and cancel pending tasks after initialization failures,
  replay failures and action timeouts. Preserve Unicode line separators inside
  JSONL event text when reading saved evidence.
- Serialize campaign updates across processes, replace each JSON file atomically,
  and count a session's map contribution once. Preserve observations recorded
  during replay and prevent explicit fingerprints from escaping output folders.
  A recovery journal completes interrupted campaign publication on the next
  locked project command, including the archived scenarios and all three indexes.
- Refresh scheduled-job leases between attempts and prevent an old attempt from
  releasing the lease of a newer one.
- Reject malformed MCP tool names without stopping the server. Redact OAuth
  credentials in URL queries and fragments during privacy exports.
- Identify installed skills by their exact frontmatter name and stage a complete
  replacement before publishing it, with rollback on publication failure.
- Honor external-runner timeouts when a descendant keeps stdout open. Opening a
  report card now selects its displayed event even in an out-of-order journal.

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

[Unreleased]: https://github.com/loukan42/chaosfolk/compare/v0.8.0...HEAD
[0.8.0]: https://github.com/loukan42/chaosfolk/compare/v0.7.0...v0.8.0
[0.7.0]: https://github.com/loukan42/chaosfolk/compare/v0.6.0...v0.7.0
[0.6.0]: https://github.com/loukan42/chaosfolk/compare/v0.5.1...v0.6.0
[0.5.1]: https://github.com/loukan42/chaosfolk/compare/v0.5.0...v0.5.1
[0.5.0]: https://github.com/loukan42/chaosfolk/compare/v0.4.0...v0.5.0
[0.4.0]: https://github.com/loukan42/chaosfolk/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/loukan42/chaosfolk/releases/tag/v0.3.0
