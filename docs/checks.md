# QA checks

Random exploration finds what nobody thought of. A QA team also runs the same
solid checks on every form, every sign-in page and every screen size. Chaosfolk
does both: users explore with their habits and faults, and each one also carries
a share of a catalog of concrete checks with test values and expected behavior.
The coordinator then proves the results with replays that need no model.

```bash
chaosfolk checks                       # the catalog
chaosfolk checks --theme security      # one theme
chaosfolk checks --kind phone          # checks for one field kind
chaosfolk checks --id phone-formats    # one check with every test value
```

## What the catalog covers

| Area | Examples |
| --- | --- |
| Field formats | first and family names in any script, emails, phone numbers, postal codes, addresses, dates of birth, date ranges, amounts, IBAN, company numbers, web addresses |
| Extreme input | empty, spaces only, very long, accents, special characters; zero, negative, decimal and announced limits |
| Form behavior | errors that keep typed data, double click, Enter, retry after an error, reload or Back halfway, cancel, delete, two tabs |
| Persistence | false success, data lost when editing another field, duplicates after a retry, views that disagree |
| Search and lists | accents and case, literal `%` and `'`, no results, quick changes, reset, filters kept after navigation, last page |
| Security (passive) | account enumeration on reset, sign-in and sign-up; throttling; password fields; secrets in URLs; sign-out; HTML-looking input shown as text; error pages; access to another account's records |
| UI and WCAG | responsive controls, overflow, keyboard reachability and focus, accessible names, contrast, target size, page structure, live regions, time limits, broken resources, JavaScript errors |
| Coordinated sessions | two users editing the same record, roles and permissions, changes made by someone else |

Each check has a theme, a scope, the field kinds or page features it applies to,
what to try, values that should be accepted or refused, the expected behavior and
how to prove it. Accessibility checks name their WCAG success criteria.

Scopes say what a check needs:

| Scope | Needs |
| --- | --- |
| `safe` | Synthetic data in any authorized test session |
| `test-account` | The email of an existing test account in `--data`; never its password |
| `two-accounts` | Two authorized test accounts; the coordinator runs it |
| `mailbox` | A test mailbox such as Mailpit; the coordinator runs it |
| `coordinated` | Several users acting on the same test object, planned by the coordinator |

## International values

Validation rules differ by country, and a product used abroad must not apply one
country's pattern to everyone. Country-dependent checks (phone numbers, postal
codes, amounts, company numbers) hold universal values plus values for France,
the United Kingdom, the United States, Canada, Germany, Spain, Italy, Belgium,
Switzerland, the Netherlands, Portugal, Ireland, Brazil, Japan and India. Their
expected behavior is the same everywhere: validation follows the selected
country, or every listed format is accepted, or the supported countries are
stated. A single national pattern applied to every user is a finding.

Pass `--countries FR,GB,US` to `draw` or `vary` to keep the universal values and
those countries only. By default every country is mixed in. On a sheet, a value
marked `(GB)` tells the user to choose that country first when the form has a
country selector. Names, addresses and free text cover Latin, Cyrillic, Arabic,
Chinese and Japanese scripts, names with one part, family names written first and
names with particles. Fictional phone numbers use the ranges that France, the
United Kingdom and the United States reserve for fiction.

## Read the page before planning

During reconnaissance, open each key page with the scout and run:

```bash
chaosfolk fields e0 --save .horde/run/fields.json
```

`fields` classifies each control from its label, attributes and type (field
labels in English, French, German, Spanish, Italian and Portuguese are
recognized), detects page features such as sign-in, password reset or lists, and
prints the checks that apply. It also reports problems visible from structure
alone: a password form sent with GET, an unmasked password field, a postal code
or phone number in `type=number`, fields without an accessible name, missing
autocomplete tokens, a too short `maxlength`, session cookies readable by
JavaScript, secrets in the query string. Confirm each one before reporting it.

`--save` adds the page to `fields.json`. `draw` then limits automatic checks to
the field kinds and features that were actually found, and `map` uses the links
recorded there to show routes nobody visited.

## Hand checks to the users

```bash
chaosfolk draw --level medium --seed 42 --objectives "Create an account;Reset a password" --themes functional,security --checks auto --countries FR,GB,DE --folder .horde/run
```

`--checks auto` (the default) uses the selected themes, or functional and ux when
no theme is given, with `safe` scope only. `--checks all` adds every scope;
`--checks reset-enumeration,phone-formats` picks checks by id; `--checks none`
keeps a pure exploration. Each user gets about one check per seven actions,
spread so the squad covers distinct checks first, with its own sample of values.
The checks use their own random stream: the same seed still draws the same users
and faults.

