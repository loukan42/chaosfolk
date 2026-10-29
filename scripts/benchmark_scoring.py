"""Compare repeated fault-window scans with exact memory and disk indexes."""
import argparse
import gc
import json
import statistics
import time
import tracemalloc

from chaosfolk.scoring import fault_pillar, severity


def scan_faults(events, users):
    """Reconstruct the preceding streaming scan, one full journey per fault."""
    faults = {}
    for event in events:
        if event["type"] == "panne-debut":
            faults[event["id"]] = {"start": event["t"], "end": None}
        else:
            faults[event["id"]]["end"] = event["t"]
    judged = []
    for fault in faults.values():
        start, end = fault["start"], fault["end"]
        instant = end is not None and end - start < 1000
        touched = []
        for actions in users.values():
            first = last = None
            after_count, bad = 0, False
            recovered = instant or end is None
            for action in actions:
                if first is None:
                    first = action
                last = action
                if action["t"] >= start:
                    after_count += 1
                    in_window = after_count <= 10 if instant else end is None or action["t"] <= end + 30000
                    if in_window:
                        bad = bad or action["action"] == "giveup" or action["action"] == "flag" and severity(action.get("gravite")) == "blocking"
                if end is not None and action["t"] > end and action["resultat"] == "ok" and action["action"] not in ("flag", "giveup", "think", "look"):
                    recovered = True
            if first is None or last["t"] < start or end is not None and first["t"] > end or not after_count:
                continue
            recovered = recovered or (last["action"] == "done" and last["t"] > end)
            touched.append(not bad and recovered)
        if touched:
            judged.append(all(touched))
    return {"id": "faults", "value": 15 * sum(judged) / len(judged), "max": 15} if judged else None


def measure(callback, repeats):
    times = []
    for _ in range(repeats):
        gc.collect()
        start = time.perf_counter()
        result = callback()
        times.append(time.perf_counter() - start)
    tracemalloc.start()
    callback()
    peak = tracemalloc.get_traced_memory()[1]
    tracemalloc.stop()
    return result, {"median_seconds": round(statistics.median(times), 4), "python_peak_bytes": peak}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--events", type=int, default=50000)
    parser.add_argument("--faults", type=int, default=150)
    parser.add_argument("--repeat", type=int, default=3)
    args = parser.parse_args()
    if min(args.events, args.faults, args.repeat) < 1:
        parser.error("Counts must be positive")
    users = {f"h{n}": [] for n in range(4)}
    for n in range(args.events):
        users[f"h{n % 4}"].append({"t": n * 100, "action": "flag" if n % 997 == 0 else "click",
                                   "resultat": "ok", "gravite": "blocking"})
    events = []
    for n in range(args.faults):
        start = (n * args.events // args.faults) * 100
        events.append({"type": "panne-debut", "id": n, "t": start})
        if n % 3:
            events.append({"type": "panne-fin", "id": n, "t": start + (500 if n % 2 else 40000)})
    events.sort(key=lambda event: event["t"])
    expected, baseline = measure(lambda: scan_faults(events, users), args.repeat)
    results = {"baseline": baseline}
    for storage in ("memory", "disk"):
        actual, results[storage] = measure(lambda: fault_pillar(events, users, storage=storage), args.repeat)
        assert actual == expected
    print(json.dumps({"events": args.events, "faults": args.faults, "repeats": args.repeat,
                      "equivalent": True, "measurements": results,
                      "scope": "Synthetic fault scoring only. Peak Python allocations exclude input data and SQLite native pages; no browser or model calls."}, indent=2))


if __name__ == "__main__":
    main()
