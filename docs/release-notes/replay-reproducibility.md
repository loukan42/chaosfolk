# Replay reproducibility (0.8.0 alpha)

Replay a finding against the same verified dataset, retain its reproduction
metadata, and compare it with a reference journey supplied by your team.

- `--environment qa/environment.json` runs bounded preparation and verification
  commands before every trial and retry. Preparation forces sequential trials;
  failed resets and fixture mismatches are invalid executions.
- Every replay links a unique reproduction manifest containing scenario and
  profile provenance, application and browser metadata, browser-state hashes and
  the fault schedule. Trial results retain actual injection events. Unknown
  metadata is explicit; private browser-state contents stay outside manifests.
- `--baseline reference.json` runs the observed and reference journeys, each
  with and without faults. Both need explicit expectations and the same fault
  conditions with anchors appropriate to their own actions. The JSON summary
  and session report show the four series without assigning a cause or severity.
- CLI and English/French reports show the failure rate together with valid,
  invalid and requested counts. Incomplete evidence never acquires a reproduced
  badge just because a percentage is displayed.

```bash
chaosfolk replay observed.json --baseline reference.json --times 5 --environment qa/environment.json --output .horde/run/reproductions
```

This example runs twenty trials before any divergence retries. Commands and
replays run without a model. Clean-data verification relies on the project's
verification command; other writers need separate isolation or coordination.
Keep the tested build, fixture scripts, backend snapshot and private browser
state with the original scenario. Manifests identify them but do not bundle them.

Existing scenarios continue to work without configuration. Those trials record
browser isolation only, and older profile provenance remains unknown. Fault
replays use action anchors and do not guarantee identical wall-clock timing.

Tracking: [issue #13](https://github.com/loukan42/chaosfolk/issues/13).
Usage and formats: [replay guide](../replay.md).
