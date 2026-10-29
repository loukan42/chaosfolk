# Chaosfolk engineering audit 28 October 2026

This audit examined resource use, browser lifecycle, campaign persistence,
process execution, privacy exports, MCP input handling, installation, reports,
packaging and CI. Three specialist agents implemented and reviewed performance,
security and architecture changes; the coordinating agent reviewed their changes,
optimized report playback and page inspection, and ran integration checks.

The starting repository revision was `4a863d4`. A separate task, “Réduire les
faux positifs”, changed scoring, report qualification and accessibility rules in
the same checkout during this work. Those changes were preserved. They are not
claimed as outcomes of this audit.

The first complete test run passed 314 tests with two platform-specific skips.
The project already had loopback authentication, process-ownership checks,
replay assertions and browser integration tests. The fixes below address
specific failures and repeated work found in that implementation.

| Area | Finding and delivered change | Regression evidence |
| --- | --- | --- |
| Session memory | Resume loaded the journal text, split lines and decoded events simultaneously. It now consumes normalized events progressively; `trace` retains only the selected user's events. | `test_engine_efficiency.py`; journal benchmark |
| Evidence integrity | `splitlines()` split valid JSON strings containing U+2028/U+2029 and lost events. File iteration preserves those strings. | Unicode journal regressions |
| Socket copies | Receiving each response block copied the preceding response. A bytearray now accumulates blocks. | Fragmented response test |
| Browser lifecycle | Initial navigation and initialization errors could leave contexts open. Failed startup, timed-out actions and cancelled actions could leave tasks pending. Cleanup now closes contexts and cancels and awaits tasks. | Failure, cancellation, timeout and dialogue tests |
| Campaign CPU | Each finding rebuilt the complete action index; map generation reread the same journal. Recording now shares both. | Equivalent fingerprints and benchmark |
| Campaign paths | Explicit fingerprints could become paths outside the archive or replay directory. Unsafe identities now use hashed filenames while retaining their original registry identity. | Archive and replay path regressions |
| Campaign concurrency | Concurrent read/modify/write operations could lose updates. A per-project SQLite lock now protects updates; JSON replacement is atomic per file. Replay checks for concurrent changes before publishing its result. | Two-process lock, parallel recording and concurrent replay tests |
| Interrupted publication | A write failure after saving campaign history could leave results missing and prevent retry. A validated recovery journal now stages scenarios and indexes before publication; the next locked project command completes an interrupted publication. | Injected write failure followed by recovery; unsafe destination rejection |
| Campaign counts | Mapping a session and then recording it counted its visits twice. Per-session contributions now replace their prior values. Rebasing also copies a scenario before modifying its URLs. | Repeated merge, map then record and rebase tests |
| Usage ingestion | Whole-file JSONL parsing and a second unique-event list duplicated memory. Input is streamed and exact duplicate identities still count once. Unknown usage remains unknown. | Usage regression tests and synthetic benchmark |
| Scheduler | Later jobs could inherit a stale reservation time; an old job could release a successor's lease. Each reservation now uses the current time and completion verifies job identity and attempt. | Long-job and replacement regressions |
| Output budgets | Captured hooks could spool arbitrarily large stdout until timeout. Capture is now limited to 64 KiB in memory. Job logs default to 10 MiB per attempt; configurable `max_log_bytes` stops the owned process on overflow and returns 125. | Real child-process tests and exact log size assertions |
| External runners | A descendant inheriting stdout could block cleanup beyond the runner timeout. Nonblocking reading now includes pipe drainage in the deadline and needs no reader thread. | Real subprocess, inherited pipe, EOF and timeout tests |
| Privacy | OAuth query and fragment credentials and URL user information could survive exports. The redactor now covers those forms; JSONL export writes progressively. | Redacted HTML export and source-preservation tests |
| MCP | A non-string tool name could crash request dispatch. Type validation now returns a protocol error; pagination avoids copying the whole registry. | Malformed call followed by a valid call |
| Installation | Prefix matches could identify another skill as Chaosfolk. Exact frontmatter matching replaces that check. A complete staged copy and rollback protect an existing installation from copy/publication failures. | Wrong skill, interrupted copy, rollback and backup-preservation tests |
| Report playback | Spreading all timestamps into `Math.min/max` failed on large journals. Per-frame filtering also rescanned the journal. Reductions avoid argument limits; binary search finds the visible prefix and view rebuilding waits for an event change. | 150,000-event browser test, backward seeks and imported event order |
| Page inspection | Multiple checks repeated geometry and style measurements. A synchronous pass now caches them per element. Prototype-named IDs are counted correctly. | Real browser geometry-count and duplicate-ID tests |
| Quality controls | Ruff checked only a subset of Pyflakes. All `F` rules now run. CI cancels superseded runs and includes a dependency audit with optional integrations. | Local Ruff check; workflow changes require a remote CI run |

