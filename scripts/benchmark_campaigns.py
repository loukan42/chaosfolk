"""Measure campaign journal retention and publication allocations on synthetic data.

Run: python scripts/benchmark_campaigns.py
The baseline reconstructs the preceding eager journal and publication paths.
Times include tracemalloc instrumentation and local filesystem writes.
"""
import argparse
import gc
import json
from pathlib import Path
import tempfile
import time
import tracemalloc

from chaosfolk import campaigns


def measure(function):
    gc.collect()
    tracemalloc.start()
    started = time.perf_counter()
    result = function()
    elapsed = time.perf_counter() - started
    peak = tracemalloc.get_traced_memory()[1]
    tracemalloc.stop()
    return result, {"seconds": round(elapsed, 4), "python_peak_bytes": peak}


def preceding_publication(root, files):
    payload = {"version": 1, "files": files}
    campaigns.transaction_targets(root, payload)
    if len(json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")) > campaigns.MAX_PENDING_BYTES:
        raise ValueError("fixture too large")

    def write(path, data):
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="\n", dir=path.parent,
                                         delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(data, stream, ensure_ascii=False, indent=2)
        temporary.replace(path)

    pending = root / campaigns.PENDING_FILE
    write(pending, payload)
    recovered = json.loads(pending.read_text(encoding="utf-8"))
    for target, data in campaigns.transaction_targets(root, recovered):
        write(target, data)
    pending.unlink()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--events", type=int, default=30000)
    parser.add_argument("--payload-bytes", type=int, default=1024)
    args = parser.parse_args()
    if args.events < 100 or args.payload_bytes < 0:
        parser.error("Use at least 100 events and a nonnegative payload size")

    def events():
        for index in range(args.events):
            yield {"type": "action", "h": "h01", "n": index, "url": f"http://localhost/orders/{index}",
                   "resultat": "ok", "ecran": f"{index}:" + "x" * args.payload_bytes}

    findings = [{"titre": f"Finding {index}", "evenements": [{"h": "h01", "n": index}]} for index in range(100)]
    with tempfile.TemporaryDirectory(prefix="chaosfolk-campaign-benchmark-") as folder:
        root = Path(folder)

        def eager():
            all_events = list(events())
            actions = campaigns.action_index(all_events)
            mapping = campaigns.journey_map(root, all_events)
            return mapping, [campaigns.fingerprint(finding, actions=actions) for finding in findings]

        original = campaigns.session_events
        campaigns.session_events = lambda _: events()
        try:
            def incremental():
                actions, mapping = campaigns.session_summary(root, findings)
                return mapping, [campaigns.fingerprint(finding, actions=actions) for finding in findings]

            before, eager_stats = measure(eager)
            after, incremental_stats = measure(incremental)
            assert before == after
        finally:
            campaigns.session_events = original

        files = {"campaigns.json": {"campaigns": []}, "map.json": {"routes": {}},
                 "findings.json": {str(i): {"state": "open", "title": f"{i}:" + "x" * args.payload_bytes}
                                   for i in range(4000)}}
        old, new = root / "old", root / "new"
        old.mkdir()
        new.mkdir()
        _, old_publish = measure(lambda: preceding_publication(old, files))
        _, new_publish = measure(lambda: campaigns.publish_project(new, files))
        assert all((old / name).read_bytes() == (new / name).read_bytes() for name in files)
    print(json.dumps({"events": args.events, "event_payload_bytes": args.payload_bytes,
                      "journal": {"before": eager_stats, "after": incremental_stats},
                      "publication": {"before": old_publish, "after": new_publish}}, indent=2))


if __name__ == "__main__":
    main()
