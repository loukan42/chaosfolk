# Security policy

Chaosfolk drives a real browser against the application you tell it to test and
can start a local development command. It is a testing tool for systems you own
or are authorized to test, with synthetic data. This page tells you how to report
a vulnerability, which versions receive fixes and what the engine does and does
not protect. The threat model, the secure development process and the
ISO/IEC 27001:2022 control mapping are in [docs/security.md](docs/security.md).

## Reporting a vulnerability

Use GitHub private vulnerability reporting: open the repository's **Security**
tab and choose **Report a vulnerability**. Reports stay private until a fix is
available. Do not open a public issue for a security problem and do not attach
session folders, screenshots or tokens from a real environment.

Include the Chaosfolk version (`chaosfolk --version`), the operating system, a
synthetic reproduction and the impact you observed. Reports written in English
or French are both fine.

| Step | Target |
|---|---|
| Acknowledgement | 3 business days |
| Triage and severity (CVSS 3.1) | 7 business days |
| Fix or mitigation for High and Critical | 30 days |
| Fix for Medium and Low | next minor release |
| Public advisory | with the fixing release, credited if you wish |

Security fixes ship as a patch release of the latest minor version, with a
GitHub Security Advisory and an entry under `Security` in
[CHANGELOG.md](CHANGELOG.md). Good-faith research that respects this policy will
not be the subject of legal action.

## Supported versions

Chaosfolk is alpha software. Only the latest minor release receives security
fixes; upgrade before reporting if you run an older one.

| Version | Supported |
|---|---|
| 0.8.x | Yes |
| < 0.8 | No |

## Threat model in short

**Trusted.** The operator who starts the engine, the coding agent that holds the
leader token, the local user account, and the files in the session folder. Anyone
with the leader token can run `inspect` (arbitrary JavaScript in the test
browser), start or stop the application under test and read every recorded
screen. Leader and user tokens separate roles inside the protocol; they do not
sandbox processes that share your operating-system account.

**Untrusted.** The application under test and every page it loads, including
text that simulated users read and repeat, download names, console messages and
redirects. The skill instructs agents to treat page content as data, not
instructions. Evidence derived from pages is escaped in reports and redacted in
shared exports, but a session folder must still be treated as confidential.

**Not a sandbox.** The engine allows HTTP(S) navigation and does not enforce a
network-origin allowlist; a malicious application can navigate the test browser
to external sites. Use network isolation when target confinement is required.
The `probe` command accepts loopback URLs only and refuses other origins,
non-GET/HEAD requests, service workers and WebSockets, but GET handlers can still
change application state. App startup commands run with your permissions.

## What the engine does to protect you

- Listens on `127.0.0.1` only, with no option to bind other addresses. Tokens are
  256-bit random values compared in constant time; the dashboard uses a bearer
  header, checks `Host` and `Origin`, sends a strict Content-Security-Policy and
  never logs tokens.
- Keeps session folders and the state directory owner-only (POSIX modes
  `0700/0600`, an explicit DACL on Windows), refuses symlinked or shared
  locations, and writes files atomically.
- Confines evidence, uploads, saved state, audit names and download names to the
  session folder. Persona ids and audit names accept a portable character set.
- Masks password, one-time-code, payment and `data-chaosfolk-private` fields in
  screenshots and screen text, including "show password" fields. Typed secrets
  never reach a report; the sanitized export (`chaosfolk privacy`) also redacts
  bearer and basic credentials, JWTs, cookie and authorization header text,
  URL credentials and credential parameters.
- Renders reports with text nodes only, under a Content-Security-Policy that
  allows no network access, and loads only relative screenshot paths.
- Runs hooks, runners and git without a shell, with timeouts and output limits,
  without the engine's own credentials in their environment, and with
  repository-configured commands (`core.fsmonitor`, hooks, external diff)
  disabled.

## Secure development

Every change goes through a pull request with required status checks: tests on
Linux and Windows, ruff, bandit, pip-audit on hash-locked requirements, CodeQL,
gitleaks, zizmor, dependency review and OpenSSF Scorecard. GitHub Actions are
pinned to commit SHAs and run with read-only tokens. Dependabot keeps the
actions current and opens Python security updates; the lock file is refreshed
with uv at each release. Installers pin the release version and verify an
archive checksum when you provide one. Details, roles and the control mapping:
[docs/security.md](docs/security.md).
