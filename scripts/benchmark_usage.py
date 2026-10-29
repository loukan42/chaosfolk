"""Compare exact usage deduplication in memory and on disk in fresh processes.

Run: python scripts/benchmark_usage.py --events 25000 --payload-bytes 2048
Reports Python allocation peaks and process peak resident memory separately.
Synthetic records only; no model request or application evidence is involved.
"""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import time
import tracemalloc


def worker(mode, count, payload_bytes):
    import psutil
    from chaosfolk import usage

    def records():
        for index in range(count):
            yield {"id": str(index), "source": "host", "input_tokens": 100, "output_tokens": 20,
                   "cost": 0.125, "currency": "USD", "metadata": f"{index}:" + "x" * payload_bytes}

    tracemalloc.start()
    started = time.perf_counter()
    result = usage.summarize(records(), max_tokens=count * 120, dedup_storage=mode)
    elapsed = time.perf_counter() - started
    peak_python = tracemalloc.get_traced_memory()[1]
    tracemalloc.stop()
    if sys.platform == "win32":
        peak_process = psutil.Process().memory_info().peak_wset
    else:
        import resource
        peak_process = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        if sys.platform != "darwin":
            peak_process *= 1024
    return {"storage": mode, "seconds": round(elapsed, 3), "python_peak_bytes": peak_python,
            "process_peak_resident_bytes": peak_process, "result": result}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--events", type=int, default=25000)
    parser.add_argument("--payload-bytes", type=int, default=2048)
    parser.add_argument("--worker", choices=("memory", "disk"))
    args = parser.parse_args()
    if args.events < 1 or args.payload_bytes < 0:
        parser.error("Use a positive event count and nonnegative payload size")
    if args.worker:
        print(json.dumps(worker(args.worker, args.events, args.payload_bytes)))
        return
    results = []
    for mode in ("memory", "disk"):
        output = subprocess.check_output([sys.executable, str(Path(__file__).resolve()), "--worker", mode,
                                          "--events", str(args.events), "--payload-bytes", str(args.payload_bytes)],
                                         text=True, timeout=180)
        results.append(json.loads(output))
    assert results[0]["result"] == results[1]["result"]
    print(json.dumps({"events": args.events, "payload_bytes": args.payload_bytes, "runs": results}, indent=2))


if __name__ == "__main__":
    main()
