# Integrations, privacy and cost

Each command here is optional and runs only when you call it. None of them sends
messages, creates tickets or reaches a remote host you did not name.

## Share a report without private data

```bash
chaosfolk privacy --folder .horde/run --output .horde/run-public --lang en --redact-file qa/private-strings.json
```

The copy drops browser state and typed values, redacts bearer tokens, secret URL
parameters, emails and the exact strings listed in the redaction file, and
excludes screenshots unless you add `--include-reviewed-captures` after looking
at each one. Automatic redaction is incomplete: read `PRIVACY-REVIEW.txt` and
the copy before sharing. The original session is left untouched.

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
