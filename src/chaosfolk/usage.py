"""Summarize host-reported model usage and gate the next batch."""
import argparse
from contextlib import contextmanager
import json
import math
from pathlib import Path
import sqlite3
import tempfile


def finite_number(value):
    if type(value) not in (int, float):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


class DiskEvents:
    """Keep complete JSON measurements on disk for exact duplicate comparisons."""
    def __init__(self, connection):
        self.connection = connection
        self.count = 0

    def get(self, identifier):
        row = self.connection.execute("SELECT payload FROM events WHERE id=?", (identifier,)).fetchone()
        return json.loads(row[0]) if row else None

    def __setitem__(self, identifier, event):
        self.connection.execute("INSERT INTO events VALUES (?, ?)",
                                (identifier, json.dumps(event, ensure_ascii=True)))
        self.count += 1

    def __len__(self):
        return self.count

    def values(self):
        for row in self.connection.execute("SELECT payload FROM events ORDER BY rowid"):
            yield json.loads(row[0])


@contextmanager
def event_store(storage):
    if storage == "memory":
        yield {}
    elif storage == "disk":
        with tempfile.TemporaryDirectory(prefix="chaosfolk-usage-") as folder:
            connection = sqlite3.connect(Path(folder) / "events.sqlite3")
            try:
                # This disposable index needs no durable journal. Keep its page
                # cache bounded; JSON payloads and identities spill to disk.
                connection.execute("PRAGMA journal_mode=OFF")
                connection.execute("PRAGMA synchronous=OFF")
                connection.execute("PRAGMA cache_size=-2048")
                connection.execute("CREATE TABLE events (id TEXT PRIMARY KEY, payload TEXT NOT NULL)")
                yield DiskEvents(connection)
            finally:
                connection.close()
    else:
        raise ValueError("dedup-storage must be memory or disk")


def summarize(events, currency="USD", max_tokens=None, max_cost=None, *, dedup_storage="memory"):
    if currency not in {"USD", "EUR", "GBP"}:
        raise ValueError("Use USD, EUR or GBP; currencies are never converted")
    if max_tokens is not None and (type(max_tokens) is not int or max_tokens < 0):
        raise ValueError("max-tokens must be a non-negative integer")
    if max_cost is not None and (not finite_number(max_cost) or max_cost < 0):
        raise ValueError("max-cost must be finite and non-negative")
    with event_store(dedup_storage) as seen:
        return _summarize(events, currency, max_tokens, max_cost, seen)


def _summarize(events, currency, max_tokens, max_cost, seen):
    tokens = cost = 0
    tokens_known = cost_known = True
    for item in events:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str) or not item["id"]:
            raise ValueError("Every usage event needs a stable string id")
        previous = seen.get(item["id"])
        if previous is not None:
            if item != previous:
                raise ValueError("Conflicting duplicate usage event")
            continue
        for field in ("input_tokens", "output_tokens"):
            n = item.get(field)
            if n is not None and (type(n) is not int or n < 0):
                raise ValueError(f"{field} must be a non-negative integer or null")
        event_cost = item.get("cost")
        if event_cost is not None:
            if not finite_number(event_cost) or event_cost < 0:
                raise ValueError("cost must be finite and non-negative")
            if item.get("currency") != currency:
                raise ValueError("Costs must use the requested currency")
        if item.get("source") != "host":
            raise ValueError("Only measured host usage is accepted; source must be host")
        seen[item["id"]] = item
        tokens_known = tokens_known and item.get("input_tokens") is not None and item.get("output_tokens") is not None
        cost_known = cost_known and event_cost is not None
        tokens += (item.get("input_tokens") or 0) + (item.get("output_tokens") or 0)
        try:
            cost += event_cost or 0
        except OverflowError:
            raise ValueError("Total cost must be finite") from None
    if not finite_number(cost):
        raise ValueError("Total cost must be finite")
    tokens_known = bool(seen) and tokens_known
    cost_known = bool(seen) and cost_known
    exhausted = (max_tokens is not None and tokens >= max_tokens) or (max_cost is not None and cost >= max_cost)
    unknown = (max_tokens is not None and not tokens_known) or (max_cost is not None and not cost_known)
    return {"events": len(seen), "tokens": tokens if tokens_known else None,
            "known_tokens": tokens, "cost": round(cost, 8) if cost_known else None,
            "known_cost": round(cost, 8), "currency": currency,
            "max_tokens": max_tokens, "max_cost": max_cost,
            "gate": "stop" if exhausted else "unknown" if unknown else "continue",
            "enforcement": "Pre-batch check of supplied host measurements. No control over active model requests."}


def main(argv=None):
    parser = argparse.ArgumentParser(prog="chaosfolk usage")
    parser.add_argument("--input", type=Path, required=True, help="host usage JSONL, one event per request")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--currency", choices=("USD", "EUR", "GBP"), default="USD")
    parser.add_argument("--max-tokens", type=int)
    parser.add_argument("--max-cost", type=float)
    parser.add_argument("--dedup-storage", choices=("memory", "disk"), default="memory",
                        help="keep exact duplicate records in memory (default) or a temporary disk index")
    args = parser.parse_args(argv)
    try:
        with args.input.open(encoding="utf-8-sig") as stream:
            events = (json.loads(line) for line in stream if line.strip())
            result = summarize(events, args.currency, args.max_tokens, args.max_cost, dedup_storage=args.dedup_storage)
        text = json.dumps(result, indent=2)
        if args.output:
            if args.output.resolve() == args.input.resolve() or (args.output.exists() and args.output.samefile(args.input)):
                raise ValueError("Output must not replace usage measurements")
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(text, encoding="utf-8")
        print(text)
        return {"continue": 0, "stop": 1, "unknown": 2}[result["gate"]]
    except (OSError, ValueError, sqlite3.Error) as error:
        print(f"usage: {error}")
        return 2
