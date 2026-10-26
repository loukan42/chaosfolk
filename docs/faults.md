# Faults

Apply faults only inside an authorized test session. `fault` and `fault-end`
require the coordinator's `CHAOSFOLK_LEADER_TOKEN`.

```bash
chaosfolk fault offline --humans h01 --after-actions 6 --duration 20
chaosfolk fault http-error --humans h02 --pattern "*/api/*" --method POST --status 503 --after-actions 5 --duration 15
chaosfolk faults
chaosfolk fault-end p1
```

Use the actual fault ID returned by the engine, not the example `p1`. `--at N`
starts after N seconds; `--after-actions N` waits for the selected user to reach N
counted actions. A duration is optional; without it the fault remains until ended,
except for instantaneous faults.

| Fault | Effect | Useful options |
| --- | --- | --- |
| `offline` | Browser context goes offline | `--duration` |
| `slow` | Delays matching requests | `--delay` in milliseconds, `--pattern` |
| `server-down` | Aborts matching app requests | `--pattern`, `--method` |
| `app-stop` | Stops/restarts the app process managed by this engine | `--at`, `--duration`; requires `--app-command` |
| `http-error` | Responds with an HTTP error status | `--status`, `--pattern`, `--method` |
| `lost-response` | Sends the request but drops its response | `--times`, `--pattern`, `--method` |
| `storage-full` | Makes localStorage writes throw a quota error | `--duration` |
| `storage-empty` | Clears browser storage | instantaneous |
| `storage-corrupt` | Replaces matching storage values with invalid data | `--key` glob |
| `clock` | Advances the page clock | `--advance 2h`; requires clock-enabled persona |
| `window` | Changes viewport dimensions | `--size 390x844` |
| `cookies-cleared` | Clears cookies in the browser context | instantaneous |

Faults operate inside the browser or the managed local process; they are not
network attacks. A lost response can still create a server-side record. Use
synthetic data and a safe backend. Killing a managed development server affects
every user testing that server.

Run `network` during reconnaissance. A static app without data requests gives
little useful evidence from API faults. For hand-authored profiles, select one
condition per user; the seeded UX catalog selects one automatically, including
the possibility of no fault.

Replays convert `app-stop` to request failure rather than killing the app for
every parallel trial. The replay guide documents the action anchors. Inspect the
recorded fault and app behavior before claiming it reproduces a real outage.
