# Benchmark

The benchmark is a set of small local apps, each with one known defect and a
corrected variant (`?fixed=1`). It answers two separate questions.

```bash
chaosfolk benchmark list
```

| Case | Defect |
| --- | --- |
| `storage-draft-loss` | A storage failure clears the unsaved draft. |
| `offline-false-success` | A failed request still reports success. |
| `double-submit-duplicate` | A double click adds the same item twice. |
| `reload-loses-data` | Saved tasks disappear after a reload. |

## Does the harness reproduce known defects?

```bash
chaosfolk benchmark run --output .horde/benchmark --times 3
```

For each case, the recorded scenario is replayed on the seeded app, on its
corrected variant and, when a fault is injected, without the fault. Verdicts:

- `detected`: every seeded trial fails and every corrected trial passes;
- `missed`: the seeded app passes;
- `false-alarm`: the corrected app fails too;
- `flaky`: some trials of a series fail and others pass;
- `invalid`: incomplete trials, or the seeded app fails without its fault.

`benchmark.json` gives the counts, the recall and the time per case. The exit code
is 0 when every case is detected, 1 otherwise, 2 when a result is invalid. No
model is involved: this measures replay and fault injection, not exploration.

## Does an agent exploration find them?

Serve the seeded apps, explore them with Chaosfolk as usual, then score the
session's findings:

```bash
chaosfolk benchmark serve --port 8770
chaosfolk benchmark score --findings .horde/bench-run --usage usage.jsonl --output bench-score.json
```

A finding is matched to a case when it mentions the case route
(`/reload-loses-data/`) or one of its keywords. Matches are suggestions. A
finding with no match, or several, stays `unreviewed`, and precision is then
reported as bounds only. Record your review in a JSON object and pass it with
`--matches`:

```json
{"QH-003": "reload-loses-data", "QH-007": null}
```

`null` marks a false positive. Several findings for one case count once in the
recall and as `duplicate` rows. Use `--case` to score only the cases you
explored. With `--usage`, the host-reported tokens and cost are added (see
[integrations.md](integrations.md#usage-and-cost)).

Compare run sizes on the same cases: found defects, false positives, duration,
and tokens and cost when the host reports them. A small synthetic set does not
prove coverage of a real app; publish the cases you missed as well.

## Add a case

Add a folder under `src/chaosfolk/bench_apps/` with an `index.html` that reads
`?fixed=1`, and an entry in `cases.json` with a scenario whose assertion fails on
the seeded variant only. `benchmark run --case ID` must report `detected`.
