# How the score is calculated

The score summarizes the recorded session on a 100-point scale. It is a heuristic,
not a probability that the app is correct or a measure of total test coverage.

The defects pillar contributes up to 50 points: `50 × exp(-penalty / 30)`.
Blocking, annoying and minor findings have weights 10, 4 and 1. Their evidence
factors are 1 for reproduced findings, 0.6 for intermittent findings, 0.4 for
observations, 0.3 for decisions or partial fixes, 0.15 for complete fixes and zero
for excluded findings. Before findings are reviewed, flags use a provisional
factor of 0.2.

Tested properties contribute up to 20 points, when present. Passing properties
receive full credit and fixed properties receive 80%. Fault resilience contributes
up to 15 points when users actually encounter recorded faults. It checks whether
users avoid blocking flags or abandonment and resume activity after recovery.
Failed fault injections do not establish resilience.

The journey pillar contributes up to 15 points: ten times the fraction of played
users ending with `done`, plus `5 × exp(-console_penalty / 4)`. Distinct uninduced
JavaScript errors, crashes and HTTP 5xx groups count twice; console groups count
once. Duplicate messages, development-server noise and fault-induced errors do
not multiply this penalty. Scout events are excluded.

The available pillars are normalized to 100. The resulting score is capped at 59
for an unresolved reproduced blocker, 74 for an open or branch-fixed blocker,
and 89 for an unresolved reproduced annoying finding. Levels begin at 0 (fragile),
40 (unstable), 60 (fair), 75 (solid) and 90 (tested).

A proof series needs at least three valid trials, all requested trials completed,
and the correct treatment/control mode. A fault-related finding needs a passing
control. A complete fix additionally needs a passing treatment after the fix and
a failing treatment after removal. Declaring a finding fixed cannot supply missing
evidence. Empty reports show no score and remain provisional.

The optional after-fix score is a labeled model projection. It changes scoring
factors and linked property credit without creating or modifying replay evidence.
Recorded events and the actual current score remain unchanged.