The benchmarks compare equivalent outputs using synthetic data on Windows with
Python 3.14. They are function-level measurements, not a claim about total
application speed, browser RSS, energy consumption or model spending.

| Measurement | Previous algorithm | Current algorithm |
| --- | ---: | ---: |
| Resume 20,000 events from a 22.693 MiB journal, peak Python allocations | 68.365 MiB | 0.159 MiB |
| Same resume, median of three runs | 338.7 ms | 263.1 ms |
| Fingerprint 200 findings against 10,000 events, median of five runs | 234.18 ms | 2.38 ms |
| Read 20,000 usage rows with 100 repeated identities, peak Python allocations | 17,576,686 bytes | 70,710 bytes |

The usage fixture intentionally includes overlapping exports. Default in-memory
deduplication still stores one record per unique identity; the second pass below
adds a disk option for exports with many unique records. The journal benchmark measures Python allocations
with `tracemalloc`, not operating-system process memory. Reproduce the measurements:

```powershell
.venv/Scripts/python.exe scripts/benchmark_journal.py --events 20000 --repeat 3
.venv/Scripts/python.exe scripts/benchmark_resources.py
```

The dependency audit found advisories for the development environment's old pip
25.2. It was upgraded locally to 26.2.2. A second `pip-audit` check against all 31
installed package versions, including inherited packages, found no known
vulnerabilities. This is a package-advisory check, not a security certification.
The local audit excludes the editable Chaosfolk package, whose source was reviewed
directly. Audit inputs and results are under `.horde/audit-20261028/` and ignored
by Git.

The second pass addressed report generation, playback indexing, finished browser
contexts and exports with many unique usage records:

| Area | Delivered change | Regression evidence |
| --- | --- | --- |
| Report generation | `reporting.py` projects the journal into a temporary SQLite database with a 2 MiB page cache. Reports encode JSON and HTML progressively; the default language is copied from its completed report. Anomaly positions, counts, evidence and scoring are preserved. | Report equivalence, unordered scoring and temporary-resource cleanup tests |
| Analysis and extraction | Analysis aggregates per-user summaries and rereads indexed sections. Single-user and coordinated extraction consume the journal once, retaining replay steps and fault evidence. | Notes, counters, cutoff, restart and multi-user extraction tests |
| Playback | A reusable index stores prefix counters, per-user event and screenshot positions, completion times and finding times. Binary searches replace repeated prefix scans; person selection reuses grouped events. | Randomized forward/backward seek comparisons and real report UI tests |
| Finished browsers | Leader-only `release h01` saves cookies/localStorage and closes a finished user's context after coordinated checks. It rejects active users, pending downloads and relevant pending/active faults. Evidence and counters remain available. | Browser lifecycle regressions and a real Chromium test with another user still active |
| Usage records | `usage --dedup-storage disk` stores complete records in temporary SQLite for exact duplicate checks. The memory mode remains the default. Output paths cannot overwrite an input through a hard link. | Duplicate conflicts, numeric validation, gates, cleanup and hard-link regressions |
| MCP and privacy | MCP reads acquire the project lock and recover pending publications before reading related registries. Privacy export rejects journal symlinks outside its source folder. | Recovery, SQLite-error handling and path confinement regressions |

These additional measurements use synthetic local fixtures on Windows/Python
3.14 with Playwright 1.64.1 and Chromium 156.0.8078.4. The report and usage variants
run in separate processes and verify identical evidence or results.

