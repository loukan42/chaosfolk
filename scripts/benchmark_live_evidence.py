"""Measure exact live evidence collection in isolated Python processes.

The baseline reconstructs the previous list/dict collections. Both modes invoke
the engine's real anomaly and request handlers and write the same journal events.
The fixture uses no browser, model, credentials or remote application.
"""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import statistics
import subprocess
import sys
import tempfile
import threading
import time
import tracemalloc
from types import SimpleNamespace

import psutil

from chaosfolk import engine


class MemoryCounter(dict):
    def increment(self, key, amount=1):
        self[key] = self.get(key, 0) + amount

    def sorted_items(self):
        yield from sorted(self.items())


def worker(mode, events, routes):
    engine.charger_moteur()
    with tempfile.TemporaryDirectory(prefix="chaosfolk-live-evidence-benchmark-") as directory:
        folder = Path(directory)
        with (folder / "journal.jsonl").open("w", encoding="utf-8") as journal:
            def record(event):
                journal.write(json.dumps(event, ensure_ascii=False) + "\n")
                journal.flush()

            context = SimpleNamespace(on=lambda *_args: None)
            world = engine.Monde("h01", context, "http://localhost", journal=record, dossier=folder)
            if mode == "memory":
                world.erreurs_page = []
                world.requetes = MemoryCounter()
                world.messages = []
            process = psutil.Process()
            initial_rss = process.memory_info().rss
            peak_rss = [initial_rss]
            stopped = threading.Event()

            def monitor():
                while not stopped.wait(0.01):
                    peak_rss[0] = max(peak_rss[0], process.memory_info().rss)

            monitor_thread = threading.Thread(target=monitor, daemon=True)
            monitor_thread.start()
            tracemalloc.start()
            started, cpu_started = time.perf_counter(), time.process_time()
            try:
                for index in range(events):
                    world._anomalie(None, "erreur-js", f"Error {index}: " + "synthetic detail " * 15)
                    world._requete(SimpleNamespace(resource_type="fetch", method="GET",
                                                   url=f"http://localhost/item-{index % routes}"))
                    world.messages.append(f"Download {index}")
                    if (index + 1) % 1000 == 0:
                        # Consume all notices, as a command response does, without retaining a second copy.
                        for _message in world.messages:
                            pass
                        world.messages.clear()
                world.evidence.flush()
                cpu_seconds = time.process_time() - cpu_started
                wall_seconds = time.perf_counter() - started
                python_peak = tracemalloc.get_traced_memory()[1]
                peak_rss[0] = max(peak_rss[0], process.memory_info().rss)
            finally:
                tracemalloc.stop()
                stopped.set()
                monitor_thread.join(timeout=5)
            errors = hashlib.sha256()
            for error in world.erreurs_page:
                errors.update((error + "\n").encode())
            requests = hashlib.sha256()
            for key, count in world.requetes.sorted_items():
                requests.update(f"{key}\t{count}\n".encode())
            result = {"mode": mode, "events": events, "routes": len(world.requetes),
                      "errors": len(world.erreurs_page), "error_digest": errors.hexdigest(),
                      "request_digest": requests.hexdigest(), "wall_seconds": wall_seconds,
                      "cpu_seconds": cpu_seconds, "peak_python_mib": python_peak / 1024**2,
                      "peak_process_rss_mib": peak_rss[0] / 1024**2,
                      "process_rss_growth_mib": (peak_rss[0] - initial_rss) / 1024**2,
                      "journal_mib": (folder / "journal.jsonl").stat().st_size / 1024**2}
            world.evidence.close()
            result["evidence_disk_mib"] = sum(path.stat().st_size for path in folder.rglob("*.sqlite")) / 1024**2
            return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--events", type=int, default=100000)
    parser.add_argument("--routes", type=int, default=20000)
    parser.add_argument("--repeat", type=int, default=3)
    parser.add_argument("--worker", choices=("memory", "spill"))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if not 1 <= args.events <= 1000000 or not 1 <= args.routes <= args.events or not 1 <= args.repeat <= 10:
        parser.error("Use 1–1000000 events, 1–events routes and 1–10 repeats")
    if args.worker:
        print(json.dumps(worker(args.worker, args.events, args.routes)))
        return
    runs = []
    for index in range(args.repeat):
        for mode in (("memory", "spill") if index % 2 == 0 else ("spill", "memory")):
            command = [sys.executable, str(Path(__file__).resolve()), "--worker", mode,
                       "--events", str(args.events), "--routes", str(args.routes)]
            completed = subprocess.run(command, check=True, capture_output=True, text=True,
                                       encoding="utf-8", timeout=180,
                                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            runs.append(json.loads(completed.stdout))
    assert len({run["error_digest"] for run in runs}) == 1, "Error values differ"
    assert len({run["request_digest"] for run in runs}) == 1, "Request counts differ"
    metrics = ("wall_seconds", "cpu_seconds", "peak_python_mib", "peak_process_rss_mib",
               "process_rss_growth_mib", "journal_mib", "evidence_disk_mib")
    medians = {mode: {metric: round(statistics.median(run[metric] for run in runs if run["mode"] == mode), 4)
                      for metric in metrics} for mode in ("memory", "spill")}
    result = {"platform": platform.platform(), "python": platform.python_version(),
              "events": args.events, "routes": args.routes, "repeats": args.repeat,
              "all_values_and_counts_equal": True, "median": medians, "runs": runs,
              "scope": "Synthetic engine event handlers and journal writes. Python/SQLite RSS and CPU; no Chromium, model or energy measurement."}
    rendered = json.dumps(result, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
