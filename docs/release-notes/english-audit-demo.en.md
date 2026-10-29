# Product-audit recording in English

The README's product-audit GIF and still image now use English labels for scan
depth, test selection, status and usage limits.

The recording script applies these translations on each run. It uses a real
local session and verifies the saved selections and limits in SQLite. The audit
does not start during recording; no test results or AI usage estimates appear.
These translations apply to the recording, while the live dashboard keeps its
existing language.

Release notes will be provided in English and French for every release, with
both versions linked from the README and changelog.

[Version française](english-audit-demo.fr.md)
