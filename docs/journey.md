# Cover the business journey

A random crowd finds what nobody planned for. It does not cover a journey: four users of
twenty actions rarely pass through the same place twice, and never through every step. The
serious defects of a multi-step journey sit in its transitions: switching mode halfway,
submitting, going back, finishing. This phase plays them one by one, before the random users
and before the audit queue, whatever level or depth was chosen.

Why: on a health-insurance quote app with two modes (a chat assistant and a form leading to the
same file), a Deep audit of 45 minutes returned five generic findings (error page,
accessibility, a spelling mistake). A human tester then found three steps skipped after
switching from the assistant to the form, a delayed synchronisation between the modes, a field
never asked for but pre-filled, and one product range named differently in each mode. No
simulated user had clicked "Save and continue" after a mode switch: the time had gone into
generic checks and into reproducing one finding by hand.

Command conventions, leader token and folder: see the start of [workflow.md](workflow.md).

## 1. Draw the map

During reconnaissance the scout follows the main path to the end in every mode, noting the
title and number of each step. The coordinator then writes `<folder>/parcours.json`:

```json
{
  "etapes": [
    {"n": 1, "nom": "Contract start date", "route": "/quote/date"},
    {"n": 2, "nom": "Contract data"},
    {"n": 3, "nom": "Range choice"},
    {"n": 4, "nom": "Needs survey", "questions": 5},
    {"n": 5, "nom": "Cover level and price"},
    {"n": 6, "nom": "Summary"}
  ],
  "fin": "Subscription",
  "modes": ["Assistant", "Form"],
  "progression": ["Save and continue", "Continue"],
  "retour": ["Back"],
  "depart": "address that opens a fresh file",
  "cases": []
}
```

- **Steps**: all of them, numbered as the screen numbers them, up to the last phase
  (subscription, test payment, confirmation). A forbidden phase (a real payment, a real
  message) is noted in `fin` and never crossed.
- **Modes**: every way of doing the same thing on the same file: chat assistant and form, list
  and detail, step by step and single page, desktop and mobile when the journey changes. With a
  single mode the matrix shrinks to the straight journeys.
- **Start**: an app that opens a fresh file at each visit of an address (a token in the URL)
  restarts from that address for every journey. Never reopen another tester's file. A one-time
  link (a second load answers 401 or "Unauthorized") needs one per journey, never opened before,
  so neither by the user nor by a trial. The safest start is the page that makes those links (an
  "Open" button on a demo page the user names): give it as `--url`, each tester clicks the button
  itself and the app opens through its own links. Check with the scout first that the tab opened
  by the button is followed (`tab`). Otherwise ask the user for as many fresh links as journeys.
  Never pass a token through a tool that masks it. A button that reloads the link's address (end
  of journey) is tested too: it leads to an error screen.
- An incomplete map (end never reached, mode never opened): keep exploring. Do not draw the crowd
  on a half-made map.

## 2. The matrix

Each cell is an action and an expectation, with an identifier (`M01`...) listed in `cases`:

| Cell | Action | Expectation |
|---|---|---|
| Straight journey, one per mode | the whole journey in a single mode; at each validated step, Back once, then validate again | each step is shown once, in order; Back returns to the previous step with answers kept; the end is reached |
| Switch mode after step N | finish step N in A, switch to B, validate in B | B shows step N+1, not N+2 or later; the answer given in A is in B |
| Switch mode in the middle of step N | answer part of step N in A, switch to B, validate | B stays on N and asks for what is missing; never the next step without the answers |
| Finish in one mode, validate in the other | finish the last step in A ("Continue", "Step done"), go back to B, validate | the remaining steps (price, summary) are shown before the end |

Switch in both directions (A to B, B to A). After each progress click, note the step displayed
(title, badge, address): a step never displayed between two validations is a skip, even if Back
shows it afterwards.

Play the matrix in zigzag to save actions: a journey that switches mode at every step tests one
transition per step. For 6 steps and 2 modes, five journeys are enough: straight in A, straight
in B, zigzag starting from A, zigzag starting from B, a switch in the middle of every
multi-question step. After a skip, note the cell, click Back to the expected step and carry on:
the rest of the journey stays testable.

## 3. Two views, one file

During the journeys, after each answer in one mode, look at the other mode without validating
anything:

- Is the value there at once, or only after a block of questions ends? Note the moment. With no
  written rule it is a finding "to confirm" with the question: synchronised at each answer or at
  the end of a block?
