# Choose the depth and tests of a full-product audit

Tracking: [issue #19](https://github.com/loukan42/chaosfolk/issues/19).

The existing checklist describes everything Chaosfolk can test, but a generated
group of users receives only a sample. A selected test can be left out when the
batch runs out of room, and assigning it does not establish that it ran. Users
also need a way to choose the scope before spending time and AI usage on a scan.

The default workflow should audit the whole product at a chosen depth. A focused
check of a feature or fix remains available when that is what the user requests.

## Expected behavior

- Offer Quick, Standard and Deep scans. Assign a priority to every test and include
  more of them as depth increases. Deep selects every test definition in the catalog.
- Adapt checks to discovered features and available accounts/tools. Keep unknown
  scope and missing access visible. Record the reason for a test that does not apply.
- Preselect the tests for the chosen depth and let users uncheck individual tests.
  Preserve their exclusions across depth changes and page reloads.
- Keep unfinished tests across batches. Assign work to simulated users or the
  relevant test tools and require a recorded outcome for completed checks.
- Show progress and time in a live local dashboard. Apply time/action limits and
  stop new work when the user requests it. Show AI usage only from actual measurements.
- Keep excluded, blocked and unfinished tests separate in the final report. An
  exhausted budget leaves a partial audit.

## Acceptance checks

- Deep includes all 69 QA checks and the other test scenarios; none disappear
  because the first group of users is too small.
- A test unchecked in the dashboard is absent from the next user sheets and its
  next browser action is rejected if it was already assigned.
- Concurrent workers cannot claim the same task. Finishing without a result
  returns the task to the work list. Recorded passes/failures require evidence.
- A real browser run verifies selection, reload, results and stopping. A running
  coordinator tool is interrupted through the same stop control.
- Missing token measurements remain unavailable. A configured token limit blocks
  work when complete, recent measurements are absent; active model requests remain
  under the coding tool's control.
- Progress polling makes no model calls. CLI summaries and paged task lists bound
  the information sent back to the coordinator.

The README should show the real settings screen. Release notes should explain the
user-facing changes and consumption limits in plain language.