| Measurement | Previous/default behavior | Optimized behavior |
| --- | ---: | ---: |
| Generate reports for 5,000 events with 4 KiB screen payloads: peak Python allocations | 46,835,673 bytes | 1,777,449 bytes |
| Same generation: sampled process peak RSS | 90,013,696 bytes | 32,456,704 bytes |
| Same generation: elapsed time with allocation tracing enabled | 0.318 s | 0.421 s |
| Aggregate 200 playback seeks over 100,000 events, median of three runs | 1,087 ms | 0.7 ms, plus 29 ms to build the index |
| Deduplicate 25,000 unique usage records with 2 KiB metadata: process peak RSS | 99,946,496 bytes | 28,352,512 bytes with disk storage |
| Same usage export: elapsed time | 0.125 s | 1.125 s |
| Four Chromium users, three finished: sum of process working sets, median of three runs | 540.98 MiB retained | 245.26 MiB after release |
| Same browsers: CPU across processes, where 100% is one core | 45.84% | 10.87% |

The playback measurement covers aggregation, excluding DOM rendering and data
loading. Report RSS is sampled every 5 ms and includes SQLite's native cache.
The browser fixture gives each user a touched 16 MiB heap and 3 ms of work every
25 ms; shared pages may count in several process working sets. The browser run
was isolated from other benchmark runs and verifies saved state, recorded traces
and continued operation of the fourth user. These are workload-specific resource
measurements. Neither model spending nor energy consumption was measured.

```powershell
.venv/Scripts/python.exe scripts/benchmark_reporting.py --events 5000 --screen-bytes 4096
.venv/Scripts/python.exe scripts/benchmark_playback.py
.venv/Scripts/python.exe scripts/benchmark_usage.py
.venv/Scripts/python.exe scripts/benchmark_browser_resources.py --users 4 --repeat 3
```

The third pass reduces the costs that remained in report loading, live evidence,
campaign recording and repeated fault scoring. It also fixes publication and
privacy defects found while reviewing those paths.

| Area | Delivered change | Verification |
| --- | --- | --- |
| Large browser reports | Above 4 MiB of projected journal and metadata, HTML carries an event index and reads full details from content-addressed local scripts. A four-chunk/1 MiB serialized cache and two concurrent loads limit retained detail data. Missing files show an error and retry control. Small reports keep inline data. | Full event/proof reconstruction; file:// EN/FR, stale-response, cache eviction, missing-file and privacy tests |
| Live evidence | Error lists, request counters and notices spill to private SQLite after 512 entries or 256 KiB of estimated string storage. Counts, order and values remain exact. Storage failures stop collection and invalidate affected assertions. | Collection equivalence and failure tests; Chromium produces 520 fetches and 520 page errors, checks assertions and then releases its context |
| Fault scoring | Each affected journey is read once into a timestamp/blocker index. Reports use a disposable SQLite index with a 1 MiB page cache. Fault-window and recovery rules are unchanged. | Memory/disk comparisons against the previous algorithm over 40 randomized datasets; source-read-once and exception cleanup tests |
| Campaign recording | One journal pass retains only the action URLs referenced by findings. Recovery snapshots are encoded progressively and reused during publication. Files are synchronized before replacement; supported POSIX directories are synchronized too. | Equivalent campaign results and files; interrupted writes, pending-journal limits and recovery tests |
| Process cleanup | External adapters retain process identity rather than looking up a bare PID during cleanup. Hooks avoid a blocked wait thread; identity-lookup failures still clean up the spawned process. | Process-identity, cancellation, timeout and failed-initialization regressions |
| Public exports | A temporary sibling folder is published only after successful generation. Proofs, including summarized sources, use generated filenames; reviewed captures resolve their original paths before redaction. Private database references are excluded. | Failed generation and rename, concurrent output, internal/escaping proof paths, private filenames and reviewed-capture tests |
| Report interpretation | A JSON `__proto__` property could supply inherited qualification and proof fields when embedded as a JavaScript object literal. Reports now parse JSON, escaping it progressively, so the UI cannot confirm a finding through those inherited values. | Actual generated reports in Chromium, inline/progressive and EN/FR; own-property and prototype checks; Python/UI qualification agreement; script delimiters and Unicode retained |

Further reproducible measurements compare the preceding implementations with
the third-pass changes. Live-evidence figures are medians of three isolated
Python processes per variant. The fixture writes 100,000 page errors and request
events across 20,000 distinct routes, with identical error and counter hashes.

