"""Compare indexed replay against a direct reading of all recorded events."""
from pathlib import Path
import random

import pytest
from playwright.sync_api import sync_playwright

from chaosfolk import engine


@pytest.mark.browser
@pytest.mark.parametrize("mode", ["ordered", "unordered", "recorded", "empty"])
def test_playback_statistics_and_evidence_match_full_journal(mode):
    rng = random.Random(44)
    events = [{"h": f"h{i % 12}", "n": i, "t": 1000 + (rng.randrange(50) if mode == "unordered" else i) * 100,
               "action": rng.choice(["click", "type", "look", "think", "flag", "giveup", "done"]),
               "gravite": rng.choice(["blocking", "minor"]),
               "capture": f"shot-{i}.png" if rng.randrange(4) == 0 else None}
              for i in range(500)] if mode != "empty" else []
    findings = [{"evenements": [{"h": "h0", "n": n}, {"h": "h6", "n": n + 6}]} for n in range(0, 500, 48)]
    findings.append({"evenements": [{"h": "missing", "n": 9999}]})
    timed = mode != "recorded"
    times = [max(0, e["t"] - 1000) if timed else i * 1000 for i, e in enumerate(events)]
    queries = [-1, 0, 1, 499999, 1000, 100, 0] + [rng.randrange(500) * 1000 for _ in range(30)]
    expected = []
    for at in queries:
        shown = [e for i, e in enumerate(events) if times[i] <= at]
        seen = {(e["h"], e["n"]) for e in shown}
        users = {}
        for user in dict.fromkeys(e["h"] for e in events):
            prior = [e for e in shown if e["h"] == user]
            shots = [e for e in prior if e["capture"]]
            users[user] = {"count": len(prior), "last": prior[-1]["n"] if prior else None,
                           "shot": shots[-1]["n"] if shots else None,
                           "blocking": any(e["action"] == "flag" and e["gravite"] == "blocking" for e in prior)}
        expected.append({"count": len(shown),
                         "actions": sum(e["action"] not in {"look", "think", "flag", "giveup", "done"} for e in shown),
                         "flags": sum(e["action"] == "flag" for e in shown),
                         "finished": len({e["h"] for e in shown if e["action"] == "done"}),
                         "found": sum(any((r["h"], r["n"]) in seen for r in f["evenements"]) for f in findings),
                         "users": users})
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        try:
            page = browser.new_page()
            page.add_script_tag(content=(Path(engine.__file__).parent / "templates/playback.js").read_text(encoding="utf-8"))
            actual = page.evaluate("""({events, findings, timed, queries}) => {
                const index = buildPlaybackIndex(events, {timed, start:1000, findings,
                    validCapture: x=>Boolean(x), blocking:x=>x==='blocking'});
                return queries.map(at=>{
                    const snapshot=index.snapshot(at);
                    snapshot.users=Object.fromEntries([...snapshot.users].map(([id,u])=>[id,
                        {count:u.count,last:u.last?.n??null,shot:u.shot?.n??null,blocking:u.blocking}]));
                    return snapshot;
                });
            }""", {"events": events, "findings": findings, "timed": timed, "queries": queries})
            assert actual == expected
        finally:
            browser.close()
