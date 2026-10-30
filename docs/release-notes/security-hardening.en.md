# Security hardening for use inside an organization

An October 2026 security review of the engine, the dashboard, the reports, the
privacy export and the installers found no critical issue, and a series of
medium and low weaknesses that this release fixes. The repository now follows a
documented secure development process aligned with ISO/IEC 27001:2022, so a
company can adopt Chaosfolk with evidence rather than trust.

## What changes for you

- **Evidence stays in the session folder.** Audit names, viewports, download
  names and campaign evidence paths are validated before any file is written or
  read; a mistaken or injected `--name ../x` is refused with a clear message.
- **Secrets stay out of reports.** Text typed into password, one-time-code and
  "show password" fields is masked in screenshots, in the screen text agents
  read and in every report; it remains in the private journal so a replay still
  works. The sanitized export (`chaosfolk privacy`) also redacts JWTs, HTTP Basic
  credentials, cookie and authorization header text and form-encoded
  credentials.
- **Less exposure of the engine's own credentials.** Chaos hooks and k6 or
  Appium runners no longer receive the leader token; tokens are compared in
  constant time; the dashboard answers errors without local paths and without a
  Python version banner; the state directory is owner-only from its creation.
- **Safer local integrations.** Git runs in your repositories with
  `core.fsmonitor`, hooks and external diff drivers disabled; the reachability
  check no longer follows redirects; reproducibility hooks run in their own
  process session; audit screenshots apply the same privacy masks as the others.
- **Reports carry a Content-Security-Policy** that forbids any network access,
  as a second barrier behind text-only rendering.
- **Pinned, verifiable installers.** `install.sh` and `install.ps1` install a
  release version by default, verify the archive checksum when
  `CHAOSFOLK_SHA256` is set, can refuse to download uv (`CHAOSFOLK_REQUIRE_UV=1`)
  and accept an internal mirror (`CHAOSFOLK_SOURCE`). The checksum of the
  0.8.0 archive is in the README.
- **A documented process.** [SECURITY.md](../../SECURITY.md) gives the reporting
  channel, response targets and supported versions. [docs/security.md](../security.md)
  holds the threat model, the engine controls, the secure development lifecycle,
  the ISO/IEC 27001:2022 Annex A mapping, a hardening checklist for managed
  environments and the accepted-risk register.

## For contributors

CI installs hash-locked requirements, pins every GitHub Action to a commit SHA
and adds CodeQL, bandit, pip-audit with a CycloneDX SBOM, gitleaks, zizmor,
dependency review and OpenSSF Scorecard. Dependabot, CODEOWNERS and pre-commit
hooks are configured. `chaosfolk install-browser` accepts only `--with-deps`,
`--force` and `--dry-run`.

## Limitations

Chaosfolk remains a testing tool, not a sandbox: the exploration mode allows
HTTP(S) navigation without an origin allowlist, the leader token can run
arbitrary JavaScript in the test browser, and the application command runs with
your permissions. The accepted-risk register in the security guide lists these
points with the compensating measures.

Release notes are provided in English and French for every release, with both
versions linked from the README and changelog.

[Version française](security-hardening.fr.md)
