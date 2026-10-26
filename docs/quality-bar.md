# Release quality bar

The comparison references selected for this release are
[Superpowers](https://github.com/obra/superpowers) for agent instructions and
[agent-browser](https://github.com/vercel-labs/agent-browser) for installation and
first-run clarity. The goal is a small, usable public tool with verifiable claims.
A star count is an adoption ambition, not a release acceptance test.

Acceptance checks:

- A fresh installation can run the local demo without a model account.
- The documented agent workflow has no missing local references and distinguishes
  engine installation, skill installation and host-specific shell behavior.
- The demo uses real browser evidence and cannot pass when its expected results
  are missing or inverted.
- Browser command failures, invalid trials and assertion failures have distinct
  outcomes. Incomplete proof cannot receive a reproduced badge.
- A package build includes the browser script, catalog, demo and report assets.
- Unit and browser integration tests cover actual failures, not wording snapshots.
- A separate critic reviews the delivered files and reports remaining adoption
  blockers. Named-source comparisons are not presented as blind tests.
- Public copy distinguishes measured results, implemented capabilities and plans.

The first independent review found missing workflow guides, invalid PowerShell
commands, silent agent-file replacement, incomplete-proof badges and empty
assertion gates. These findings became documentation changes and regression checks.
The review must be repeated against the completed repository before claiming
that those blockers are resolved.