| Measurement | Previous implementation | Third-pass implementation |
| --- | ---: | ---: |
| Live evidence: process peak RSS | 78.586 MiB | 35.121 MiB |
| Live evidence: peak Python allocations | 31.916 MiB | 0.114 MiB |
| Live evidence: CPU / wall time | 3.875 s / 3.901 s | 5.688 s / 6.001 s |
| Live evidence: additional SQLite disk space | 0 | 29.656 MiB |
| Campaign journal, 30,000 events with 1 KiB payloads: peak Python allocations | 46,869,755 bytes | 114,536 bytes |
| Same campaign journal: elapsed time | 0.5746 s | 0.5639 s |
| Publication of 4,000 campaign snapshots: peak Python allocations | 9,983,891 bytes | 157,816 bytes |
| Same publication: elapsed time | 0.2071 s | 0.2561 s |
| Score 150 faults over 50,000 actions: median of three runs | 0.5006 s | 0.0700 s with disk index; 0.0158 s with memory index |

The final browser measurement compares the current safe JSON format with and
without progressive loading. It uses fresh Chromium processes, 12,000 events
with 2,048 bytes of reaction text each, local `file://` URLs and an explicit
garbage collection before each heap reading. The traversal follows the actual
chunk manifest, so every one of the 107 chunks is visited.

| Browser measurement | Inline report | Progressive report |
| --- | ---: | ---: |
| Initial JavaScript heap | 28,393,428 bytes | 2,398,784 bytes |
| JavaScript heap after traversal | 28,424,068 bytes | 3,025,356 bytes |
| Initial HTML file | 28,444,473 bytes | 1,995,449 bytes |
| Initial readiness | 0.410 s | 0.133 s |

Loading the full set of progressive chunks takes 3.256 seconds in this run.
The final cache contains four chunks totaling 871,173 serialized bytes, with
zero pending or active loads. This measures JavaScript heap, not complete
Chromium RSS or image decoding memory. The final generator benchmark also
checks identical evidence: on 5,000 events with 4 KiB screen payloads, process
peak RSS is 91,414,528 bytes for the reconstructed eager generator and
32,620,544 bytes for progressive generation. Generation takes 0.319 and
0.595 seconds respectively with Python allocation tracing enabled.

The live-evidence change saves RAM at the cost of CPU, writes and disk space;
small sessions do not open a database. The fault index also trades storage for
fewer repeated scans. Python allocation figures exclude native SQLite pages;
the live-evidence process RSS includes them. No model cost or energy saving is
inferred from these measurements.

```powershell
.venv/Scripts/python.exe scripts/benchmark_browser_reports.py --events 12000 --text-bytes 2048
.venv/Scripts/python.exe scripts/benchmark_live_evidence.py --events 100000 --routes 20000 --repeat 3
.venv/Scripts/python.exe scripts/benchmark_campaigns.py
.venv/Scripts/python.exe scripts/benchmark_scoring.py
```

The operating constraints are explicit:

- A large report's structural event index still grows with event count. Visible
  text/images and an individual oversized event or proof require their own
  memory, beyond the bounded detail cache. Keep `assets/journal/` with the HTML.
  Old content-addressed chunks remain available for previously opened reports.
  Distinct anomaly summaries and extracted scenarios grow with their output;
  complete requested dumps also require memory for the response text.
- Live evidence commits every 256 writes and at command/close boundaries.
  Abrupt termination can lose the last uncommitted batch. SQLite files and their
  WAL files contain private evidence; the timestamped anomaly journal remains
  the primary recorded trace. This is bounded collection memory, not a promise
  of bounded storage or total process memory.
- Browser contexts remain open until the coordinator releases them or stops
  the session. Release is explicit because closing a finished user's browser
  can affect coordinated checks and post-session inspection.
- Campaign recovery is limited to batches of 64 MiB and 10,003 JSON files. It
  handles interrupted publication. File synchronization reduces lost-write risk
  but does not guarantee recovery from storage corruption or every power cut.
  Historical map counts predating per-session tracking
  cannot be deduplicated automatically.
- The `usage` gate checks host measurements between batches. It cannot cancel
  requests already running in an external model host. No token or monetary
  saving was measured in this audit.
