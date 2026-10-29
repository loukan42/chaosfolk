"""Synthetic CPU/memory comparison for campaign indexing and usage ingestion.

Run with the development environment: python scripts/benchmark_resources.py.
The baseline reconstructs the former repeated-index and whole-file algorithms.
No browser, model request, credentials or application evidence is needed.
"""
import io
import json
import statistics
import time
import tracemalloc

from chaosfolk import campaigns, usage


def measure_time(call, repeats=5):
    samples = []
    for _ in range(repeats):
        started = time.perf_counter()
        call()
        samples.append(time.perf_counter() - started)
    return statistics.median(samples)


def measure_memory(call):
    tracemalloc.start()
    try:
        result = call()
        return result, tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()


def main():
    events = [{"type": "action", "h": "h01", "n": n, "url": f"http://localhost/orders/{n}"}
              for n in range(10_000)]
    findings = [{"titre": f"[double-submit] Order {n} duplicated", "evenements": [{"h": "h01", "n": n}]}
                for n in range(200)]

    def repeated_index():
        return [campaigns.fingerprint(finding, events) for finding in findings]

    def shared_index():
        actions = campaigns.action_index(events)
        return [campaigns.fingerprint(finding, actions=actions) for finding in findings]

    assert repeated_index() == shared_index()
    before = measure_time(repeated_index)
    after = measure_time(shared_index)

    # Repeated host events represent overlapping usage exports; all must be
    # parsed, while exact duplicates must count once. The source is preallocated
    # outside tracing for both algorithms to measure ingestion allocations.
    source = "".join(json.dumps({"id": str(i % 100), "source": "host", "input_tokens": 100,
                                "output_tokens": 20, "cost": 0.002, "currency": "USD"}) + "\n"
                     for i in range(20_000))
    stream = io.StringIO(source)

    def eager():
        stream.seek(0)
        return usage.summarize([json.loads(line) for line in stream.read().splitlines() if line.strip()])

    def incremental():
        stream.seek(0)
        return usage.summarize(json.loads(line) for line in stream if line.strip())

    old_usage, old_peak = measure_memory(eager)
    new_usage, new_peak = measure_memory(incremental)
    assert old_usage == new_usage
    print(json.dumps({
        "campaign": {"events": len(events), "findings": len(findings), "repeats": 5,
                     "baseline_median_seconds": before, "indexed_median_seconds": after,
                     "speedup": before / after},
        "usage": {"lines": 20_000, "unique_events": 100, "baseline_peak_bytes": old_peak,
                  "streamed_peak_bytes": new_peak, "peak_reduction_percent": 100 * (1 - new_peak / old_peak)},
        "scope": "Synthetic function-level comparison, not end-to-end browser or model cost.",
    }, indent=2))


if __name__ == "__main__":
    main()
