# Choose how thoroughly Chaosfolk checks your app

Included in Chaosfolk 0.8.0 alpha. [Lire en français](product-audit-scans.fr.md).

You can choose a scan depth, remove tests you do not need and follow the audit
from a local dashboard while your coding agent runs it.

## Pick a scan depth

Quick starts with the highest-priority checks. Standard adds more cases around
your users' journeys. Deep selects every test in the catalog. All three cover the
whole product, with tests adapted to the features Chaosfolk finds in your app.

For example, checks that need an upload field apply when the app has one. If a
check needs a test account you have not provided, it stays visible as blocked.

You can uncheck individual tests before or during a scan. Chaosfolk keeps those
choices when you change depth or reopen the dashboard. A test you remove receives
no new work; an action already in progress may finish.

![Changing the scan depth, removing a test and saving time and action limits.](../../assets/audit-scan.gif)

[View a still image](../../assets/audit-scan.png). The recording shows settings
before a scan starts.

## Set limits and follow progress

The dashboard shows elapsed time and the state of the tests. You can cap the scan's
duration or the number of browser actions, such as clicks and form entries.
Press Stop to block new work and interrupt the test tools monitored by Chaosfolk.

AI usage appears when your coding tool provides it. Tokens are the pieces of text
the AI processes; their count helps track consumption. If that information is
missing, the dashboard says it is unavailable. A token limit requires recent,
complete measurements before work can continue.

An AI request already running can still consume tokens after you press Stop.
Cancelling that request depends on the coding tool running the agents.

Stop stays available during saves and while reading the test list. A delayed start
cannot restart an audit you have just stopped. Unsaved limits survive failures and
reloads; edits to different limits in separate tabs preserve one another.

You can also limit how many user browsers stay open at once: six by default.
Chaosfolk releases finished users before starting the next batch. Browsers needed
for shared-user checks remain available until those checks finish.

If you stop and resume the audit, interrupted tools return to the queue and keep
their earlier observations. **Fermer le tableau de bord** closes the dashboard's
local server; use Stop to halt test work. Without client activity, that server
closes after fifteen minutes.

## See what was checked

The report keeps completed tests, observations awaiting review and unfinished
work separate. Tests you remove are listed too. If an agent finishes its batch
without reporting a result, the test remains on the list of work to do.

A Deep scan can stay partial if time runs out, a feature is inaccessible or a
required tool is missing. Completion means every selected, applicable test has a
recorded result for the product areas that were discovered.
The report has no numerical score until a check has a result, and partial audits
keep a visible provisional label. Concurrent discoveries preserve all saved routes.

Sanitized report copies retain depth, exclusions and progress. Private session
files have restricted access permissions. External test programs and their child
processes are cleaned up when a test succeeds, fails or reaches its time limit.
Shared copies also omit detailed replay diagnostics that can contain entered values.
Read-only probes and accessibility checks block redirects; supply the final
authorized URL to continue those checks.

The live dashboard refreshes without asking an AI model to redraw it. Agents
receive small batches of work and short progress summaries to limit repeated
context in their conversations.

For installation and commands, see the [product audit guide](../audit-runs.md).