- Log limits cover captured stdout and stderr. A configured command can write
  other files. Descendants that detach from an owned process remain outside a
  guaranteed containment boundary.
- Loopback authentication does not isolate agents sharing an OS account. The
  browser has no network-origin sandbox. Privacy exports still require review
  before sharing screenshots or application-specific text.
- `reporting.py` now owns journal projection and progressive rendering.
  `engine.py` still combines browser actions, faults, replay and CLI orchestration.
  Further extraction should follow responsibility boundaries and compatibility
  tests; moving code alone does not establish a resource benefit.
- Windows/Python 3.14 was tested locally. The existing Linux/Windows and
  Python 3.12/3.14 CI matrix remains the cross-platform check. POSIX-only process
  ownership and Windows symlink permissions cannot both be exercised on this host.

The first-pass combined checkout passed `python -m pytest -q --tb=short -ra`: **442 passed,
3 skipped in 201.53 seconds**. The skipped cases require Windows symlink
permission or POSIX process groups. Ruff with all Pyflakes rules and
`git diff --check` passed. Earlier integration failures caused by concurrent
report changes were resolved before this run. The accessibility fixture now
uses a full-size adjacent target to exercise a real target-spacing violation.

After the second pass, the complete combined checkout passed the same command:
**518 passed, 4 skipped in 197.71 seconds**. Three skipped tests require Windows
symlink permission; one requires POSIX process groups. Ruff and
`git diff --check` pass. This run includes report UI tests, the new release
lifecycle tests, scoring equivalence and the concurrent task's changes.

The third pass first passed **664 tests with 4 skips**. The final JSON-parsing
security fix added three cases. Its complete run passed **666 tests**, skipped
the same four platform cases, and exposed one obsolete assertion that searched
for unescaped JSON directly in demo HTML. That assertion now decodes the report
data and verifies the French language value. The corrected demo test passed in
**6.75 seconds**, yielding **667 validated cases and 4 platform skips** across
the full run and focused rerun. No runtime code changed after that full run.
The real Chromium live-evidence and progressive-report tests are included.
Final Ruff and `git diff --check` also pass.

The wheel and source archive build successfully. Build artifacts are under
`.horde/audit-20261028/dist/`. A separate virtual environment installed the wheel
and passed version, environment/browser check, skill installation, seeded draw,
sheet generation and packaged-asset checks. The wheel's Python, JavaScript, HTML
and JSON files matched the source checkout at that check. An initial Windows
rename refusal did not recur in the comparative diagnostic or the final complete
smoke test; no filesystem permissions were changed.

The second-pass wheel and source archive were rebuilt successfully. The isolated
wheel environment passed the complete smoke test again, including the new
`playback.js` asset and source-to-wheel equality checks. CI now also checks the
installed report assets from outside the source checkout.

The final third-pass wheel was rebuilt, installed separately and checked against
every Python, JavaScript, HTML and JSON source file. The smoke test passes version,
environment/browser check, skill installation, seeded draw, sheets and packaged
assets, then generates a progressive report from six large synthetic events
through the installed CLI. Its manifest, detail files and all three report
scripts are present. The source archive was rebuilt after the demo-test update.

The updated workflow has not run on GitHub in this task. Changes are local and
have not been released.

## Fourth pass: independent review of the three passes (29 October 2026)

The uncommitted result of the first three passes was reviewed again before
publication: three reviewers read the complete diff by area (engine, evidence
and fault index; campaigns, scheduler, privacy, usage, installation and MCP;
reporting, templates and page audit), ran differential checks against the
previous algorithms, and the coordinating agent profiled report generation.
Fault scoring was compared with the legacy algorithm over 2,400 random fixtures
and 400 random spool-backed journals without a mismatch. The deliberate scoring
changes from the “Réduire les faux positifs” task (qualification, `expected_basis`,
zero penalty for observations) remain outside this audit's claims.

