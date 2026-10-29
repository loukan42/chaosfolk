# Regression tests, CI and visual checks

A proven scenario (see [replay.md](replay.md)) can become a test that stays in
your repository and runs without a model.

## Export a portable Playwright test

```bash
chaosfolk regression export .horde/run/scenarios/h02-save.json --output tests/regressions/test_save_draft.py
```

The file is a plain Python Playwright test with no Chaosfolk import. It runs under
pytest or directly with `python test_save_draft.py`. The export refuses what it
cannot reproduce faithfully instead of dropping a step:

- several sessions, a virtual clock, uploads and faults other than `offline` and
  `storage-full`;
- inline browser state, credentials in a URL and typing into a password field.
  Pass a Playwright storage-state file at run time with `CHAOSFOLK_STORAGE_STATE`;
- tolerant steps that failed in the original run, and fault schedule warnings.

It never overwrites an existing file. Review the synthetic inputs before you
commit the test, and reset the app data before each run.
New browser recordings mark password and one-time-code controls as sensitive,
regardless of their displayed name. Export also checks authentication parameters
in URL queries and fragments, including hash-router callbacks. Older recordings
without control metadata still need review before sharing.

Run time options:

| Variable | Effect |
| --- | --- |
| `CHAOSFOLK_BASE_URL` | Replaces the recorded origin, for a CI or preview server. |
| `CHAOSFOLK_STORAGE_STATE` | External signed-in state, required when the scenario had one. |
| `CHAOSFOLK_BROWSER` | `chromium` (default), `firefox` or `webkit`. |

## Run saved scenarios in CI

`regression run` replays scenarios with the Chaosfolk engine, writes `junit.xml`
and `summary.json`, and keeps every trial in a fresh `run-*` folder.

```bash
chaosfolk regression run qa/scenarios/*.json --output qa-results --times 3
```

| Exit code | Meaning |
| --- | --- |
| 0 | Every scenario passed every trial. |
| 1 | A product failure: the assertion failed on every trial. |
| 2 | Not a product verdict: invalid scenario, browser that does not start, incomplete or intermittent trials. |

An intermittent series (some trials failing) is reported as an error, not a pass.
Add `--with-control` to also run each faulted scenario without its fault.

```yaml
# .github/workflows/regressions.yml
name: Regressions
on: [pull_request]
permissions:
  contents: read
jobs:
  replay:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - run: python -m pip install chaosfolk
      - run: python -m playwright install --with-deps chromium
      - run: npm ci && (npm start &) && npx wait-on http://localhost:3000
      - run: chaosfolk regression run qa/scenarios/*.json --output qa-results
      - uses: actions/upload-artifact@v4
        if: always()
        with:
          name: chaosfolk-regressions
          path: qa-results
```

Adapt the app start line to your project. Results can contain screenshots of the
test app: keep test data synthetic.

## Other browser engines

`replay`, `regression run` and `visual capture` accept `--channel` (or
`--browser`) `firefox` or `webkit`. Install them first with
`python -m playwright install firefox webkit`. An explicit engine never falls back
to Chromium: if it cannot start, the result is an error (exit code 2). WebKit is
not Safari on a real device.

## Visual comparison

Install the optional extra: `python -m pip install "chaosfolk[visual]"`.

```bash
chaosfolk visual capture http://localhost:3000/orders --output qa/visual/new/orders.png --mask ".clock"
chaosfolk visual compare qa/visual/baseline/orders.png qa/visual/new/orders.png --output qa/visual/diff-orders
chaosfolk visual approve --candidate qa/visual/new/orders.png --baseline qa/visual/baseline/orders.png --reviewed
```

Captures disable animations, hide the caret and mask password, card and one-time
code fields, plus each `--mask` selector. `compare` writes `before.png`,
`after.png`, `diff.png`, `visual.json` and an `index.html` to review them; it exits
with 1 when more than `--max-diff-ratio` of the pixels changed (default 0.1%). A
difference is something to look at, not a bug verdict. A baseline is only
replaced by `approve`, which requires `--reviewed`.
