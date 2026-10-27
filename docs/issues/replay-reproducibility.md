# Make replay evidence repeatable across clean trials and reference journeys

QA teams need to distinguish a repeatable application defect from an expected fault response, a journey-specific failure, or contaminated test data.

## Acceptance criteria

- Allow a bounded preparation command and a separate verification command before every trial, including divergence retries. Run such trials sequentially. A failed reset, timeout or mismatched fixture identity makes the trial invalid, never a product failure.
- Record whether only the browser was isolated or backend data was reset and verified. Existing scenarios keep working without reset configuration.
- Save a reproduction manifest with the scenario snapshot and fingerprint, seed and generated profiles when available, profile/catalog fingerprints, application build or Git revision and dirty state, engine/browser versions, initial browser-state fingerprints and recorded fault schedule. Missing metadata is explicit; browser-state credentials and hook output stay out of the manifest.
- Offer an optional 2x2 replay: observed journey and team-supplied reference journey, each with and without faults. Keep each journey's own explicit assertions and action-anchored fault schedule. Require assertions and a fault schedule for both journeys; do not guess a reference or transplant action numbers.
- Save all four series and a linked summary. Incomplete or intermittent series remain distinguishable; matrix outcomes describe observed differences without deciding which product behavior is correct.
- Display failures / valid trials, percentage, invalid trials and requested trials in CLI, JSON and English/French reports, including small and incomplete series. Keep severity separate and preserve the existing reproduced badge requirements.
- Cover backend contamination, preparation failures, repeated clean trials, matrix differences, missing metadata and existing replay compatibility with tests.
- Update the replay guide, changelog and release notes after validation.

## Existing behavior

`replay --with-control --times N` already repeats the recorded journey with and without faults. The report requires at least three valid failures and an equally complete passing control for a fault-related reproduced badge. This issue extends that workflow.

## Validation

Implemented in [PR #14](https://github.com/loukan42/chaosfolk/pull/14). Full suite: 314 passed, 2 skipped. Ruff and wheel/source builds pass. The matrix report was checked at mobile width. Changelog entries and release notes are prepared for 0.8.0 alpha.
