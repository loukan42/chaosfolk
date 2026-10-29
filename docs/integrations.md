# Integrations, privacy and cost

Each command here is optional and runs only when you call it. None of them sends
messages, creates tickets or reaches a remote host you did not name.

## Share a report without private data

```bash
chaosfolk privacy --folder .horde/run --output .horde/run-public --lang en --redact-file qa/private-strings.json
```

The copy drops browser state and typed values, redacts bearer tokens, user
information in any URL scheme, credential-like URL parameters (tokens, secrets,
signatures, keys, one-time codes, SAML and OAuth values), emails and the exact
strings listed in the redaction file, and excludes screenshots unless you add `--include-reviewed-captures` after looking
at each one. Automatic redaction is incomplete: read `PRIVACY-REVIEW.txt` and
the copy before sharing. The original session is left untouched.
Raw replay screens, observation snapshots and assertion diagnostics are omitted
from public proofs because they can contain field values. Trial outcomes and counts
remain available; inspect detailed diagnostics in the original private session.

The read-only `probe` and axe integration block HTTP redirects before following
them, including same-origin redirects. Supply the final authorized URL. A blocked
redirect or resource makes the result inconclusive. Requests use a controlled relay,
so probe timings include that overhead.

Exports are prepared in a temporary sibling folder and published only after
report generation succeeds. A failed generation leaves the destination absent
or empty, so the same command can be retried. Existing nonempty output folders
are never replaced. Internal proof paths are relocated into the exported copy;
proofs outside the source session are rejected before reading them.

During exploration, password, card and one-time code fields and elements with
`data-chaosfolk-private` are masked in screenshots. Add selectors with
`CHAOSFOLK_MASK_SELECTORS='[".balance", "#iban"]'`.

## Usage and cost

Chaosfolk cannot see model tokens; your agent host can. Export one JSON line per
model request, measured by the host:

```json
{"id": "req-1", "source": "host", "input_tokens": 1200, "output_tokens": 300, "cost": 0.0042, "currency": "USD"}
```

```bash
chaosfolk usage --input usage.jsonl --max-tokens 500000 --max-cost 2
```

Exit code 0 means continue, 1 means a limit is reached, 2 means a limit was set
but a value is missing. Run it before each batch of simulated users. It does
not stop a model request already running, and it never converts currencies.

For large exports with many distinct request IDs, add `--dedup-storage disk`:

```bash
chaosfolk usage --input usage.jsonl --max-tokens 500000 --dedup-storage disk
```

The default keeps complete measurements in memory to compare repeated IDs.
Disk mode keeps those records in a temporary SQLite index, with a 2 MiB page
cache. Both modes count identical events once and reject conflicting events
with the same ID. Disk mode trades extra disk space and processing time for
lower memory use; it still needs enough memory for one JSON record. The index
is removed when the command finishes, including validation failures. A forced
process termination can leave a `chaosfolk-usage-*` folder in the system
temporary directory containing the supplied measurements. This option does
not reduce model token usage.

## Test mailbox (Mailpit)

```bash
chaosfolk integrations mailpit --url http://127.0.0.1:8025
chaosfolk integrations mailpit --message ID --subject "Reset your password" --contains "/reset?code="
```

Listing shows ids and subjects only. Checking reads one message and reports which
expectations hold. It never sends, releases, deletes or marks messages read.
A non-local Mailpit needs `--allow-origin`.

## Downloaded files

```bash
chaosfolk integrations file export.csv --column email --min-rows 1
chaosfolk integrations file invoice.pdf --contains "Total"
```

CSV, text and PDF (with `python -m pip install "chaosfolk[pdf]"`). The result
gives the checks, size and a hash, not the file content.

## Accessibility with axe-core

Chaosfolk does not download axe-core. Point it to a copy you trust:

```bash
chaosfolk integrations axe --url http://localhost:3000/signup --script vendor/axe.min.js
```

Requests to other origins are blocked and counted; the result is then
`inconclusive`. Automated rules cover part of WCAG only.

## Load and native mobile

```bash
chaosfolk integrations external --tool k6 --executable /usr/local/bin/k6 --script load/smoke.js
chaosfolk integrations external --tool appium --executable ./run-mobile --script mobile/suite.py
```

Chaosfolk runs the program you name, without a shell, with a timeout and an
output limit. For k6 the verdict comes from its summary export; for Appium the
program writes `{"tests", "failures", "errors", "skipped"}` to the path in
`CHAOSFOLK_RESULT_PATH`. A run with no machine-readable result is `inconclusive`.

All integration commands print JSON and accept `--output`. Exit code 0 passed,
1 failed, 2 error or inconclusive.

## MCP server

```bash
chaosfolk mcp --project-dir ~/.chaosfolk/projects/shop-front
```

A read-only MCP server over stdio for one project memory folder. Tools:
`campaign_status`, `list_findings` and `list_scenarios`. It exposes counts,
fingerprints, states and scenario names, never titles, evidence, scenario
bodies or file paths. Example client configuration:

```json
{"mcpServers": {"chaosfolk": {"command": "chaosfolk", "args": ["mcp", "--project-dir", "/home/me/.chaosfolk/projects/shop-front"]}}}
```

Each metadata request waits for the project writer lock. If a prior campaign
publication was interrupted, it finishes that pending publication before
reading, using the same recovery checks as the campaign CLI. This prevents
counts from combining an updated history with an older findings registry.
The process needs write access to the selected project folder for this lock
and recovery step.
