<div align="center">

<img src="logo.png" alt="Chaosfolk. AI users. Real browser evidence. Explore, break, replay." width="820">

**Simulated users break your web app in a real browser.<br>You get the bugs, the proof and a fix prompt for your coding agent.**

[![Tests](https://github.com/loukan42/chaosfolk/actions/workflows/tests.yml/badge.svg)](https://github.com/loukan42/chaosfolk/actions/workflows/tests.yml)
[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue)](https://www.python.org/)
[![MIT license](https://img.shields.io/badge/license-MIT-dcf78b)](LICENSE)

[Choose a scan](#choose-a-scan) · [What it checks](#what-it-checks) · [What you get](#what-you-get) · [Install](#install) · [Demo](#try-the-demo) · [Changelog](CHANGELOG.md)

</div>

Version [0.8.0 alpha](https://github.com/loukan42/chaosfolk/releases/tag/v0.8.0)
adds configurable product scans, live limits and fixes to audit controls and
shared reports. Read the [release notes in French](docs/release-notes/0.8.0.fr.md).

## Choose a scan

Ask your coding agent to audit your product with Chaosfolk. Choose a depth in the
local dashboard, then uncheck any tests you want to leave out. Every level covers
the product as a whole; the deeper levels include more checks.

| Scan | What it selects | Tests before application discovery |
| --- | --- | ---: |
| Quick (Rapide) | The highest-priority checks | 41, including 27 QA checks |
| Standard | Priority checks and more cases around each journey | 96, including 57 QA checks |
| Deep (Approfondi) | Every test in the catalog | 116, including all 69 QA checks |

Chaosfolk adapts the selection to the features it finds in your app. A test that
needs a missing account or tool stays marked as blocked. Your exclusions remain
saved when you change depth or reopen the dashboard.

![Choosing a scan depth, removing an email-validation test and setting a 15-minute limit in the real Chaosfolk dashboard.](assets/audit-scan.gif)

[View a still image](assets/audit-scan.png). This recording shows the dashboard
before a scan starts. It contains no test results or estimated AI usage.

During the scan, follow the tests and elapsed time, set limits and stop new work
from the same screen. AI usage appears when your coding tool supplies measurements;
otherwise it is shown as unavailable. An AI request already in progress may finish
and keep consuming usage after you press Stop.

You can also cap the number of open user browsers (six by default). Finished
independent users are released before the next batch; coordinated users remain
available until their shared checks finish. Resume returns interrupted tools to
the queue. Closing the dashboard shuts down its local server; use Stop when you
want to halt the audit itself.

The report records what ran, what you removed and what remains unfinished. Deep
counts as complete only when all selected, applicable tests have a recorded result.
If access or the budget prevents that, the audit stays partial.
Sanitized reports keep this coverage and your exclusions when shared.

Read the [setup and execution guide](docs/audit-runs.md) or the release
notes in [English](docs/release-notes/product-audit-scans.md) and
[French](docs/release-notes/product-audit-scans.fr.md).

The [latest release note in French](docs/release-notes/audit-reliability.fr.md)
explains the fixes to stopping scans, saving limits and sharing reports.

## Test checklist

The checklist includes test definitions, exploration methods, behavior profiles
and execution controls. Its 116 selectable tests include the 69 QA checks below;
the other 62 entries describe ways to run tests and collect evidence.

<details>
<summary><strong>Full test checklist: exploration, chaos experiments and 69 QA checks</strong></summary>

Chaosfolk combines open-ended agent exploration, randomized behavior profiles,
controlled fault injection and the 69 predefined QA checks. Agents choose their
next actions from the page they see, their goals and their assigned habits;
the catalog does not limit the journeys they can explore.

A check means the capability is available, not that every run executes it.
Some checks need test accounts, a mailbox, coordinated users, project assertions
or an explicitly configured integration. Country-dependent values cover 15 countries.

<table>
<thead><tr><th>What Chaosfolk can test</th><th>Supported</th></tr></thead>
<tbody>
<tr><th colspan="2" align="left">OPEN-ENDED EXPLORATION AND RANDOMIZED SCENARIOS</th></tr>
<tr><td>Agent-chosen actions and unexpected routes within supplied goals and authorized scope</td><td align="center">✓</td></tr>
<tr><td>Pure exploration without predefined catalog checks (<code>--checks none</code>)</td><td align="center">✓</td></tr>
<tr><td>Seeded selection and combinations of behavior profiles and shared habits</td><td align="center">✓</td></tr>
<tr><td>Varied computer confidence and patience in generated user sheets</td><td align="center">✓</td></tr>
<tr><td>Weighted draws of desktop, laptop, tablet and mobile contexts</td><td align="center">✓</td></tr>
<tr><td>Shuffled objective order so users approach the same goals differently</td><td align="center">✓</td></tr>
<tr><td>Randomized shares of applicable checks and samples of valid/invalid test values</td><td align="center">✓</td></tr>
<tr><td>Weighted fault draws, including the possibility of no injected fault</td><td align="center">✓</td></tr>
<tr><td>Randomized fault-start action, duration and parameters within catalog ranges</td><td align="center">✓</td></tr>
<tr><td>Combined behavior, device, objective order and fault conditions</td><td align="center">✓</td></tr>
<tr><td>Less-visited and unvisited known routes suggested from previous project campaigns</td><td align="center">✓</td></tr>
<tr><td>Unexpected outcomes when users repeat, interrupt, abandon or resume an action</td><td align="center">✓</td></tr>
<tr><td>Seed retained to reproduce the draw; recorded actions used to replay the actual journey</td><td align="center">✓</td></tr>
<tr><th colspan="2" align="left">ALL 16 SIMULATED BEHAVIOR PROFILES</th></tr>
<tr><td>First-time visitor: visible paths, unfamiliar terms and help<!-- profile:first-time --></td><td align="center">✓</td></tr>
<tr><td>In a hurry: repeated clicks, skipped help and required fields only<!-- profile:in-a-hurry --></td><td align="center">✓</td></tr>
<tr><td>Keyboard-focused: Tab, Enter, Escape and menu arrow keys<!-- profile:keyboard --></td><td align="center">✓</td></tr>
<tr><td>Mobile user: phone viewport, quick scrolling and going back when lost<!-- profile:mobile --></td><td align="center">✓</td></tr>
<tr><td>Careful reader: slow reading, persistence checks and cautious deletion<!-- profile:careful-reader --></td><td align="center">✓</td></tr>
<tr><td>Unfamiliar with jargon: unclear terms and plain-language navigation<!-- profile:plain-language --></td><td align="center">✓</td></tr>
<tr><td>Distracted: interruptions, returning halfway and restarting after reload<!-- profile:distracted --></td><td align="center">✓</td></tr>
<tr><td>Detail checker: rereading lists, confirmation and saved-state checks<!-- profile:detail-checker --></td><td align="center">✓</td></tr>
<tr><td>Cautious: undo, full confirmations and hesitation before submission<!-- profile:cautious --></td><td align="center">✓</td></tr>
<tr><td>Explorer: menus, footers, unusual authorized URLs and rarely used pages<!-- profile:explorer --></td><td align="center">✓</td></tr>
<tr><td>Multitasker: duplicated tabs and stale views after an edit<!-- profile:multitasker --></td><td align="center">✓</td></tr>
<tr><td>Text-focused: required fields, errors and states conveyed in text<!-- profile:text-focused --></td><td align="center">✓</td></tr>
<tr><td>Copy-paster: surrounding spaces, accented text, emoji and multiline input<!-- profile:copy-paster --></td><td align="center">✓</td></tr>
<tr><td>Backtracker: Back/Forward, cancelled edits and unfinished drafts<!-- profile:backtracker --></td><td align="center">✓</td></tr>
<tr><td>Search-first: partial names, combined filters and cleared searches<!-- profile:search-first --></td><td align="center">✓</td></tr>
<tr><td>Recovery seeker: correcting invalid input, Undo/Cancel and resuming after errors<!-- profile:recovery-seeker --></td><td align="center">✓</td></tr>
<tr><th colspan="2" align="left">CONTROLLED CHAOS EXPERIMENTS AND EXECUTION CONTROLS</th></tr>
<tr><td>Per-injection admission probability, sampled during the session</td><td align="center">✓</td></tr>
<tr><td>Manual, time-delayed and action-triggered fault injection</td><td align="center">✓</td></tr>
<tr><td>Configurable allowed fault types and excluded users, roles, routes and HTTP methods</td><td align="center">✓</td></tr>
<tr><td>Target groups selected by user, role or route</td><td align="center">✓</td></tr>
<tr><td>Cooldowns between injections, including group-specific intervals</td><td align="center">✓</td></tr>
<tr><td>Limits on simultaneous injections and the fraction of affected users</td><td align="center">✓</td></tr>
<tr><td>Total injection budgets and maximum fault duration</td><td align="center">✓</td></tr>
<tr><td>Forbidden combinations of overlapping faults</td><td align="center">✓</td></tr>
<tr><td>Injection windows by weekday, hour and timezone</td><td align="center">✓</td></tr>
<tr><td>Dry-run admission simulation with recorded decisions and no applied fault</td><td align="center">✓</td></tr>
<tr><td>Live pause/resume and stopping reversible active faults</td><td align="center">✓</td></tr>
<tr><td>Separate controls for scheduled injections and immediate manual faults</td><td align="center">✓</td></tr>
<tr><td>Policy reload for future injections during a session</td><td align="center">✓</td></tr>
<tr><td>Independent incident/health command that can block new injections</td><td align="center">✓</td></tr>
<tr><td>Cross-process coordination of active limits, cooldowns and forbidden pairs through shared local state</td><td align="center">✓</td></tr>
<tr><td>Recorded applied, simulated, skipped and cancelled injections with reasons</td><td align="center">✓</td></tr>
<tr><td>Injection-event tracking and separate engine/hook error counters via configured commands</td><td align="center">✓</td></tr>
<tr><td>Bounded recurring test commands via an external scheduler, with finite attempts and timeouts</td><td align="center">✓</td></tr>
<tr><th colspan="2" align="left">QA CATALOG: ALL 69 CHECKS</th></tr>
<tr><td>First names: alphabets, accents, punctuation and saved values<!-- check:first-name-formats --></td><td align="center">✓</td></tr>
<tr><td>Family names: particles, apostrophes, case and saved values<!-- check:last-name-formats --></td><td align="center">✓</td></tr>
<tr><td>Single names, multiple family names and non-Western name order<!-- check:name-structure --></td><td align="center">✓</td></tr>
<tr><td>Email formats, plus addressing, case, whitespace and invalid addresses<!-- check:email-formats --></td><td align="center">✓</td></tr>
<tr><td>Sign-in with uppercase emails and surrounding spaces (test account)<!-- check:email-case-and-trim --></td><td align="center">✓</td></tr>
<tr><td>International and national phone formats, normalization and mobile keypad<!-- check:phone-formats --></td><td align="center">✓</td></tr>
<tr><td>Postal codes by country, letters, spaces and leading zeros<!-- check:postal-code-formats --></td><td align="center">✓</td></tr>
<tr><td>International addresses, town names and keyboard address suggestions<!-- check:address-formats --></td><td align="center">✓</td></tr>
<tr><td>Birth dates: invalid dates, future dates, age rules and timezone shifts<!-- check:birth-date-rules --></td><td align="center">✓</td></tr>
<tr><td>Date ranges: reversed dates, year boundaries and daylight-saving changes<!-- check:date-ranges --></td><td align="center">✓</td></tr>
<tr><td>Amounts: locale separators, currency precision, rounding and limits<!-- check:amount-formats --></td><td align="center">✓</td></tr>
<tr><td>Quantities: empty, zero, negative, decimal, oversized values and steppers<!-- check:quantity-bounds --></td><td align="center">✓</td></tr>
<tr><td>IBAN: checksum, country length, spaces, case and masked display<!-- check:iban-checksum --></td><td align="center">✓</td></tr>
<tr><td>Company registration numbers and country-specific validation<!-- check:company-id-formats --></td><td align="center">✓</td></tr>
<tr><td>Web addresses: schemes, saved links and unsafe URL schemes<!-- check:url-formats --></td><td align="center">✓</td></tr>
<tr><td>Password rules, passphrases, paste, show/hide and confirmation<!-- check:new-password-rules --></td><td align="center">✓</td></tr>
<tr><td>Free text: Unicode, emoji, line breaks, RTL, CJK and literal markup<!-- check:free-text-content --></td><td align="center">✓</td></tr>
<tr><td>Search: accents, case, symbols, whitespace, empty and unmatched queries<!-- check:search-inputs --></td><td align="center">✓</td></tr>
<tr><td>Uploads: file type, size, empty files, names, removal and replacement<!-- check:file-upload-rules --></td><td align="center">✓</td></tr>
<tr><td>Form validation: required fields, precise errors, focus and retained values<!-- check:form-errors-keep-data --></td><td align="center">✓</td></tr>
<tr><td>Duplicate records after double-clicking or pressing Enter twice<!-- check:double-submit --></td><td align="center">✓</td></tr>
<tr><td>Duplicate submissions after reload, Back and Forward<!-- check:reload-after-submit --></td><td align="center">✓</td></tr>
<tr><td>Saved values after reload and opening a new tab<!-- check:persistence-new-tab --></td><td align="center">✓</td></tr>
<tr><td>Cancellation of edits and recovery of unsaved work<!-- check:edit-cancel --></td><td align="center">✓</td></tr>
<tr><td>Delete confirmation, cancellation, persistence and undo when available<!-- check:delete-safety --></td><td align="center">✓</td></tr>
<tr><td>Lists: empty states, pagination bounds, stable sorting and combined filters<!-- check:list-edges --></td><td align="center">✓</td></tr>
<tr><td>Conflicting edits to the same record in two tabs<!-- check:two-tabs-conflict --></td><td align="center">✓</td></tr>
<tr><td>Private deep links while signed out and return after sign-in (test account)<!-- check:deep-link-auth --></td><td align="center">✓</td></tr>
<tr><td>Account enumeration through password-reset responses (test account)<!-- check:reset-enumeration --></td><td align="center">✓</td></tr>
<tr><td>Account enumeration through sign-in errors (test account)<!-- check:login-enumeration --></td><td align="center">✓</td></tr>
<tr><td>Account enumeration through sign-up responses (product review) (test account)<!-- check:signup-enumeration --></td><td align="center">✓</td></tr>
<tr><td>Throttling after repeated wrong passwords (six attempts, explicit approval) (test account)<!-- check:login-throttling --></td><td align="center">✓</td></tr>
<tr><td>Password masking, paste, password-manager support and URL exposure<!-- check:password-field-hygiene --></td><td align="center">✓</td></tr>
<tr><td>Passwords, session tokens and personal data exposed in URLs<!-- check:secrets-in-url --></td><td align="center">✓</td></tr>
<tr><td>Sign-out, Back, private-page reloads and session invalidation across tabs (test account)<!-- check:logout-session --></td><td align="center">✓</td></tr>
<tr><td>HTML-like input rendered as literal text<!-- check:html-escaping --></td><td align="center">✓</td></tr>
<tr><td>Technical details exposed in error pages<!-- check:error-leaks --></td><td align="center">✓</td></tr>
<tr><td>Access to another authorized test account&#x27;s records (two test accounts)<!-- check:object-access-control --></td><td align="center">✓</td></tr>
<tr><td>Password-reset links: expiry and single use (test mailbox)<!-- check:reset-token-lifecycle --></td><td align="center">✓</td></tr>
<tr><td>Masking of sensitive data after saving (test account)<!-- check:sensitive-display --></td><td align="center">✓</td></tr>
<tr><td>Field labels, required indicators and accessible error associations<!-- check:field-labels-and-errors --></td><td align="center">✓</td></tr>
<tr><td>Completing a whole form using the keyboard<!-- check:keyboard-form --></td><td align="center">✓</td></tr>
<tr><td>Autocomplete purpose and mobile input attributes<!-- check:autocomplete-attributes --></td><td align="center">✓</td></tr>
<tr><td>Reflow at 320 CSS pixels and 200% zoom<!-- check:small-screen-reflow --></td><td align="center">✓</td></tr>
<tr><td>Feedback and recovery during slow or failed saves<!-- check:slow-submit-feedback --></td><td align="center">✓</td></tr>
<tr><td>Clear, actionable error messages in the application language<!-- check:error-message-quality --></td><td align="center">✓</td></tr>
<tr><td>Pasting values, automatic formatting and caret behavior<!-- check:paste-and-formatting --></td><td align="center">✓</td></tr>
<tr><td>Text inputs: empty, whitespace-only, long and special-character values<!-- check:text-input-extremes --></td><td align="center">✓</td></tr>
<tr><td>Numeric inputs: zero, negative, decimal and announced boundaries<!-- check:number-extremes --></td><td align="center">✓</td></tr>
<tr><td>Retrying a submission after an error<!-- check:submit-retry-after-error --></td><td align="center">✓</td></tr>
<tr><td>Interrupted forms: reload, Back/Forward, tab closure and reopening<!-- check:interrupted-form --></td><td align="center">✓</td></tr>
<tr><td>Search/filter races, reset and state retained after navigation<!-- check:search-filter-behavior --></td><td align="center">✓</td></tr>
<tr><td>Success messages checked against actual saved data<!-- check:false-success --></td><td align="center">✓</td></tr>
<tr><td>Unedited fields and attachments retained after another field changes<!-- check:data-loss-on-edit --></td><td align="center">✓</td></tr>
<tr><td>Consistency between lists, detail views, counters, badges and tabs<!-- check:ui-desync --></td><td align="center">✓</td></tr>
<tr><td>Controls reachable on phone, tablet and desktop viewports<!-- check:responsive-controls --></td><td align="center">✓</td></tr>
<tr><td>Horizontal overflow, clipped forms and unreachable submit buttons<!-- check:layout-overflow --></td><td align="center">✓</td></tr>
<tr><td>Tab order, focus visibility, hidden focus targets and modal focus traps<!-- check:keyboard-reachability --></td><td align="center">✓</td></tr>
<tr><td>Accessible names for controls, informative images and frames<!-- check:accessible-names --></td><td align="center">✓</td></tr>
<tr><td>Estimated text contrast (review signal)<!-- check:color-contrast --></td><td align="center">✓</td></tr>
<tr><td>Pointer-target dimensions and spacing (WCAG signal)<!-- check:target-size --></td><td align="center">✓</td></tr>
<tr><td>Page language, title, heading order, duplicate IDs, tabindex and zoom<!-- check:page-structure --></td><td align="center">✓</td></tr>
<tr><td>Live-region markup for results, success messages and errors<!-- check:status-messages --></td><td align="center">✓</td></tr>
<tr><td>Session-timeout warnings, extension and retained work (test account)<!-- check:time-limits --></td><td align="center">✓</td></tr>
<tr><td>Broken images and failed same-site styles, scripts, fonts and resources<!-- check:broken-resources --></td><td align="center">✓</td></tr>
<tr><td>Unhandled JavaScript errors and promise rejections during interactions<!-- check:javascript-errors --></td><td align="center">✓</td></tr>
<tr><td>Conflicting edits by two users on the same record (coordinated users)<!-- check:concurrent-edit-two-users --></td><td align="center">✓</td></tr>
<tr><td>Editor/reader permissions, direct URLs and visibility of changes (coordinated users)<!-- check:role-permissions --></td><td align="center">✓</td></tr>
<tr><td>Changes or deletions made by another user while a screen stays open (coordinated users)<!-- check:shared-object-notifications --></td><td align="center">✓</td></tr>
<tr><th colspan="2" align="left">ADDITIONAL FIELD AND PAGE INSPECTION</th></tr>
<tr><td>Password forms submitted with GET or served over plain HTTP outside localhost</td><td align="center">✓</td></tr>
<tr><td>Session-like cookies readable by JavaScript (review signal)</td><td align="center">✓</td></tr>
<tr><td>Numeric field types that lose phone prefixes or postal-code zeros</td><td align="center">✓</td></tr>
<tr><td>Labels provided only by disappearing placeholders</td><td align="center">✓</td></tr>
<tr><td>Overly short maxlength limits for names, emails and addresses</td><td align="center">✓</td></tr>
<tr><td>Controls covered by sticky bars, banners or other elements</td><td align="center">✓</td></tr>
<tr><td>Clipped text in buttons, links, labels and headings</td><td align="center">✓</td></tr>
<tr><td>Clickable-looking elements unreachable from the keyboard</td><td align="center">✓</td></tr>
<tr><td>Focusable elements inside aria-hidden regions</td><td align="center">✓</td></tr>
<tr><td>Generic link names such as &quot;click here&quot;</td><td align="center">✓</td></tr>
<tr><td>Focus escaping a modal, landing on hidden elements or lacking a visible indicator</td><td align="center">✓</td></tr>
<tr><th colspan="2" align="left">FAULT INJECTION AND RECOVERY</th></tr>
<tr><td>Offline browser context (<code>offline</code>)</td><td align="center">✓</td></tr>
<tr><td>Slow matching requests (<code>slow</code>)</td><td align="center">✓</td></tr>
<tr><td>Aborted application requests (<code>server-down</code>)</td><td align="center">✓</td></tr>
<tr><td>Stop/restart of a local application managed by Chaosfolk (<code>app-stop</code>; replay uses request failure)</td><td align="center">✓</td></tr>
<tr><td>HTTP error responses, including selected routes and methods (<code>http-error</code>)</td><td align="center">✓</td></tr>
<tr><td>Backend writes whose responses are lost (<code>lost-response</code>)</td><td align="center">✓</td></tr>
<tr><td>localStorage write failures from simulated quota exhaustion (<code>storage-full</code>)</td><td align="center">✓</td></tr>
<tr><td>Cleared local/session storage (<code>storage-empty</code>)</td><td align="center">✓</td></tr>
<tr><td>Corrupted browser-storage values (<code>storage-corrupt</code>)</td><td align="center">✓</td></tr>
<tr><td>Page-clock advances (<code>clock</code>)</td><td align="center">✓</td></tr>
<tr><td>Viewport changes during a journey (<code>window</code>)</td><td align="center">✓</td></tr>
<tr><td>Cleared browser cookies (<code>cookies-cleared</code>)</td><td align="center">✓</td></tr>
<tr><th colspan="2" align="left">REPLAY ASSERTIONS AND PERSISTENCE</th></tr>
<tr><td>Expected text visible, absent or present a specified number of times</td><td align="center">✓</td></tr>
<tr><td>Expected field value, exact or containing a substring</td><td align="center">✓</td></tr>
<tr><td>Expected localStorage key/value or JSON content</td><td align="center">✓</td></tr>
<tr><td>Expected URL substring</td><td align="center">✓</td></tr>
<tr><td>No recorded JavaScript page errors</td><td align="center">✓</td></tr>
<tr><td>Page body contains visible text</td><td align="center">✓</td></tr>
<tr><td>Custom JavaScript assertions defined by the project</td><td align="center">✓</td></tr>
<tr><td>Persistence after reload (<code>--persist reload</code>)</td><td align="center">✓</td></tr>
<tr><td>Persistence after reopening the start address (<code>--persist revisit</code>)</td><td align="center">✓</td></tr>
<tr><td>Persistence in a new tab (<code>--persist new-tab</code>)</td><td align="center">✓</td></tr>
<tr><td>Persistence after clearing local/session storage (<code>--persist local-only</code>)</td><td align="center">✓</td></tr>
<tr><td>Behavior after Back (<code>--persist back</code>)</td><td align="center">✓</td></tr>
<tr><td>Duplicates and recovery after retrying the last successful action (<code>--persist retry</code>)</td><td align="center">✓</td></tr>
<tr><td>All supplied field values, with separate acceptance/rejection assertions (<code>vary</code>)</td><td align="center">✓</td></tr>
<tr><td>Equivalent or different final outcomes from two scenarios (<code>compare</code>)</td><td align="center">✓</td></tr>
<tr><td>Repeated treatment/control trials with and without injected faults</td><td align="center">✓</td></tr>
<tr><td>Observed/reference journey comparison with and without faults (2×2 matrix)</td><td align="center">✓</td></tr>
<tr><td>Fixture preparation and identity verification before every trial and retry (project commands)</td><td align="center">✓</td></tr>
<tr><td>Failure rates with valid, invalid and requested trial counts</td><td align="center">✓</td></tr>
<tr><td>Whether saved findings still fail or pass after a fix or in a later campaign</td><td align="center">✓</td></tr>
<tr><td>Saved scenario assertions in CI, with JUnit results (<code>regression run</code>)</td><td align="center">✓</td></tr>
<tr><th colspan="2" align="left">BROWSER JOURNEYS AND COMPATIBILITY</th></tr>
<tr><td>Project-defined create, read, edit, delete and multi-step journeys</td><td align="center">✓</td></tr>
<tr><td>Navigation, links, Back/Forward, tabs and browser dialogs</td><td align="center">✓</td></tr>
<tr><td>Journey comprehension, labels, discoverability and feedback through simulated users</td><td align="center">✓</td></tr>
<tr><td>Assigned behavior profiles, including hurried, distracted, keyboard and mobile users</td><td align="center">✓</td></tr>
<tr><td>Independent users and coordinated users with separate roles on shared records</td><td align="center">✓</td></tr>
<tr><td>Desktop, laptop, tablet and mobile viewport/input emulation</td><td align="center">✓</td></tr>
<tr><td>Chromium, Firefox and WebKit scenario replays (installed browser engines)</td><td align="center">✓</td></tr>
<tr><td>Pixel differences against reviewed screenshot baselines (optional visual extra)</td><td align="center">✓</td></tr>
<tr><th colspan="2" align="left">PERFORMANCE SIGNALS AND OPTIONAL INTEGRATIONS</th></tr>
<tr><td>Observed responsiveness and delays during user journeys</td><td align="center">✓</td></tr>
<tr><td>Bounded local concurrent page-load smoke tests: HTTP errors, median and p95 timings (<code>probe</code>)</td><td align="center">✓</td></tr>
<tr><td>Presence of CSP, X-Content-Type-Options, X-Frame-Options, Referrer-Policy and HSTS headers (local probe)</td><td align="center">✓</td></tr>
<tr><td>Email subject, recipient and body content (Mailpit test mailbox)</td><td align="center">✓</td></tr>
<tr><td>Downloaded CSV files: required columns, row-count bounds and expected content</td><td align="center">✓</td></tr>
<tr><td>Downloaded text files: expected content</td><td align="center">✓</td></tr>
<tr><td>Downloaded PDF files: PDF parsing and expected text (optional PDF extra)</td><td align="center">✓</td></tr>
<tr><td>Automated axe-core accessibility rules (locally supplied axe-core script)</td><td align="center">✓</td></tr>
<tr><td>External k6 load-test results (configured k6 executable and script)</td><td align="center">✓</td></tr>
<tr><td>External Appium test results, including native mobile suites (configured Appium runner and script)</td><td align="center">✓</td></tr>
</tbody>
</table>

Accessibility and security rows describe checks and review signals, not compliance
certification or a penetration test. Mobile viewports are browser emulation;
native-device tests require the external Appium runner. Local performance probes
do not establish production capacity.

Details: [QA catalog](docs/checks.md), [faults](docs/faults.md),
[replay and evidence](docs/replay.md), [regressions and visual checks](docs/regression.md),
[optional integrations](docs/integrations.md), [chaos policies](docs/chaos.md)
and [campaigns](docs/campaigns.md).

</details>

### Watch the trailer

https://github.com/user-attachments/assets/500cdc82-94da-466b-bc26-2f85cfc8072d

## Why

Your tests cover the paths you wrote. Your users double-click Save, lose their
connection halfway through a form and come back an hour later in another tab.
You rarely do these things yourself, because you know how the app is supposed
to work.

An AI agent can explore the app for you, but its "this looks broken" may be
wrong. Chaosfolk reports a bug only after replaying it and seeing it fail again.

## How

Your coding agent runs simulated users. Each one has a goal and one of 16
behavior profiles (in a hurry, keyboard only, on mobile, distracted, unfamiliar
with jargon), drives its own Chromium context and can work through several of
your goals.

While they work, the engine injects the conditions real users meet: offline,
slow or failing requests, lost responses, full or corrupted storage, cleared
cookies, clock jumps and viewport changes.

For a product audit, each tester receives a small batch from the saved selection,
with test values and expected behavior. Those checks cover names in any script,
phone numbers and postal codes from 15 countries, extreme input, double submits,
interrupted forms, account enumeration and keyboard access. Chaosfolk reads the
page's fields before assigning the relevant checks. Work that does not fit in one
batch stays queued for the next, within the scan's limits.

The agent turns each promising observation into a scenario with an explicit
assertion, and the engine replays it without a model. A finding is reproduced
when it fails three times with the fault and passes three control runs without
it. A "saved" message does not count: the replay reloads, reopens, clears local
storage or submits again before checking. Anything less stays labeled as an
observation.

## What it checks

Chaosfolk explores the goals you give it in a real browser. Each agent chooses
its next action from the current page and its assigned behavior: a hurried user
clicks again, a distracted one returns to an unfinished form, a multitasker edits
across tabs. The 16 profiles combine with sampled habits, devices and shuffled
objectives, so exploration can reach journeys beyond the predefined checks.

- **Open-ended exploration.** Try unexpected navigation, interrupted forms,
  repeated actions, stale tabs and recovery after errors. Project memory points
  later campaigns toward less-explored known routes. Use `--checks none` for
  exploration without catalog assignments.
- **Randomized fault scenarios.** Draw faults, start actions, durations and
  parameters within configured ranges. Observe offline use, slow or failing
  requests, lost responses, damaged storage, cleared cookies and clock changes
  while users work. Keep the seed for the draw and the recorded actions for replay.
- **Controlled chaos experiments.** Set admission probability, target groups,
  exclusions, cooldowns, affected-user limits and allowed time windows. Simulate
  injections first, pause them live, consult an incident gate and coordinate
  concurrent sessions sharing a local environment.
- **Systematic QA and proof.** Assign the 69 catalog checks, vary field values,
  measure UI/accessibility signals and compare recorded outcomes. Repeat a
  candidate with and without faults, optionally against a reference journey,
  and report failures alongside invalid trials and product severity.

The controlled experiments use probability, grouping and scheduling patterns
also documented by [Netflix's Chaos Monkey](https://netflix.github.io/chaosmonkey/Termination-behavior/).
Chaosfolk applies its faults inside browser contexts and an explicitly managed
local test process; it has no cloud-instance or Kubernetes termination adapter.
See [chaos policies](docs/chaos.md) for controls and limits.

These commands run without a model, alongside agent exploration, and feed the
same report. Expand the [full test checklist](#test-checklist) above for every
listed capability.

| Command | What it does | Example of a problem it finds |
| --- | --- | --- |
| `fields` | Classifies every field of a page and lists the checks that apply | A postal code in `type=number` loses its leading zero |
| `vary` | Replays a form once per test value of a field, for the countries you serve | `+44 7700 900123` refused because the rule only knows French numbers |
| `compare` | Replays two scenarios and compares their outcomes | Password reset says "no account for this email" |
| `audit` | Measures a page at several screen sizes, then tabs through it | The submit button leaves the screen at 320 px; keyboard focus gets stuck |
| `replay --persist` | Reloads, reopens, clears storage or retries before asserting | A success message with nothing saved; a duplicate after a retry |
| `campaign` | Keeps a project's findings across runs and replays the open ones | A fix that came back two campaigns later |

Test values cover several countries, because validation should follow the
user's country. Security checks are passive and use synthetic accounts. `audit`
reports WCAG signals such as contrast, target size, names and reflow; confirm
them by hand, they are not a conformance audit. See the
[QA checks guide](docs/checks.md).

You name each app with a project name instead of relying on `localhost:3000`.
Chaosfolk then remembers the journeys already explored, so the next testers go
elsewhere, and the findings of every campaign, so you check a fix by replaying
what failed. Testers can work on separate data, or on the same records with
different roles to find conflicts and permission gaps. See
[campaigns and sessions](docs/campaigns.md).

## What you get

A local HTML report in English or French.

### Findings, evidence and a fix prompt

The report gives a score out of 100, the findings by severity and the evidence
for each one: replay results, screenshots and the expected behavior. Tick the
findings you want fixed and copy the generated prompt into your coding agent.

![A finding opens to reveal its evidence, then selected findings are assembled into a fix prompt.](assets/audit-findings.gif)

### Synchronized session replay

Every tester's screen plays on one timeline. You can change the speed and jump
to the moments where something went wrong.

![Synchronized browser screens playing back a recorded session.](assets/audit-replay.gif)

Both recordings come from Chaosfolk auditing its own report with four simulated
users. The score is a [documented heuristic](docs/scoring.md) for one session,
not a measure of coverage.

## Install

One command installs the engine, its browser and the skill for each coding
agent found on your computer (Claude Code, Codex, Cursor, GitHub Copilot,
Gemini CLI, OpenCode and Windsurf). You don't need Python, Node.js or Git.

**macOS and Linux**

```bash
curl -LsSf https://raw.githubusercontent.com/loukan42/chaosfolk/v0.8.0/install.sh | CHAOSFOLK_SOURCE=https://github.com/loukan42/chaosfolk/archive/refs/tags/v0.8.0.zip sh
```

**Windows**, in PowerShell

```powershell
$env:CHAOSFOLK_SOURCE = 'https://github.com/loukan42/chaosfolk/archive/refs/tags/v0.8.0.zip'
powershell -ExecutionPolicy ByPass -c "irm https://raw.githubusercontent.com/loukan42/chaosfolk/v0.8.0/install.ps1 | iex"
```

**With the [Skills CLI](https://github.com/vercel-labs/skills)** ([skills.sh](https://skills.sh))

```bash
npx skills add loukan42/chaosfolk --skill chaosfolk -g
```

The Skills CLI installs the skill, not the engine it drives. Run the macOS and
Linux or Windows command above as well.

Then restart your coding agent and ask it: `Run chaosfolk check and tell me if
anything is missing.` These commands install version 0.8.0. To update later,
use the commands in the newer release's README.

If your agent can start subagents, testers run in parallel. Otherwise the agent
plays them one after another, which takes longer and makes them less
independent.

<details>
<summary>What the installer does</summary>

1. Installs [uv](https://docs.astral.sh/uv/) if it is missing. uv downloads
   Python 3.12 or newer into its own folder when your computer has none.
2. Installs the Chaosfolk engine as a command-line tool, isolated from your other
   Python packages, and adds it to your PATH.
3. Runs `chaosfolk setup`, which downloads Chromium when no usable browser is
   found, copies the skill into each agent's skills folder and, for Claude Code,
   adds the simulated user definition. That definition runs testers on Sonnet
   with only the shell and file reading.

You can read [install.sh](install.sh) and [install.ps1](install.ps1) before
running them. Set `CHAOSFOLK_NO_MODIFY_PATH=1` to keep your PATH unchanged.

</details>

<details>
<summary>Other ways to install</summary>

- **Your agent was not detected**, or you want one agent only: run
  `chaosfolk setup --agent claude-code`. The other ids are `codex`, `cursor`,
  `github-copilot`, `gemini-cli`, `opencode`, `windsurf`, and `universal` for the
  shared `~/.agents/skills` folder.
- **With pipx or uv** you already use:
  `pipx install git+https://github.com/loukan42/chaosfolk.git`, or
  `uv tool install git+https://github.com/loukan42/chaosfolk.git`, then
  `chaosfolk setup`.
- **Manual installation** and details for each agent: see the
  [agent guide](docs/agents.md).

</details>

<details>
<summary>Something went wrong?</summary>

- **`chaosfolk: command not found`**: open a new terminal; the installer added
  Chaosfolk to your PATH for new terminals only.
- **`chaosfolk check` shows a missing browser**: run `chaosfolk install-browser`.
  On Linux, `chaosfolk install-browser --with-deps` also installs the system
  libraries Chromium needs.
- **Your agent does not know Chaosfolk**: restart it, or run
  `chaosfolk setup --agent <id>` for the agent you actually use.
- **To uninstall**: run `uv tool uninstall chaosfolk`, then delete the
  `chaosfolk` folder from your agent's skills folder.

</details>

## Try the demo

The demo needs no AI agent or API key. It starts a small local app whose form
loses your draft when storage is full, runs real browser trials on the broken
and fixed versions, then writes the report.

```bash
chaosfolk demo --lang en
```

Open `.horde/demo/rapport.html` in the folder where you ran the command, and
keep it next to its screenshot folders. Use `--lang fr` for French; the report
has a language switch.

## Use it on your app

Start your app locally, open your coding agent in its project, and ask:

```text
Use Chaosfolk on my local test app at http://localhost:3000, project "shop-front".
Explore creating, finding and editing a project. Use the medium run size,
synthetic data and an English report. Do not send messages or make purchases.
Report what you find without changing the app.
```

For a QA pass, name the themes and what matters to you:

```text
Run Chaosfolk on project "shop-front" at http://localhost:3000 with the themes
functional, security and accessibility. Our customers are in France, Belgium and
Switzerland. Check every form field with the catalog, prove persistence after
reload, check the password reset for account enumeration with the test account
test@example.com, and audit the sign-up page on mobile and desktop.
```

After a fix, ask: `Replay the open Chaosfolk findings for shop-front and tell me
what is fixed.`

The themes are `functional`, `ux`, `accessibility`, `resilience`, `security`,
`performance` and `compatibility`, or `all`. The report shows which ones were
tested, partly tested or left out.

Three run sizes are available. Preview one with `chaosfolk plan --level medium`.

| Run size | Simulated users | Actions per user |
| --- | ---: | ---: |
| Low | 2 | 12 |
| Medium | 4 | 20 |
| High | 12 | 40 |

These numbers cap browser actions, not tokens. Model cost depends on your agent
host, your pages and the analysis. If the host exports its usage,
`chaosfolk usage` stops the next batch at a token or cost limit.

## Control fault injection

Existing runs keep their users, action budgets and fault pool. Optional chaos
policies let you limit simultaneous faults, the fraction of affected users,
injection probability, frequency and duration. You can group users by role or
journey, exclude targets and prevent certain faults from overlapping.

The engine applies these rules without a model. A blocked injection is skipped
with a recorded reason; it never waits for a slot or retries to fill a quota.
Policies add no simulated users, exploration steps or automatic replays.

To create a policy and use it for a short run:

```bash
chaosfolk chaos init --file qa/chaos.json
chaosfolk chaos check qa/chaos.json
chaosfolk launch --url http://localhost:3000 --project shop-front --folder .horde/run --level low --chaos-policy qa/chaos.json
```

Continue with the usual exploration workflow. The generated policy allows at
most one active injection, four admissions per session and 20 seconds per fault,
with at least 10 seconds between admissions. These are caps, not targets.
Edit the JSON or use TOML for your own rules. `chaos init --project shop-front`
saves a policy that future sessions of that named project load automatically.

Add `--dry-run` to `launch` to record injections without applying them. Simulated
injections never count as real fault evidence. Browser exploration still runs,
and ordinary user actions can still change test data.

During a session, the coordinator can run:

```bash
chaosfolk chaos pause --end-active
chaosfolk chaos resume
chaosfolk chaos inspect --folder .horde/run
```

Pause and resume require `CHAOSFOLK_LEADER_TOKEN`. `--end-active` removes reversible
faults; it cannot restore cleared cookies or storage. `inspect` reads the saved
injection plan, its statuses and skip reasons, including after the session ends.

Time windows, coordination between runs sharing a test environment, and incident,
tracking and credential hooks are opt-in. Recurring jobs start disabled unless
explicitly enabled, require a finite attempt budget and timeout, and run through
an external scheduler. Prefer saved scenario replays for recurring fix checks.
Commands or hooks you configure can add runtime and model costs of their own.
See [chaos policies and recurring jobs](docs/chaos.md) for configuration and limits.

## Keep what you found

Once a finding is proven, you can keep it as a test that runs without a model:

```bash
chaosfolk regression export .horde/run/scenarios/h02-save.json --output tests/test_save_draft.py
chaosfolk regression run qa/scenarios/*.json --output qa-results
```

The first command writes a plain Playwright test for your repository. The
second replays saved scenarios in CI and writes JUnit results: exit code 1 is a
product failure, 2 means the run itself cannot be trusted. Visual comparison
and Firefox and WebKit are covered in [regression tests and CI](docs/regression.md).

Other commands:

- `chaosfolk planning changes` picks the journeys a pull request touches ([planning](docs/planning.md)).
- `chaosfolk privacy` makes a copy of a report you can share.
- `chaosfolk benchmark run` checks the harness on apps with known defects ([benchmark](docs/benchmark.md)).
- Optional adapters cover a Mailpit test mailbox, downloaded files, axe-core,
  k6, Appium and a read-only MCP server ([integrations](docs/integrations.md)).

## Limits

Chaosfolk is alpha software. Its users are fictional, so their reactions are
test hypotheses, not research with real people. Security checks are passive,
performance probes are small local smoke tests, accessibility signals
(including estimated contrast) are not a conformance audit, and mobile means
browser emulation. For more depth, you still need product knowledge, a
dedicated security test, a screen reader review and real devices.

Run it only on local apps or test environments you are allowed to test, with
synthetic data. Screenshots can contain sensitive content: review them before
sharing. See [SECURITY.md](SECURITY.md).

---

[Workflow and coverage](docs/workflow.md) · [QA checks](docs/checks.md) · [Campaigns and sessions](docs/campaigns.md) ·
[Fault injection](docs/faults.md) · [Chaos policies](docs/chaos.md) · [Replay format](docs/replay.md) · [Regressions and CI](docs/regression.md) ·
[Planning](docs/planning.md) · [Integrations](docs/integrations.md) · [Benchmark](docs/benchmark.md) · [Changelog](CHANGELOG.md) · [Contributing](CONTRIBUTING.md) · [MIT license](LICENSE)