- Is it named the same way? One object named differently from one view to the other ("Range name
  1" in the assistant, "Product name 1" in the form) is reported, even on a mock-up: the user
  cannot know it is the same thing.
- Does the assistant announce a finished step ("Step done") that the form does not show as
  finished, or the reverse?

## 4. Field inventory

Cross the fields of each form step (`chaosfolk fields e0 --save <folder>/fields-step<N>.json`)
with what the assistant asks. For each field: asked by the assistant (yes, no, sometimes), value
present before any answer, mandatory or not. Report:

- a field never asked and filled in for the user (occupation preset to a value): a defect if it
  weighs on what follows (price, eligibility, document), otherwise "to confirm" with the
  question "which rule justifies this value?";
- a value present before the question that collects it (needs at "High" before the needs
  survey);
- a list where one option is chosen by default, with neither "Choose" nor an empty field.

These are not demo values: the app decides in the user's place. The rule about fixture data
(see the main guide) does not discard them.

## 5. Conversational assistant

An assistant driven by a model does not answer twice the same way. Compare the matrix journeys
that go through it:

- the order and grouping of questions (birth date, postal code and scheme asked together or
  apart);
- forgotten questions (a form field never asked, section 4);
- its presence in every phase, to the end: an assistant that disappears at subscription is noted
  "to confirm";
- what each of its buttons does ("Continue" after "Step done"): which step is shown next, which
  ones are validated without having been shown.

A variation is not a defect by itself. Note it, "to confirm" if it changes what the user must do
or sees.

A model's answers take time: give the testers `"attente_max": 600` (cumulative seconds of
waiting, 60 by default, from 1 to 1800) and the scout too, in its file.

## 6. Visual review

The screen read as text shows neither alignment nor overlap. At the end of the matrix the
coordinator opens one screenshot per step and per mode (`chaosfolk trace <tester> --around <n>`
gives the screenshot of an action) and looks: amounts and labels aligned in columns, price or
formula boxes without offset, clipped text, a button overlapping another. A misalignment is
`ui`, `mineur`; it is proven by the screenshot, without replay.

## Who plays the matrix

Directed testers, not the crowd: hand-written users, `t01` to `t06`, whose `intention` gives
their journeys with, for each cell, the action and the expectation. Two journeys at most per
tester.

```json
{
  "humains": [
    {
      "id": "t01",
      "nom": "Acceptance tester 1",
      "age": 35,
      "metier": "acceptance tester",
      "profil": "Acceptance tester",
      "aisance": "high",
      "patience": 5,
      "appareil": "desktop",
      "intention": "Play the zigzag starting from the Assistant, from the start address. M03: answer step 1 in the Assistant, switch to Form, Save and continue; expected: step 2 Contract data. M04: fill step 2 in the Form, switch to the Assistant; expected: it asks the step 3 question. After each click, note the number and title of the step shown, and look at the other mode. Finish with done and one line per cell: M03 held, or M03 broken at action N, step shown and step expected.",
      "histoire": "receives the acceptance matrix from the project manager",
      "habitudes": ["notes the step shown after every click", "rereads every pre-filled value before validating"],
      "manies": ["looks at the other mode after every answer"],
      "budget": 80,
      "duree": 1500,
      "attente_max": 600
    }
  ]
}
```

```bash
chaosfolk humans <folder>/testers.json
chaosfolk sheets --folder <folder> --level medium --data "<synthetic data>" --forbidden "<forbidden actions>"
```

`humans` adds the testers to `personas.json`; a later `draw` keeps them (it replaces only the
drawn users). Run the testers like the crowd (one subagent per sheet, three at a time) and read
their reports before drawing the crowd. Each broken cell is flagged by the tester with `flag`;
it goes to triage ahead of the other candidates, and its scenario is extracted from the tester
(`chaosfolk extract t01 --up-to <n>`).

## Budget

- The matrix comes before the crowd, the audit queue and any reproduction. Allow its time in
  `launch --max-duration` or in the audit's limit: about 10 minutes per batch of three testers,
  more with a slow assistant.
- No hand reproduction during the matrix. Afterwards a hand reproduction is limited to 3 trials
  and a control, then move on to the next finding.
- Budget spent before the end of the matrix: partial report, unplayed cells "untested", and the
  summary says so first.

## In the report

Each cell becomes a property of `constats.json`: `{"id": "M03", "enonce": "Assistant then Form
after step 1, Save and continue: step 2 shown", "statut": "broken", "constat": "C1"}`. A general
property ("switching mode keeps answers and position") is `held` only if all its cells are
played and held; one played cell never makes it `held`, and an unplayed cell leaves it `untested`.

Each question about the expectation (synchronised per answer or per block, assistant limited to
the simulation, match between range and formula, default value) becomes a `product-decision`
finding, status "to decide", with the question in `suite`. All of them, no cap: it is the list
the product team settles.
