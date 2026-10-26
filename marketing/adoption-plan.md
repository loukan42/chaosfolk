# Adoption plan

The first decision is whether an outside developer can get a useful report without
the maintainer explaining the tool in a call. Track that before optimizing for stars.
The numbers below are proposed acceptance targets, not existing results or forecasts.

## Release and learning sequence

| Stage | Work | Evidence needed to move on |
| --- | --- | --- |
| Ready to try | Public repo, tagged release, passing checks, working demo, screenshot, issue templates, installation docs | A fresh environment installs the released artifact and completes the demo using only the README |
| First outside users | Share one announcement on an owned channel; invite feedback from people who choose to try it | Ten outside developers report where the first run succeeded or failed; fix repeated setup blockers |
| Useful exploration | Publish two small test-app examples with goals, seed, model host and replay evidence | Five outside users complete an exploration; at least three share a reproduced issue or a documented false positive |
| Wider distribution | Publish one technical walkthrough, pursue relevant skill listings or integrations, offer the runnable demo to one permitted community | Visitors from each channel can reach installation and a report; support questions have documented answers |
| Repeat use | Improve the top recurrent blocker, add portable examples and invite small test-backed contributions | Outside users report a second session on another change; at least one external code contribution is reviewed and merged |

A practical first cycle is four weeks, adjusted to actual feedback. In week one,
fix installation failures. In week two, watch consented first runs and improve the
report. Use weeks three and four for examples and wider distribution only if the
earlier evidence supports it. A large launch does not compensate for a broken
first run.

## Metrics

| Metric | Collection | Interpretation |
| --- | --- | --- |
| Unique repository visitors and clones | Maintainer's GitHub traffic view, sampled weekly | Interest and attempts to obtain source; neither proves use |
| Skill installs | skills.sh aggregate installation counts when listed | Distribution of the skill; not active usage or engine installs |
| Demo completion | Optional first-run feedback with version and outcome | Installation quality; include failures and the reporting sample size |
| Useful replay | Optional report of an actionable reproduced issue | Product value; distinguish fixture demos from outside apps |
| Repeat use | Voluntary follow-up from the same participant | Retention signal, subject to response bias |
| Outside contributions | Merged PRs and reviewed fixtures | Whether others can understand and improve the project |
| Stars | Public repository count | Awareness and interest; report separately from use |

The engine has no usage telemetry. Do not describe GitHub clones or install counts
as active users. Keep any consented participant notes private; publish aggregate
counts with sample size and period.

## Distribution routes

The public repository plus `npx skills add loukan42/chaosfolk --skill chaosfolk`
is the first skill distribution route. The skills.sh FAQ says real installs via
the CLI's anonymous telemetry cause skills to appear in its rankings. There is
no need to invent a manual submission process. Verify the resulting listing
before adding an install-count badge. [skills.sh FAQ](https://skills.sh/docs/faq).

The installer has its own telemetry, separate from Chaosfolk. Its documentation
provides `DISABLE_TELEMETRY=1` for opting out. Keep this distinction in installation
and privacy copy. [Skills CLI reference](https://skills.sh/docs/cli).

GitHub Discussions can collect usage questions and examples after it is enabled.
Start with a welcome post and link answers from the README. Keep defects with
reproduction steps in Issues. [GitHub Discussions setup](https://docs.github.com/en/discussions/quickstart).

Official agent marketplaces are a later route. The references below show that
established projects use them, but Chaosfolk is not listed or approved by those
providers. A submission needs a packaged integration and a real host compatibility
test before any “official” or “supported” badge is used.

## Concrete next experiments

1. Have a developer unfamiliar with the project follow the README on Windows and
   another on Linux. Record the first error and the number of manual corrections.
2. Compare the README's no-key demo path against an agent-first introduction with
   a small consenting sample. Ask which path made the report's evidence clearer.
3. Publish an example of a false positive that replay rejected. Make the assertion
   and control inspectable; measure whether it reduces evidence-interpretation questions.
4. Add one fixture from an outside contributor, with permission and synthetic data.
   Use the review to improve the contribution guide.

The next cycle should follow the most frequent observed failure. Keep a dated
record of the sample and result rather than setting a publication quota.
