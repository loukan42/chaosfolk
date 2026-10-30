# Contributing

Start with a reproducible failure, a missing browser behavior or a documented
workflow that does not work. Include the engine version, operating system, a
small synthetic fixture and the command that demonstrates the problem.

For local development, create a virtual environment, install `.[dev]`, then run
`python -m playwright install chromium`. Run `python -m pytest` and
`python -m ruff check .` before submitting a change. `python -m build` verifies
the distributable package; runtime templates must be included in the wheel.

Ruff includes all Pyflakes checks. CI also audits installed dependencies and
optional integrations with `pip-audit`. Use a current pip when creating a local
environment; the audit found vulnerabilities in an older local pip during the
October 2026 review.

## Security practices

Read [docs/security.md](docs/security.md) before changing anything that touches
a trust boundary: the engine protocol, the dashboard, privacy and private state,
installers, workflows or dependencies. In short:

- Install the hooks once with `pre-commit install`; they run ruff, bandit,
  gitleaks and basic file checks before each commit.
- Install development requirements from the lock file:
  `python -m pip install --require-hashes -r requirements-dev.txt` then
  `python -m pip install --no-deps --no-build-isolation -e .`. Refresh the lock
  after changing `pyproject.toml` with
  `uv pip compile --universal --generate-hashes --python-version 3.12 --extra dev --extra visual --extra pdf --extra chaos pyproject.toml requirements-build.in -o requirements-dev.txt`
  and review the diff; Dependabot proposes routine updates.
- Pin new GitHub Actions to a commit SHA with the version in a comment, keep
  `permissions` minimal and `persist-credentials: false`.
- Treat everything read from the application under test as untrusted. Escape it
  in reports (`textContent` only), confine any path to the session folder, and
  add a regression test in `tests/test_hardening.py` or next to the module.
- Never commit tokens, session folders, screenshots of real applications or
  customer data; use the synthetic fixtures under `tests/`.
- A security fix gets a `Security` entry in the changelog and, when it fixes a
  vulnerability, a GitHub Security Advisory.

For journal or campaign performance changes, run
`python scripts/benchmark_journal.py --events 20000 --repeat 3` and
`python scripts/benchmark_resources.py`. Both use synthetic data and verify
equivalent outputs before reporting timings or peak Python allocations. These
measurements do not represent Chromium memory, energy use or model token costs.

For large-report changes, run `python scripts/benchmark_reporting.py` and
`python scripts/benchmark_playback.py`. The first compares report generation in
separate processes; the second isolates playback aggregation from DOM rendering.
`python scripts/benchmark_usage.py` compares exact memory and disk deduplication.
For browser lifecycle changes, run
`python scripts/benchmark_browser_resources.py --users 4 --repeat 3` alone,
without other browser tests. It measures descendant Chromium working sets and
CPU on a synthetic polling page, including an active user's continued operation.
Shared memory can be counted in more than one process. None of these benchmarks
measures model token costs or energy consumption.

`python scripts/benchmark_browser_reports.py --events 12000 --text-bytes 2048`
compares inline and progressive reports in fresh Chromium processes, including
heap after every detail chunk has been visited. Run it without other browser
workloads. `python scripts/benchmark_live_evidence.py` measures real engine
callbacks and journal writes in isolated Python processes.
`python scripts/benchmark_campaigns.py` verifies campaign results and published
files; `python scripts/benchmark_scoring.py` compares the same fault judgments
with repeated scans, memory indexes and disk indexes. Report memory, elapsed
time and disk costs separately rather than treating them as interchangeable.

Keep model decisions in the skill and deterministic behavior in the engine.
Browser tests should use loopback servers, never real accounts or production
systems. New faults need a passing control and a reproducible treatment. Invalid
trials must stay distinct from failures. Changes to serialized keys must preserve
existing traces or include an explicit migration.

Do not commit `.horde/`, cookies, tokens, application screenshots or customer data.
Use the synthetic demo for public report examples. Explain the observable change
and tests in your pull request. Bug fixes benefit from a test that fails before
the fix and passes after it.

Internal function names and stored trace keys retain some French terminology.
New public APIs and documentation use English. Translate interfaces incrementally
with compatibility tests rather than renaming arbitrary strings in saved evidence.

Add user-visible changes under `Unreleased` in [CHANGELOG.md](CHANGELOG.md), in
the matching `Added`, `Changed`, `Fixed` or `Removed` group.

## Releasing

For every release, write matching English and French notes in
`docs/release-notes/X.Y.Z.en.md` and `docs/release-notes/X.Y.Z.fr.md`.
Both versions must cover the same changes and limitations. Link both from the
README and changelog, and include both languages in the GitHub release notes.
User-facing notes for unreleased changes must also have an English/French pair.

1. Move the `Unreleased` entries to a new dated version section in
   `CHANGELOG.md` and update the comparison links at the bottom.
2. Set the same version in `pyproject.toml`, `src/chaosfolk/__init__.py`,
   `install.sh` and `install.ps1` (`tests/test_hardening.py` checks they match).
3. Run the tests, ruff, bandit and `python -m build`, then commit `Release X.Y.Z`.
4. Tag that commit `vX.Y.Z` and push the branch and the tag.
5. Create the GitHub release from the tag, with the version's changelog section
   as notes and the wheel and source archive from `dist/` attached. Mark it as a
   pre-release while Chaosfolk is alpha.
6. Compute `sha256sum` of the tag archive
   (`https://github.com/loukan42/chaosfolk/archive/refs/tags/vX.Y.Z.zip`) and of
   the attached files; publish them in the release notes and update the
   `CHAOSFOLK_SHA256` value in the README install commands.
