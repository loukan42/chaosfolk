# Reference review

The maintainer selected Superpowers and agent-browser as quality references.
This review inspects their published README material. It is not a claim that
Chaosfolk matches their maturity, performance, compatibility or adoption.

## What to borrow

| Reference | Observed in the reference | Application to Chaosfolk |
| --- | --- | --- |
| Superpowers | The README describes an agent workflow, gives installation paths by host, and links community and troubleshooting sections | Explain the coordinator/user contract; document verified hosts separately; give users a place to report a blocked session |
| agent-browser | The README starts with an executable installation path and a short browser command sequence; detailed command behavior follows | Let a new user run a deterministic demo before learning the entire command catalog; explain failure exits and required browser installation |

Read directly: [Superpowers README](https://github.com/obra/superpowers/blob/b739a8af570e10a95898f2bdf6cec97467fa6c12/README.md),
[agent-browser README](https://github.com/vercel-labs/agent-browser/blob/815ba8d4ddb3018dc86cf792bdf72c29d4c7addc/README.md).
These snapshots were inspected during launch preparation on 26 October 2026.

## Comparable tests

For installation clarity, give a new developer only the README and a fresh
environment. Record whether they reach the first documented result, every command
they had to correct and elapsed time excluding downloads. Repeat with each
reference's corresponding quick start. Use comparable machines and disclose the
different runtime requirements. That measures setup friction, not overall product quality.

For the skill instructions, use one test app and the same explicit user goals.
An independent reviewer should inspect the executed actions and resulting report:
did the agent remain in scope, finish cleanup and distinguish observations from
proof? Compare the clarity of workflow and recovery behavior with the relevant
reference instructions. No numerical superiority claim should precede this test.

For the report, hide project branding and ask reviewers to identify the failing
behavior, control result and next action from a real artifact. Measure incorrect
answers as well as preference. The browser CLI reference does not provide the same
report product, so a direct “better than agent-browser” UI claim would be misleading.

## Current gaps to close

- The Python engine and skill are separate installation steps; the README must
  make the distinction visible before a user installs only the skill.
- A local engine smoke test does not establish every agent host's compatibility.
- The deterministic demo proves the fixture and replay path, not autonomous
  discovery on an unseen app.
- Community support, repeat use and external contribution quality require outside
  users over time. They cannot be established by a launch rewrite.

No blind comparison has been completed by this marketing work. Keep the findings
from technical or independent reviews alongside this document when they are available.
