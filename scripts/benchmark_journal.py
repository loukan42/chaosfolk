"""Compare journal resume memory with the previous whole-file reader.

Run: python scripts/benchmark_journal.py --events 20000 --repeat 3
Uses synthetic records in a temporary directory; never reads campaign data.
"""
import argparse
import gc
import json
from pathlib import Path
import statistics
import tempfile
import time
import tracemalloc

from chaosfolk.engine import iterer_journal, normaliser_evenement


def whole_file_reader(folder):
    events = []
    for line in (folder / "journal.jsonl").read_text(encoding="utf-8", errors="replace").splitlines():
        event = json.loads(line)
        if isinstance(event, dict) and "type" in event:
            events.append(normaliser_evenement(event))
    return events


def resume(reader, folder):
    counters = {}
    latest = 0
    for event in reader(folder):
        latest = max(latest, event["t"])
        if event["type"] == "action":
            counters[event["h"]] = max(counters.get(event["h"], 0), event["n"])
    return latest, counters


def measure(reader, folder, repeat):
    timings, peaks = [], []
    for _ in range(repeat):
        gc.collect()
        tracemalloc.start()
        started = time.perf_counter()
        result = resume(reader, folder)
        timings.append(time.perf_counter() - started)
        peaks.append(tracemalloc.get_traced_memory()[1])
        tracemalloc.stop()
    return result, {"median_seconds": round(statistics.median(timings), 4),
                    "peak_python_mib": round(max(peaks) / 1024**2, 3)}


def positive(value):
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("expected a positive integer")
    return number


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--events", type=positive, default=20000)
    parser.add_argument("--repeat", type=positive, default=3)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="chaosfolk-journal-benchmark-") as temporary:
        folder = Path(temporary)
        journal = folder / "journal.jsonl"
        with journal.open("w", encoding="utf-8") as output:
            for number in range(args.events):
                event = {"type": "action", "h": f"h{number % 12:02d}", "n": number // 12 + 1,
                         "t": number * 100, "action": "click", "ecran": ["Synthetic screen line " * 4] * 12}
                output.write(json.dumps(event) + "\n")
        before, old = measure(whole_file_reader, folder, args.repeat)
        after, new = measure(iterer_journal, folder, args.repeat)
        assert before == after, "Resume counters differ"
        print(json.dumps({"events": args.events, "repeat": args.repeat,
                          "journal_mib": round(journal.stat().st_size / 1024**2, 3),
                          "whole_file": old, "streaming": new, "same_resume_state": True}, indent=2))


if __name__ == "__main__":
    main()
