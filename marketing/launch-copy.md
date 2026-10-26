# Launch drafts

These drafts are for review and publication by the maintainer after release checks.
They have not been posted. Update commands and measured details if the release changes.

## English launch post

I built Chaosfolk to test the paths I forget to write down.

It gives simulated users their own browser and goal. They can lose their
connection, switch tabs or run into a full browser store while trying to finish.
Your coding agent coordinates the exploration.

When a user flags a problem, the next step is an explicit assertion and a browser
replay. A fault-related bug needs three failing runs with the fault and three
passing controls before the report calls it reproduced.

The local demo starts with a form that clears your draft before saving. Fill the
browser store and the save fails. The report compares that version with a fix,
using real Chromium trials. You can run the demo without an AI API key.

Chaosfolk is an MIT-licensed alpha. Simulated feedback still needs judgment, and
this does not replace tests with real users. I would like feedback on the first
run: where installation breaks, where the report is unclear, and which findings
survive replay on your app.

[Code and installation](https://github.com/loukan42/chaosfolk)

## Short English post

Chaosfolk lets simulated users explore a web app, then replays suspected bugs
with fault and control trials. The local demo shows a failed save losing a draft,
followed by the corrected behavior. MIT licensed, alpha, no AI key needed for the
demo.

[Try Chaosfolk](https://github.com/loukan42/chaosfolk)

## LinkedIn, français

Un formulaire qui efface ta saisie avant de l’enregistrer. Le stockage du
navigateur est plein. L’enregistrement échoue, et ton texte a disparu.

C’est le premier défaut que tu peux reproduire avec Chaosfolk, le projet open
source que je publie.

Le principe : donner une mission à des utilisateurs simulés par des agents IA,
chacun dans son navigateur, puis provoquer des imprévus pendant qu’ils essaient
de la terminer. Un réseau qui coupe, une fenêtre qui change de taille, un
enregistrement qui échoue.

Quand un agent signale un problème, il reste à le vérifier. Chaosfolk rejoue le
parcours trois fois avec la panne, puis trois fois sans elle. Le rapport conserve
les captures et les résultats. Les commentaires des personnages restent des
observations simulées.

La démo fonctionne en local, sans clé API : elle compare le formulaire cassé et
sa version corrigée dans de vrais navigateurs Chromium.

Le projet est en alpha, sous licence MIT. Si tu le testes sur une maquette, je
veux surtout savoir où tu bloques et quel défaut tu arrives à reproduire.

[Le dépôt Chaosfolk](https://github.com/loukan42/chaosfolk)

## Welcome discussion for the repository

Title: First run with Chaosfolk? Share what happened

Start with the local demo in the README. Then choose one small local app and one
goal, such as creating a project and finding it again.

When sharing your result, include your OS, Python version, agent host and Chaosfolk
version. Say whether installation completed, whether the report opened and whether
you reached a useful replay. A short explanation of the first blocker is useful
even if the session never finished.

Screenshots and traces can contain app data. A small synthetic reproduction is
easier to share and maintain. Put reproducible engine errors in Issues; keep
questions about test goals and report interpretation in this discussion.

## Reddit draft for a community that permits project feedback

Title: I built a local tool that replays AI-reported UI bugs with control trials

I’m the author of Chaosfolk, an open-source alpha for exploring web apps with
simulated users. I want feedback on whether its evidence is useful to developers
and testers.

An agent gives each fictional user a goal and separate browser context. The
engine can introduce a network or storage failure. After an observation, the
coordinator writes an assertion and replays the trace three times with the fault
and three times without it.

The bundled demo is deliberately small: a project form loses its draft when a
storage write fails. Real browser runs compare that code with a fix. The demo
needs Python and Chromium, with no model API key.

I’m particularly interested in false positives: findings that look convincing
in an agent’s narration but disappear under a useful assertion or control. If
you try it, what would you need to trust the report enough to act on it?

[Repository and runnable demo](https://github.com/loukan42/chaosfolk)

Choose one community with a relevant audience, read its current rules and adapt
the draft to its feedback format. No subreddit approval has been checked here.
Reddit's [spam policy](https://support.reddithelp.com/hc/en-us/articles/360043504051-Spam)
prohibits repetitive mass promotion and makes local community rules relevant.

## Show HN author briefing

Write the submission yourself. Hacker News explicitly asks for human-written
posts and comments, including no AI-edited text, and prohibits automated posting.
This section is factual preparation, not submission copy. See the
[HN guidelines](https://news.ycombinator.com/newsguidelines.html).

Facts the maintainer can explain from personal experience:

- Why you built the tool and one failure that made you want it.
- How exploration differs from the deterministic demo.
- The assertion used for the lost-draft bug and what each control establishes.
- What happened when you ran the released version, including unresolved failures.
- The cost boundary: the engine has no model provider; the agent host supplies models.

Link the runnable repository. Use the required Show HN title prefix and stay
available to discuss the implementation. Show HN expects something people can
try, and advises removing sign-up barriers. It also forbids asking friends to
upvote or comment. [Show HN guidelines](https://news.ycombinator.com/showhn.html).
