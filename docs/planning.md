# Change planning, coverage and triage

These commands read local files and write reviewable JSON. They do not launch
browsers, invoke a model, change findings or publish tickets.

## Choose journeys from a change

Use the map produced by `chaosfolk map`. Add explicit file-to-route mappings
in a separate rules file:

```json
{
  "mappings": [
    {
      "paths": ["src/orders/*", "src/api/orders/*"],
      "routes": ["/orders", "/orders/:id/edit"],
      "reason": "Order editor and its API"
    },
    {
      "paths": ["src/shared/*"],
      "routes": ["/orders", "/settings"],
      "reason": "Shared application controls"
    }
  ]
}
```

```bash
chaosfolk planning changes --repo . --base main --map .horde/run/map.json --rules qa/routes.json --output .horde/change-plan.json
```

The comparison includes changes between the resolved base commit and the working
tree, including staged edits and untracked files outside `.gitignore`. Renames
keep both paths. The command does not fetch a branch or change Git state. Use a
base commit or branch that exists locally.

Patterns are case-sensitive, repository-relative strings using `*`, `?` and
`[abc]`; `*` can match across directory separators. Mappings may also live in the
map's own `mappings` array. A mapped route may be absent from the recorded map.

Every route suggestion records its source files and reason. A match on a route
name in a filename receives `low` confidence. Such a match remains an unmapped
change: the command has not proved a dependency. Unmapped changes stay in the
output and recommend a broader run. Add `--all` to include every known route.
This still cannot include routes missing from the map.

Review the suggestions before assigning test goals. A route is marked
`proposed`, never tested or covered merely because its filename matched.

## Track checks, not just page visits

Write an explicit check plan. Give different roles, states or expectations
different IDs:

```json
{
  "checks": [
    {
      "id": "save-editor-online",
      "theme": "functional",
      "route": "/orders/:id/edit",
      "role": "editor",
      "state": "online",
      "expectation": "The edited order survives reload"
    },
    {
      "id": "edit-reader",
      "theme": "security",
      "route": "/orders/:id/edit",
      "role": "reader",
      "state": "signed-in",
      "expectation": "The reader cannot change the order"
    }
  ]
}
```

Record results separately. Evidence references should point to the captured
result, screenshot, trace or assertion output used to reach the verdict:

```json
{
  "results": [
    {
      "id": "save-editor-online",
      "status": "passed",
      "evidence": ["reproductions/save-editor-online.json"]
    },
    {
      "id": "edit-reader",
      "status": "skipped",
      "reason": "No authorized reader test account was supplied"
    }
  ]
}
```

```bash
chaosfolk planning coverage --plan qa/plan.json --results .horde/run/check-results.json --output .horde/run/check-coverage.json
```

Allowed result statuses are `expected`, `not-tested`, `skipped`, `attempted`,
`passed`, `failed` and `inconclusive`. Passing and failing results require
non-empty evidence references. This command checks their presence, not the
contents of the referenced evidence; the coordinator must verify those contents.

Missing or skipped checks remain `not-tested`. Mixed pass/fail attempts become
`inconclusive`; an unfinished attempt keeps the aggregate `attempted`. Results
for unknown IDs are retained as `unplanned_results` and excluded from planned
coverage. Counts are grouped by theme, route, role and application state. They
describe the declared plan, not a percentage of the entire application.

The output is a detailed check ledger. It is separate from the report's
theme-level `coverage.json`; do not replace that file with this different schema.

## Group findings for review

```bash
chaosfolk planning triage --findings .horde/run/constats.json --output .horde/run/finding-groups.json
```

The input may be an array, an object with `constats`, or an object with
`findings`. Every finding should have a unique `id`. Candidate grouping needs:

- a `check_id`, `check`, or `[check-id]` prefix in the title;
- a `route` or `url`;
- an explicit `evidence_signature`, `error`, `assertion` or `condition`.

The title, symptom, route template, host when supplied, role, state and target
must match. Titles alone do not establish duplication. Recorded proof filenames
are retained but are not treated as equivalent symptoms. Existing findings
without these fields remain separate; the command does not invent a location
from their title.

Each group retains every original finding, its evidence and its original
status. A reproduced finding does not turn the group's other observations into
reproduced findings. A candidate group requires review and never deletes a
finding. Explicit decisions can be supplied with `--overrides`:

```json
{
  "split": ["CF-001"],
  "groups": [
    {"id": "same-save-error", "members": ["CF-002", "CF-003"]}
  ]
}
```

All commands return `0` after writing their result or `2` for invalid inputs or
execution errors. An unresolved finding does not cause a nonzero planning exit
code. Output files must differ from the input files.
