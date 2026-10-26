# Roadmap

The first public version concentrates on exploration, fault reproduction and a
local evidence report. These are planned improvements, not existing capabilities.

- Add English output for remaining engine diagnostics and a versioned trace schema.
- Add an explicit target-origin policy enforced by browser requests and navigation.
- Add opt-in adapters for additional agent hosts, with recorded compatibility checks.
- Export portable regression tests from proven scenarios.
- Measure exploration cost and coverage on a public collection of synthetic apps.
- Expand the fault catalog with fixtures that distinguish injected errors from app defects.

There are no promised release dates. A useful contribution includes a fixture and
an observable acceptance criterion. Security scanning and load testing would need
separate execution models; adding more simulated users does not provide either.