Every sheet also lists the variations to try when meeting a text field, a
numeric field, a submit button, a form in progress, or a search, and asks users
to confirm each success message by reloading or reopening. Users start a flag
about a check with its id, such as `[phone-formats]`, so `analyze` and the
report can link it back.

## Replay every value of a field

Exploration tries a few values. `vary` replays a recorded scenario once per
catalog value, without a model:

```bash
chaosfolk extract h02 --up-to 9 --output .horde/run/scenarios/signup.json --folder .horde/run
chaosfolk vary .horde/run/scenarios/signup.json --field "Phone" --check phone-formats --countries FR,GB,US \
  --accept '{"type": "text-visible", "text": "Account created"}' \
  --reject '{"type": "text-visible", "text": "Invalid number"}'
```

`--step N` targets a source action number instead of a label. `--values` takes
your own list, or `{"valid": [...], "invalid": [...]}`. `--persist reload` checks
each value again after a reload. Without assertions, `vary` records the final
address, the fields marked invalid and the step where a refused value blocked the
form, so you can read what happened before deciding what is a bug. Each value
that breaks its assertion is written as its own scenario: prove it with
`replay --times 3`. `--fail-on-bug` makes `vary` usable as a CI gate.

## Prove account enumeration

```bash
chaosfolk compare reset-known.json reset-unknown.json --times 3 --fail-on-bug
```

`compare` replays two scenarios in pairs and compares their final pages. Values
typed in either scenario are masked, so "sent to a@example.com" and "sent to
b@example.com" match. Add `--ignore REGEX` for dates or request numbers. With the
default `--expect same`, any other difference is a failure: three different pairs
reproduce an enumeration leak. `--expect different` checks the opposite. The
result file uses the replay format, so a finding can cite it as proof. Median
replay times are reported as a timing signal, never as proof.

## Measure UI, responsive and accessibility signals

```bash
chaosfolk audit e0 --keyboard
chaosfolk audit e0 --viewports 320x640,390x844,768x1024,1440x900 --name checkout
```

`audit` resizes the user's tab to each viewport (default 320x640, 375x812,
768x1024 and 1440x900), measures it, takes a full-page screenshot, then restores
the original size. It reports, per viewport:

- horizontal overflow and the elements causing it (WCAG 1.4.10);
- controls outside the screen, and submit buttons that cannot be reached;
- controls covered by another element, such as a sticky bar or a banner;
- clipped text in buttons, links, labels and headings;
- targets under 24 by 24 pixels that are too close to another target (WCAG 2.5.8).

And for the page: controls, images and frames without an accessible name, links
named only "click here", estimated text contrast (WCAG 1.4.3, text over images is
skipped), broken images and resources answered with 4xx or 5xx, missing language
or title, skipped heading levels, duplicate ids, positive tabindex, focusable
elements inside `aria-hidden`, blocked zoom, and clickable-looking elements that
the keyboard cannot reach.

`--keyboard` tabs from the top of the page until focus leaves it or comes back.
It lists visible controls never reached, focus landing on invisible elements,
focus without an outline or shadow, focus escaping an open modal, and focus
stuck on one element. Run it again with each dialog or menu open. JavaScript
errors raised during the audit, and those recorded before it, are reported too.

Results and screenshots are saved in `<session>/audits/`. These are measured
review signals in Chromium, not a conformance audit: confirm each one, and use a
dedicated accessibility tool and real assistive technologies for a full review.

## Systematic persistence recipes

A success message does not prove that anything was saved. Replays can verify
each scenario after a recipe, each one in its own series:

```bash
chaosfolk replay .horde/run/scenarios/save.json --times 3 --persist reload,revisit,new-tab,local-only,retry
```

| Recipe | What it does after the steps | Problem it exposes |
| --- | --- | --- |
| `reload` | Reloads the page | False success, data loss |
| `revisit` | Opens the scenario's start address again | Data loss, stale views |
| `new-tab` | Opens the current address in a new tab | Out-of-sync views and caches |
| `local-only` | Clears local and session storage, then reloads | Data kept only in the browser while the app claimed it was saved |
| `back` | Presses Back | Resubmission, half-saved states |
| `retry` | Replays the last successful step again | Duplicates after a new attempt |

Pair them with assertions on what must hold: `field-value` for the value of an
input after reload, `count` with `equals: 1` for duplicates, `text-visible` for
lists and detail pages. See the [replay guide](replay.md).
