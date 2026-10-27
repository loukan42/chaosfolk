"""Summarize host-reported model usage and gate the next batch."""
import argparse
import json
import math
from pathlib import Path


def summarize(events, currency="USD", max_tokens=None, max_cost=None):
    if currency not in {"USD", "EUR", "GBP"}:
        raise ValueError("Use USD, EUR or GBP; currencies are never converted")
    if max_tokens is not None and (type(max_tokens) is not int or max_tokens < 0):
        raise ValueError("max-tokens must be a non-negative integer")
    if max_cost is not None and (not math.isfinite(max_cost) or max_cost < 0):
        raise ValueError("max-cost must be finite and non-negative")
    seen, unique = {}, []
    for item in events:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str) or not item["id"]:
            raise ValueError("Every usage event needs a stable string id")
        if item["id"] in seen:
            if item != seen[item["id"]]:
                raise ValueError("Conflicting duplicate usage event")
            continue
        for field in ("input_tokens", "output_tokens"):
            n = item.get(field)
            if n is not None and (type(n) is not int or n < 0):
                raise ValueError(f"{field} must be a non-negative integer or null")
        cost = item.get("cost")
        if cost is not None:
            if type(cost) not in (int, float) or not math.isfinite(cost) or cost < 0:
                raise ValueError("cost must be finite and non-negative")
            if item.get("currency") != currency:
                raise ValueError("Costs must use the requested currency")
        if item.get("source") != "host":
            raise ValueError("Only measured host usage is accepted; source must be host")
        seen[item["id"]] = item
        unique.append(item)
    tokens_known = bool(unique) and all(x.get("input_tokens") is not None and x.get("output_tokens") is not None for x in unique)
    cost_known = bool(unique) and all(x.get("cost") is not None for x in unique)
    tokens = sum(x.get("input_tokens", 0) or 0 for x in unique) + sum(x.get("output_tokens", 0) or 0 for x in unique)
    cost = sum(x.get("cost", 0) or 0 for x in unique)
    exhausted = (max_tokens is not None and tokens >= max_tokens) or (max_cost is not None and cost >= max_cost)
    unknown = (max_tokens is not None and not tokens_known) or (max_cost is not None and not cost_known)
    return {"events": len(unique), "tokens": tokens if tokens_known else None,
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
    args = parser.parse_args(argv)
    try:
        events = [json.loads(line) for line in args.input.read_text(encoding="utf-8-sig").splitlines() if line.strip()]
        result = summarize(events, args.currency, args.max_tokens, args.max_cost)
        text = json.dumps(result, indent=2)
        if args.output:
            if args.output.resolve() == args.input.resolve():
                raise ValueError("Output must not replace usage measurements")
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(text, encoding="utf-8")
        print(text)
        return {"continue": 0, "stop": 1, "unknown": 2}[result["gate"]]
    except (OSError, ValueError) as error:
        print(f"usage: {error}")
        return 2
