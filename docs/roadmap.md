# Roadmap

These are planned improvements, not existing capabilities.

- Add English output for remaining engine diagnostics and a versioned trace schema.
- Add an explicit target-origin policy enforced by browser requests and navigation.
- Add opt-in adapters for additional agent hosts, with recorded compatibility checks.
- Grow the benchmark with cases that need exploration to be found, and publish
  scores per run size.
- Export multi-session scenarios and more faults as portable tests.
- Expand the fault catalog with fixtures that distinguish injected errors from app defects.

There are no promised release dates. A useful contribution includes a fixture and
an observable acceptance criterion. Security scanning and load testing would need
separate execution models; adding more simulated users does not provide either.
