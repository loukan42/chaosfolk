# Chaosfolk launch kit

These are launch materials, not records of messages sent. Publish release copy
after the public repository, installation path and demo have passed their checks.

Chaosfolk is an open-source agent skill and Python browser engine for exploratory
web QA. Simulated users try the app; deterministic browser replays check whether
a suspected failure holds under an explicit assertion and a control.

The first audience is developers who already use coding agents and want evidence
before shipping a local prototype or web-app change. The first useful action is
to run `chaosfolk demo --lang en`, inspect the report, then try one small test app.

## Reusable copy

Repository description:

> Simulated users explore your web app. Fault injection, deterministic replays and local evidence reports.

Short description:

> Chaosfolk gives AI users separate browsers and different habits, then turns
> promising bug reports into repeatable browser scenarios with control trials.

Suggested topics:

```text
agent-skills ai-agents exploratory-testing browser-testing playwright qa
fault-injection developer-tools python
```

Use [the launch drafts](launch-copy.md) for owned channels and a relevant community.
[The demo script](demo-script.md) specifies footage that can be recorded from the
shipped fixture. [The adoption plan](adoption-plan.md) ties each distribution step
to an observable result. [The reference review](reference-review.md) records what
we borrowed as a quality target and where comparison is still incomplete.

## Claims and evidence

| Claim | Evidence required before publishing it |
| --- | --- |
| Local demo without a model API key | A clean install followed by a successful `chaosfolk demo --lang en` run |
| A storage fault loses the draft in the broken fixture | Three valid treatment failures and three passing controls in the generated replay files |
| The corrected fixture handles this fault | Three valid corrected treatment passes and three passing corrected controls |
| A particular agent host is supported | An installed skill completes a real smoke session on that host; list version and date |
| A release works on an OS/Python combination | Passing CI or a recorded local test for that exact combination |
| Users returned or found a useful defect | Consented feedback or linked public evidence, with the sample size |

The 100,000-star ambition is a long-term adoption goal. Do not put it in a product
claim. Publish measured installs, usable reports and outside contributions when
there is data to support them. Never buy stars, manufacture testimonials or count
repeated maintainer installations as user adoption.

## Release handoff

Before announcing, open the public repo while signed out, follow its installation
instructions in a fresh environment and confirm the release assets match the tag.
Attach a screenshot from the synthetic demo. Keep private session folders out of
public assets. The first announcement should point to the exact release or commit
that was verified, not an untested moving branch.

Enable a small set of repository discussion categories: usage help, demo results
and ideas. Keep reproducible engine defects in Issues. GitHub documents how to
enable and organize this forum in its [Discussions quickstart](https://docs.github.com/en/discussions/quickstart).
