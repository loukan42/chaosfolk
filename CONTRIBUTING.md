# Contributing

Start with a reproducible failure, a missing browser behavior or a documented
workflow that does not work. Include the engine version, operating system, a
small synthetic fixture and the command that demonstrates the problem.

For local development, create a virtual environment, install `.[dev]`, then run
`python -m playwright install chromium`. Run `python -m pytest` and
`python -m ruff check .` before submitting a change. `python -m build` verifies
the distributable package; runtime templates must be included in the wheel.

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
