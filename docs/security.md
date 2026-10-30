# Security guide

This guide is written for the people who decide whether Chaosfolk may run inside
their organization and for the people who maintain it. It describes what the
tool protects, how it is developed and how its controls map to ISO/IEC
27001:2022 Annex A. The short version, the reporting channel and the supported
versions are in [SECURITY.md](../SECURITY.md).

Last review: 30 October 2026 ([issue 24](https://github.com/loukan42/chaosfolk/issues/24)).
Owner: the maintainer listed in [CODEOWNERS](../.github/CODEOWNERS).

## 1. Scope and roles

Chaosfolk is a local testing tool. A coding agent (the leader) starts the engine,
which drives a Chromium browser with Playwright against a web application and
records evidence in a session folder. Simulated users (other agent processes)
send commands to the engine over a loopback socket. Optional parts: a live audit
dashboard served on loopback, a read-only MCP server exposing campaign memory,
a `probe` smoke-load command, integrations with Mailpit, k6 and Appium.

| Role | Who | Responsibility |
|---|---|---|
| Maintainer | `@loukan42` | Reviews and merges every change, triages vulnerability reports, publishes releases and advisories, keeps this guide current. |
| Contributor | Anyone opening a pull request | Follows [CONTRIBUTING.md](../CONTRIBUTING.md): tests, pre-commit hooks, no secrets, regression test for a security change. |
| Operator | The person or team running Chaosfolk | Chooses targets and data, runs the tool in the environment described in section 7, reviews evidence before sharing it. |
| Security contact | Private vulnerability reporting on GitHub | See [SECURITY.md](../SECURITY.md). |

## 2. Assets and data classification

| Asset | Where | Classification | Protection |
|---|---|---|---|
| Session and leader tokens | `<session>/serveur.json`, `~/.chaosfolk/active.json`, process memory, `CHAOSFOLK_LEADER_TOKEN` | Secret | 256-bit random, owner-only files, constant-time comparison, never logged, stripped from hook and runner environments. |
| Session folder (journal, screenshots, downloads, saved browser state, audit evidence) | `--folder`, default under the state directory | Confidential | Owner-only directory and files, refused on shared or symlinked locations, every write confined to the folder. |
| Reports (`rapport.html`, `report-en.html`, `rapport-fr.html`, `assets/`) | Session folder | Internal | Text-only rendering, Content-Security-Policy with no network access, typed secrets masked, relative image paths only. |
| Sanitized export (`chaosfolk privacy`) | Operator-chosen empty folder | Shareable after review | Screen text, typed values and live evidence dropped, credentials redacted, `PRIVACY-REVIEW.txt` lists what to check. |
| Campaign memory (`findings.json`, `campaigns.json`, scenarios) | `<state>/projects/<name>` | Internal | Validated project names, size caps, atomic transactions, MCP exposes names and metadata only. |
| Source code, workflows, lock file | This repository | Public | Reviewed pull requests, required checks, pinned dependencies, signed-off release process. |

Chaosfolk never sends data to a remote service of its own. The only outbound
traffic is the browser navigating the application under test, the installers
downloading the release archive, uv and Chromium, and the coding agent's own
model provider, which is outside this tool.

## 3. Threat model

### Trust boundaries

```
 operator shell ──► coding agent (leader token) ──► engine (127.0.0.1, line-JSON protocol)
                        │                              │
                        └─ simulated users (user token) ┤
                                                        ├─► Chromium (Playwright) ──► application under test (untrusted)
                                                        ├─► session folder (confidential)
                                                        └─► app command, hooks, k6/Appium, git (operator-configured)
 browser ──► audit dashboard (127.0.0.1, bearer token, Host and Origin checks)
 agent host ──► MCP server (stdio, read-only tools)
```

### Attackers considered

| Attacker | Capability | Goal | Main controls |
|---|---|---|---|
| The application under test | Controls every page, response header, redirect, download name, console message and text the simulated users read | Make the engine write outside the session folder, run code, exfiltrate evidence, inject instructions into agents | Path confinement, base-name downloads, HTTP(S)-only navigation, text-only reports with CSP, redaction, skill instructions treating page text as data, no redirect following in server-side checks |
| Another local process without a token | Can reach loopback ports | Drive the engine or the dashboard | Token on every command, dashboard bearer header, Host allowlist against DNS rebinding, Origin check on state changes |
| A web page open in the operator's browser | Cross-site requests to loopback | Reach the dashboard | Host and Origin checks, no CORS headers, strict CSP |
| Another operating-system user on the same host | File system access | Read tokens or evidence | Owner-only directories and files, refusal of shared locations |
| A compromised dependency or action | Code execution in CI or on install | Tamper with releases | Hash-locked requirements, SHA-pinned actions, read-only tokens, Dependabot, pip-audit, Scorecard, release checksums |
| A model-driven agent making a mistake | Holds the leader token | Damage evidence or read files by error | Validated names and paths even for leader commands, allowlisted CLI flags, no shell in subprocess calls |

### Out of scope

- Isolating processes that share the operator's account. Leader and user tokens
  separate roles inside the protocol; an agent running as the same user can read
  `serveur.json` and obtain the leader token (accepted risk AR-1).
- Confining the test browser's network. Exploration mode allows any HTTP(S)
  navigation; use network isolation when the target must be confined (AR-4).
- Hostile applications beyond a test environment. The engine is not a sandbox
  for arbitrary malicious websites.
- The coding agent's model provider and prompt-injection resistance of the
  model itself. The skill and persona templates mitigate; they cannot guarantee.

## 4. Engine controls

| Area | Control | Where |
|---|---|---|
| Network exposure | Engine and dashboard bind `127.0.0.1` with no option to change it; dashboard checks `Host` and `Origin`, emits CSP, `nosniff`, `Referrer-Policy: no-referrer`, `Cache-Control: no-store`, a neutral `Server` header, no access log. | `engine.py`, `audit_dashboard.py` |
| Authentication | `secrets.token_hex(32)` and `secrets.token_urlsafe(32)` tokens; `hmac.compare_digest`; non-string tokens rejected; reserved commands require the leader token; dashboard token in the `Authorization` header only. | `engine.autorise`, `engine.jeton_egal`, `audit_dashboard` |
| Private state | `0700/0600` on POSIX, explicit owner/SYSTEM/Administrators DACL on Windows, applied to files, temporary files and newly created state directories; symlinks, junctions, hard links and repository roots refused; atomic replace with retry on Windows sharing violations. | `private_state.py` |
| Path confinement | Persona ids, audit names and viewports validated; uploads, saved state, evidence, audit files, downloads and campaign proofs resolved and checked with `is_relative_to`. | `engine.validate_id`, `audit.validate_name`, `engine.nom_de_fichier_sur`, `campaigns.inside`, `audit_session.Session.evidence` |
| Input limits | 16 MiB line limit and 10 s read timeout on the protocol; 128 KiB JSON bodies, exact content type and field allowlists on the dashboard; 1 MiB frames and 4 MiB files on the MCP server; 8 MiB downloads in integrations; 20 Mpx images; 200-page PDFs with content size checked before decompression. | `engine.py`, `audit_dashboard.py`, `mcp_server.py`, `integrations.py`, `visual.py` |
| Subprocesses | Argument lists only (the operator's `--app-command` is the documented exception), timeouts, bounded output, `CREATE_NO_WINDOW`, own process session or Windows job object, identity-checked termination, `-I` for the helper interpreter, leader token removed from hook and runner environments, git run with `core.fsmonitor`, hooks and external diff disabled and `--end-of-options`. | `chaos.py`, `chaos_jobs.py`, `owned_process.py`, `reproducibility.py`, `planning.py`, `integrations.py` |
| Outbound requests | urllib clients disable proxies and refuse redirects; `probe` and the accessibility runner accept loopback origins only, GET/HEAD only, no redirects, no service workers, no WebSockets, no downloads. | `engine.url_repond`, `integrations.py`, `probe.py` |
| Privacy | Screenshot masks for password, current/new password, one-time code, payment and `data-chaosfolk-private` fields plus `CHAOSFOLK_MASK_SELECTORS`; screen text masks the same fields; reports mask text typed into sensitive fields; the export redacts bearer and basic credentials, JWTs, cookie and authorization headers, URL credentials, credential parameters, emails and configured literals. | `privacy.py`, `screen.js`, `reporting.py` |
| Report rendering | Data embedded as a `JSON.parse` string with `<`, U+2028 and U+2029 escaped; DOM built with `textContent`; images only from validated relative paths; CSP `default-src 'none'`; lazy chunks loaded only from `assets/journal/<sha256>.js`. | `reporting.py`, `templates/report.html`, `templates/evidence.js` |
| Installation | Skill files copied from a constant list with staging and rollback; another skill or a link to another skill is never replaced; `install-browser` accepts an allowlist of flags; installers pin the release, verify `CHAOSFOLK_SHA256`, pin the uv version and can refuse to download uv. | `install.py`, `cli.py`, `install.sh`, `install.ps1` |

Regression tests for these controls live in `tests/test_hardening.py`,
`tests/test_security_audit.py`, `tests/test_followup_security.py`,
`tests/test_privacy_publication.py`, `tests/test_readonly_redirects.py`,
`tests/test_audit_session.py` and `tests/test_core.py`.

## 5. Secure development lifecycle

1. **Plan.** Work starts from an issue that states the user-visible problem and
   the acceptance criteria. Security-relevant work names the threat it addresses.
2. **Develop.** Contributors install the hash-locked requirements and the
   pre-commit hooks (ruff, bandit, gitleaks, large-file and private-key checks).
   Everything read from the application under test is treated as untrusted; new
   paths are confined to the session folder; new subprocesses use argument lists.
3. **Review.** Every change reaches `main` through a pull request. CODEOWNERS
   requests the maintainer on every file and explicitly on trust boundaries. The
   pull request template asks how the change was verified and whether trace
   formats or agent permissions changed.
4. **Verify.** Required checks on Linux and Windows with Python 3.12 and 3.14:
   tests, ruff, build and installation of the wheel in a clean environment, and
   the installer's checksum behaviour. The Security workflow runs pip-audit on the
   locked environment and produces a CycloneDX SBOM, bandit (fails on medium and
   high), gitleaks over the whole history, and zizmor on the workflows. CodeQL
   analyzes Python and JavaScript with the extended security queries. Dependency
   review blocks pull requests adding vulnerable or copyleft dependencies.
   OpenSSF Scorecard measures the repository weekly.
5. **Release.** Versions are tagged, the changelog carries a `Security` group,
   release notes exist in English and French, installers are updated to the new
   version, and the archive checksum is published with the release. Releases are
   built from the locked environment.
6. **Operate.** Dependabot opens grouped weekly updates for GitHub Actions and
   immediate security updates for Python packages; the Python lock itself is
   refreshed with uv (see [CONTRIBUTING.md](../CONTRIBUTING.md)) at each release
   and whenever pip-audit, which also runs weekly, reports a vulnerability.
   Private vulnerability reporting is enabled; triage and response
   targets are in [SECURITY.md](../SECURITY.md). Fixes ship as a patch release
   with a GitHub Security Advisory.
7. **Learn.** Each review adds its findings to this guide and its regression
   tests to the suite; accepted risks are recorded in section 8 with an owner
   and compensating measures.

### Dependency and supply-chain policy

- Runtime dependencies are kept to Playwright and psutil, with Pillow, pypdf and
  tzdata as optional extras, all with upper bounds in `pyproject.toml`.
- `requirements-dev.txt` is a universal, hash-locked file generated from
  `pyproject.toml` and `requirements-build.in`; CI installs with
  `--require-hashes` and builds with `--no-isolation` so the build backend is
  also pinned.
- GitHub Actions are pinned to commit SHAs with the version as a comment; tokens
  are read-only by default and widened per job only for SARIF upload or OIDC.
- The installers download a release archive, not a branch, verify its SHA-256
  when given, pin the uv version and accept an internal mirror.
- Browser binaries are downloaded by Playwright from its CDN; their integrity is
  Playwright's responsibility (AR-8). Organizations can pre-install Chromium or
  point `PLAYWRIGHT_BROWSERS_PATH` to a vetted copy.

## 6. ISO/IEC 27001:2022 Annex A mapping

The mapping covers the controls an organization will look for when it assesses
a development tool. "Evidence" names the artifact an auditor can inspect.

| Control | Title | How Chaosfolk meets it | Evidence |
|---|---|---|---|
| A.5.8 | Information security in project management | Issues state security acceptance criteria; the review that produced this guide is tracked as issue 24. | GitHub issues, this guide |
| A.5.9 | Inventory of information and other associated assets | Section 2 classifies tokens, sessions, reports, exports, memory and code. | Section 2 |
| A.5.10 | Acceptable use of information and assets | Authorized targets and synthetic data only; the skill and README state the rule. | `SECURITY.md`, README Security section, `SKILL.md` |
| A.5.12, A.5.13 | Classification and labelling of information | Confidential session folder, shareable export, `PRIVACY-REVIEW.txt` in every export. | Section 2, `privacy.py` |
| A.5.14 | Information transfer | Only the sanitized export is meant to leave the machine; raw sessions stay local. | `chaosfolk privacy`, Section 7 |
| A.5.15, A.5.18 | Access control and access rights | Token-based roles (leader/user), owner-only files, CODEOWNERS on the repository. | `engine.autorise`, `private_state.py`, `CODEOWNERS` |
| A.5.19 to A.5.21 | Supplier relationships and ICT supply chain | Pinned, hash-locked dependencies, pinned actions, Dependabot, dependency review, SBOM, Scorecard. | Workflows, `requirements-dev.txt`, `dependabot.yml` |
| A.5.23 | Information security for use of cloud services | GitHub is the only service: least-privilege workflow tokens, private vulnerability reporting, secret scanning with push protection, Dependabot alerts. | Repository settings, workflows |
| A.5.24 to A.5.28 | Incident management planning, assessment, response, learning, evidence | Reporting channel, acknowledgement and fix targets, advisories, `Security` changelog group, accepted-risk register. | `SECURITY.md`, `CHANGELOG.md`, Section 8 |
| A.5.34 | Privacy and protection of PII | Masks, typed-secret masking, redaction, export review file; synthetic data required by the skill. | `privacy.py`, `reporting.py`, `SKILL.md` |
| A.5.36 | Compliance with policies and standards | Pre-commit hooks locally and the same tools in CI; CONTRIBUTING lists the rules. | `.pre-commit-config.yaml`, `CONTRIBUTING.md` |
| A.5.37 | Documented operating procedures | Installation, operation, release and hardening procedures. | README, `CONTRIBUTING.md`, Section 7 |
| A.6.8 | Information security event reporting | Private vulnerability reporting enabled; issue template warns against tokens and real artifacts. | Repository settings, `.github/ISSUE_TEMPLATE` |
| A.8.2 | Privileged access rights | Reserved commands require the leader token; the token is never written to logs or passed to hooks. | `engine.py`, `chaos.py` |
| A.8.3 | Information access restriction | Owner-only state; MCP server exposes metadata only; dashboard requires a bearer token. | `private_state.py`, `mcp_server.py`, `audit_dashboard.py` |
| A.8.4 | Access to source code | Public repository, protected `main` through rulesets and pull requests, CODEOWNERS. | Repository settings |
| A.8.5 | Secure authentication | Random tokens, constant-time comparison, header-only transport. | `engine.jeton_egal`, `audit_dashboard.py` |
| A.8.7 | Protection against malware | Pinned releases with checksums, pinned installers, no `curl | sh` of unpinned content, allowlisted CLI flags. | `install.sh`, `install.ps1`, `cli.py` |
| A.8.8 | Management of technical vulnerabilities | pip-audit on every change and weekly, Dependabot alerts and security updates, CodeQL, bandit, Scorecard. | Security, CodeQL and Scorecard workflows |
| A.8.9 | Configuration management | Declarative lock file, pinned actions, documented environment variables, `pyproject.toml` as the single source of versions. | `requirements-dev.txt`, workflows |
| A.8.10 | Information deletion | Session folders are self-contained and deletable; exports are written to an empty folder chosen by the operator; Section 7 asks for retention rules. | Section 7 |
| A.8.11 | Data masking | Screenshot and screen-text masks, report masking of typed secrets. | `privacy.MASKS`, `screen.js`, `reporting.py` |
| A.8.12 | Data leakage prevention | Export redaction, no outbound traffic from the engine, CSP in reports, no leader token in child environments. | `privacy.py`, `report.html`, `chaos.py` |
| A.8.15, A.8.16 | Logging and monitoring | Journal of every action with timestamps in the session folder; no tokens in logs; dashboard access log disabled by design. | `journal.jsonl`, `audit_dashboard.py` |
| A.8.19 | Installation of software on operational systems | Isolated tool installation with uv, pinned version, checksum, opt-out of PATH changes, `CHAOSFOLK_REQUIRE_UV`. | Installers, README Install |
| A.8.20, A.8.22 | Network security and segregation | Loopback-only listeners; `probe` loopback allowlist; guidance to run in an isolated network. | `engine.py`, `probe.py`, Section 7 |
| A.8.24 | Use of cryptography | `secrets` for tokens, SHA-256 for identifiers and provenance, `hmac.compare_digest`; SHA-1 only as a non-security fingerprint. | `engine.py`, `campaigns.py` |
| A.8.25 | Secure development life cycle | Section 5. | Section 5, workflows |
| A.8.26 | Application security requirements | Threat model and controls in Sections 3 and 4; security acceptance criteria in issues. | This guide |
| A.8.27 | Secure system architecture and engineering principles | Least privilege, defence in depth (validation plus CSP plus redaction), fail closed on validation errors. | Sections 3 and 4 |
| A.8.28 | Secure coding | Argument-list subprocesses, parameterised SQL, text-only DOM, input validation, ruff and bandit gates, review checklist in CONTRIBUTING. | `CONTRIBUTING.md`, `pyproject.toml` |
| A.8.29 | Security testing in development and acceptance | Regression tests for every finding, browser tests against synthetic fixtures, CodeQL and bandit in CI. | `tests/test_hardening.py` and related tests |
| A.8.30 | Outsourced development | Not applicable: no outsourced development. Contributions are reviewed as in A.8.28. | `CONTRIBUTING.md` |
| A.8.31 | Separation of development, test and production environments | The tool targets test environments only; the skill forbids production targets; CI uses synthetic loopback fixtures. | `SECURITY.md`, `SKILL.md`, tests |
| A.8.32 | Change management | Pull requests, required checks, changelog, release process with tags and notes in two languages. | `CONTRIBUTING.md`, `CHANGELOG.md` |
| A.8.33 | Test information | Synthetic personas, fixtures and demo application only; no customer data in the repository. | `tests/`, `src/chaosfolk/demo` |

## 7. Hardening checklist for managed environments

Before the first run inside an organization:

- [ ] **Authorization.** Confirm in writing which applications and environments
  may be tested. Never point Chaosfolk at production or at systems you do not
  own.
- [ ] **Data.** Use synthetic accounts and data. Set `CHAOSFOLK_MASK_SELECTORS`
  to a JSON list of selectors for any field your application shows that must
  never appear in a screenshot.
- [ ] **Isolation.** Run on a dedicated workstation, virtual machine or
  container with network access limited to the application under test and the
  model provider. The exploration mode does not restrict browser egress.
- [ ] **Installation.** Install a pinned release with its checksum (README
  Install), from an internal mirror if downloads are controlled
  (`CHAOSFOLK_SOURCE`). Pre-install uv or Python 3.12+ with your package manager
  and set `CHAOSFOLK_REQUIRE_UV=1`. Set `CHAOSFOLK_NO_MODIFY_PATH=1` when shell
  profiles are managed centrally. Pre-install Chromium or vet the Playwright
  browser cache if browser binaries must be controlled.
- [ ] **State location.** Keep `CHAOSFOLK_HOME` (or `--state-dir`) and session
  folders on an encrypted local disk, never on a shared drive. The engine refuses
  shared or symlinked locations but cannot check encryption.
- [ ] **Retention.** Decide how long session folders are kept and delete them
  when an investigation ends. Share the sanitized export
  (`chaosfolk privacy --include-reviewed-captures` only after reviewing
  screenshots), never the raw folder.
- [ ] **Agents.** Review the installed skill and persona definitions
  (`chaosfolk setup` prints their paths). The simulated users run with shell and
  file access to the session folder; grant the coding agent no more than that.
- [ ] **Updates.** Subscribe to repository releases and security advisories;
  upgrade to the latest minor version, which is the only supported one.
- [ ] **Local integrations.** Configure chaos hooks, k6, Appium and
  reproducibility commands from reviewed files only; they run with the
  operator's permissions, without the engine's tokens.

## 8. Accepted-risk register

| Id | Risk | Rationale | Compensating measures | Owner, review |
|---|---|---|---|---|
| AR-1 | Processes running as the operator can read `serveur.json` and obtain the leader token. | Local orchestration needs the token on disk for the leader to reconnect; OS-level isolation is the operator's domain. | Owner-only files; documented in SECURITY.md; run simulated users under a dedicated account or container when role separation matters. | Maintainer, each minor release |
| AR-2 | `--app-command` runs through a shell. | The operator writes the command exactly as in a terminal; no network input reaches it. | Only CLI source; `# nosec B602` with reason; documented. | Maintainer |
| AR-3 | `inspect` and `js` assertions execute arbitrary JavaScript in the test browser with the leader token. | Required to collect evidence and assert state. | Leader token only; review scenarios from other people before replaying; results truncated. | Maintainer |
| AR-4 | Exploration mode allows navigation to any HTTP(S) origin. | Simulated users must follow the application wherever it goes to find defects. | Network isolation recommended; `probe` and accessibility runs enforce a loopback allowlist. | Operator |
| AR-5 | Non-HTTP browser egress (DNS prefetch, preconnect, WebRTC) is not blocked for `probe` and accessibility runs. | Not verified as exploitable; Playwright routing covers HTTP, service workers and WebSockets. | Network isolation; candidate for Chromium host-resolver flags in a future release. | Maintainer, next review |
| AR-6 | MCP tools annotated read-only acquire a lock file and may publish a pending campaign transaction. | Recovery keeps project memory consistent for every reader. | Writes are confined to validated names and sizes; documented here. | Maintainer |
| AR-7 | Finding fingerprints use truncated SHA-1. | Non-cryptographic identity; changing it would break existing `findings.json` continuity. | `usedforsecurity=False`; SHA-256 everywhere else. | Maintainer |
| AR-8 | Chromium is downloaded by Playwright without an application-level checksum. | Playwright owns the browser distribution. | Pre-install or vet browsers in managed environments. | Operator |
| AR-9 | k6 and Appium executables are chosen by the operator; only shell wrappers are refused. | The adapters cannot vet arbitrary binaries. | Regular-file check, no shell wrappers, no engine tokens in their environment, bounded output. | Operator |

## 9. Review history

| Date | Scope | Outcome |
|---|---|---|
| 2026-10-30 | Engine protocol and dashboard, probe/MCP/subprocess/git surface, reports, privacy export, installers, CI and repository settings; bandit 1.9 and pip-audit 2.10. | No critical finding. Four medium and fifteen low findings fixed with regression tests; governance gaps closed (SHA-pinned CI, lock file, CodeQL, gitleaks, zizmor, dependency review, Scorecard, Dependabot, CODEOWNERS, pre-commit, this guide). Repository settings: Dependabot alerts and security updates, private vulnerability reporting and branch deletion on merge enabled. |
| 2026-10 | Dependency audit of the local environment during the engineering review. | Vulnerable local pip found and documented; CI audit introduced. |