| Area | Finding | Delivered change |
| --- | --- | --- |
| Report integrity | `JSON.parse` rejects the `NaN`/`Infinity` tokens Python emits by default; a report built from such evidence displayed nothing while generation reported success. | All report and detail-chunk encoders use `allow_nan=False`; generation fails with an error and the previous report stays in place. |
| Report CPU | Each language re-encoded the metadata with the pure-Python encoder and re-streamed the journal; the playback index decoded every full payload to keep ten fields; the default report reopened a freshly written file. | The journal is indexed once with `executemany`, projected scoring and summary columns, two indexes instead of four and no rollback journal. One escaped body serves both languages and the default copy; metadata uses the C encoder. |
| Privacy export | User information was redacted only in `http(s)://` URLs; signature, key, OTP, SAML and OAuth parameters survived; the value pattern swallowed the closing quote; dropped fields were redacted before being removed. | Scheme-generic user-information redaction, a credential parameter list, values that stop at closing delimiters, and fields dropped before redaction. |
| Hooks and runners | Output capture completed on pipe EOF. A descendant inheriting standard output turned a finished hook into a timeout, and the finished root could no longer be stopped by identity. | Capture returns once the root has exited and a final read yields nothing; `TimeoutExpired` after a kill is handled. |
| Session commands | `save-state` waited without limit behind a gesture; one user's evidence failure hid every user's `network` counters; a failed evidence flush skipped the executed action's journal line; a failed close after `release` left an unreferenced state file; concurrent closes cancelled each other. | Ten-second lock wait, per-user error lines, journal before flush, state recorded before close, one shared close task. |
| Campaign robustness | Lock-file and connection errors escaped as tracebacks; atomic replacement left 0600 files on POSIX; a map aggregate missing a recorded route raised `KeyError` during publication. | Clear command errors, preserved file modes, tolerant subtraction. |
| Usage | Cost was summed in a second pass over every stored record. | Cost accumulates during ingestion. |
| Fault index | The disk index raised `OverflowError` for integer timestamps beyond SQLite's range while the memory index handled them. | Out-of-range integers are stored as floats, preserving order. |

Measurements use the same synthetic fixtures as the earlier passes, on Windows
with Python 3.14. Report figures compare the third-pass implementation with the
fourth-pass one in the same process layout.

| Measurement | Third pass | Fourth pass |
| --- | ---: | ---: |
| Generate reports for 5,000 events with 4 KiB screen payloads, elapsed without tracing | 0.281 s | 0.154 s |
| Same generation, elapsed with allocation tracing (benchmark script) | 0.582 s | 0.460 s |
| Same generation, process peak RSS | 33.2 MiB | 35.2 MiB |
| Deduplicate 25,000 unique usage records with disk storage | 1.100 s | 0.824 s |
| Score 150 faults over 50,000 actions, disk index | 0.066 s | 0.068 s |

Report generation on this host is now dominated by file creation and
antivirus scanning of new files, not by Python work: profiling attributed
0.13 s of the 0.35 s profiled run to reopening the just-written report for the
default copy, which the fourth pass avoids by writing the default copy from the
shared body. With 12,000 events the streamed generator takes 1.05 s with
tracing and 38 MiB peak RSS against 0.71 s and 176 MiB for the eager baseline.
Above the 4 MiB inline threshold the report switches to progressive loading;
`benchmark_reporting.py` then compares metadata only and reports that mode.

Remaining observations that were not changed, with the reason:

- Content-addressed detail chunks under `assets/journal/` are never garbage
  collected. This is documented behavior so that an open report keeps reading
  its evidence after regeneration; each regeneration during a live session adds
  the changed tail chunk and changed proofs. Remove the folder when archiving.
- Live evidence writes one SQLite statement per record after spilling. Batching
  would save roughly one second per 300,000 records in the synthetic benchmark;
  real sessions write far fewer records than browser latency allows, so the
  simpler exact implementation was kept.
- `EvidenceStore.close()` leaves a temporary directory in place when no session
  folder was supplied, until the object is collected. Live sessions and replays
  always supply a folder.
- An oversized single event above the 1 MiB detail cache is reloaded whenever
  its card is rendered. Such events are rare and the cache bound is deliberate.

The complete suite passed after these changes: **699 passed, 4 skipped in
209.86 seconds**, with the same four platform skips. Ruff with all Pyflakes
rules, `git diff --check` and the wheel build pass. Working-copy CRLF line
endings introduced by editors on Windows were normalized to LF, matching
`.gitattributes`. Nothing has been committed or pushed, and the updated
workflow has still not run on GitHub.
