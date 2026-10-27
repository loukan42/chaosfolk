"""Public evaluation set: small apps with known defects, replayed without a model.

`run` checks the harness itself: every seeded defect must fail on each trial and
its corrected variant must pass. `serve` hosts the apps for an agent exploration,
and `score` compares that run's findings with the known defects.
"""
import argparse
import functools
import json
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import sys
import threading
import time

APPS = Path(__file__).parent / "bench_apps"


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *_):
        pass


def load_cases(selected=()):
    cases = json.loads((APPS / "cases.json").read_text(encoding="utf-8"))["cases"]
    known = {case["id"] for case in cases}
    unknown = [name for name in selected if name not in known]
    if unknown:
        raise ValueError(f"Unknown benchmark case: {', '.join(unknown)} (known: {', '.join(sorted(known))})")
    return [case for case in cases if not selected or case["id"] in selected]


def start_server(port=0):
    handler = functools.partial(QuietHandler, directory=str(APPS))
    server = ThreadingHTTPServer(("127.0.0.1", port), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread, f"http://127.0.0.1:{server.server_port}/"


def classify(seeded, fixed, control, times):
    """Verdict of one case from its replay series (None when a series is missing)."""
    series = [s for s in (seeded, fixed, control) if s is not None]
    if seeded is None or fixed is None or any(s.get("demandes") != times or s.get("fois") != times for s in series):
        return "invalid"
    if control is not None and control.get("casses"):
        # Without the fault the seeded app should work: otherwise the fault is not the cause.
        return "invalid"
    if 0 < seeded.get("casses", 0) < times or 0 < fixed.get("casses", 0) < times:
        return "flaky"
    if fixed.get("casses"):
        return "false-alarm"
    return "detected" if seeded.get("casses") == times else "missed"


def run(output, times=3, selected=()):
    from . import engine
    cases = load_cases(selected)
    output = Path(output).resolve()
    if output.exists() and any(output.iterdir()):
        raise ValueError("Output is not empty. Choose a new --output directory to preserve previous evidence.")
    output.mkdir(parents=True, exist_ok=True)
    engine.charger_moteur()
    server, thread, base = start_server()
    results = []
    try:
        for case in cases:
            started = time.monotonic()
            url = f"{base}{case['id']}/"
            series = {}
            for variant, address in (("seeded", url), ("fixed", url + "?fixed=1")):
                name = f"{case['id']}-{variant}"
                path = output / "scenarios" / f"{name}.json"
                engine.ecrire_json(path, dict(case["scenario"], url=address, session_dir=str(output)))
                argv = ["replay", str(path), "--times", str(times), "--name", name,
                        "--output", str(output / "reproductions")]
                if variant == "seeded" and case["scenario"].get("faults"):
                    argv.append("--with-control")
                engine.principal(argv)
                series[variant] = engine.lire_json(output / "reproductions" / f"{name}.json", None)
                if "--with-control" in argv:
                    series["control"] = engine.lire_json(output / "reproductions" / f"{name}-temoin.json", None)
            verdict = classify(series["seeded"], series["fixed"], series.get("control"), times)
            results.append({"id": case["id"], "category": case["category"], "verdict": verdict,
                            "seeded_failures": (series["seeded"] or {}).get("casses"),
                            "fixed_failures": (series["fixed"] or {}).get("casses"),
                            "control_failures": (series.get("control") or {}).get("casses"),
                            "trials": times, "seconds": round(time.monotonic() - started, 3)})
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
    count = {verdict: sum(r["verdict"] == verdict for r in results)
             for verdict in ("detected", "missed", "false-alarm", "flaky", "invalid")}
    summary = {"schema_version": 1, "kind": "harness", "cases": len(results), **count,
               "recall": round(count["detected"] / len(results), 4) if results else None,
               "seconds": round(sum(r["seconds"] for r in results), 3), "results": results,
               "scope": "Checks that seeded defects replay and corrected variants pass. "
                        "It does not measure what an agent finds while exploring: use serve and score."}
    engine.ecrire_json(output / "benchmark.json", summary)
    if count["invalid"]:
        return summary, 2
    return summary, 0 if count["detected"] == len(results) else 1


def finding_text(finding):
    return json.dumps(finding, ensure_ascii=False).casefold()


def match(finding, cases):
    """Cases a finding plausibly describes: its route, or a keyword in its title or summary."""
    text = finding_text(finding)
    prose = f"{finding.get('titre') or finding.get('title') or ''} {finding.get('resume') or finding.get('summary') or ''}".casefold()
    return [case["id"] for case in cases
            if f"/{case['id']}/" in text or any(keyword.casefold() in prose for keyword in case["keywords"])]


def score(findings_path, cases, matches=None, usage_events=None):
    findings_path = Path(findings_path)
    if findings_path.is_dir():
        findings_path = findings_path / "constats.json"
    data = json.loads(findings_path.read_text(encoding="utf-8-sig"))
    findings = data.get("constats", data.get("findings", [])) if isinstance(data, dict) else data
    if not isinstance(findings, list):
        raise ValueError("Findings must be a list or an object with constats")
    matches = matches or {}
    known = {case["id"] for case in cases}
    for key, value in matches.items():
        if value is not None and value not in known:
            raise ValueError(f"Match {key}: unknown case {value}")
    rows, found = [], {}
    for index, finding in enumerate(findings, 1):
        if not isinstance(finding, dict):
            raise ValueError(f"Finding {index} must be an object")
        key = str(finding.get("id") or index)
        if key in matches:
            # A reviewed decision always wins over the automatic suggestion.
            case, status = matches[key], "true-positive" if matches[key] else "false-positive"
        else:
            candidates = match(finding, cases)
            case, status = (candidates[0], "true-positive") if len(candidates) == 1 else (None, "unreviewed")
            if len(candidates) > 1:
                finding = dict(finding, candidates=candidates)
        if case:
            status = "duplicate" if case in found else status
            found.setdefault(case, key)
        rows.append({"finding": key, "case": case, "status": status,
                     **({"candidates": finding["candidates"]} if "candidates" in finding else {})})
    true = sum(r["status"] in ("true-positive", "duplicate") for r in rows)
    false = sum(r["status"] == "false-positive" for r in rows)
    unreviewed = sum(r["status"] == "unreviewed" for r in rows)
    total = len(rows)
    result = {"schema_version": 1, "kind": "exploration", "cases": len(cases), "found": len(found),
              "recall": round(len(found) / len(cases), 4) if cases else None,
              "findings": total, "true_positives": true, "false_positives": false, "unreviewed": unreviewed,
              "precision": round(true / (true + false), 4) if total and not unreviewed and true + false else None,
              "precision_bounds": [round(true / total, 4), round((true + unreviewed) / total, 4)] if total else None,
              "missed": sorted(known - set(found)), "rows": rows,
              "scope": "Automatic matches are suggestions. Review unreviewed findings with --matches before quoting precision."}
    if usage_events is not None:
        from .usage import summarize
        usage = summarize(usage_events)
        result["usage"] = {k: usage[k] for k in ("events", "tokens", "cost", "currency")}
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(prog="chaosfolk benchmark", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list", help="list the benchmark cases")
    r = sub.add_parser("run", help="replay every seeded defect and its corrected variant")
    r.add_argument("--output", type=Path, required=True)
    r.add_argument("--times", type=int, default=3)
    r.add_argument("--case", action="append", default=[])
    s = sub.add_parser("serve", help="host the seeded apps for an agent exploration")
    s.add_argument("--port", type=int, default=0)
    s.add_argument("--case", action="append", default=[])
    c = sub.add_parser("score", help="compare an exploration's findings with the known defects")
    c.add_argument("--findings", type=Path, required=True, help="session folder or constats.json")
    c.add_argument("--matches", type=Path, help="reviewed JSON object: finding id -> case id, or null for a false positive")
    c.add_argument("--usage", type=Path, help="host usage JSONL, as read by chaosfolk usage")
    c.add_argument("--case", action="append", default=[], help="score only these cases (the ones explored)")
    c.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "list":
            for case in load_cases():
                print(f"{case['id']:<26} {case['category']:<14} {case['title']}")
            return 0
        if args.command == "run":
            if not 1 <= args.times <= 20:
                raise ValueError("--times must be between 1 and 20")
            summary, code = run(args.output, args.times, args.case)
            for row in summary["results"]:
                print(f"{row['id']:<26} {row['verdict']:<12} seeded {row['seeded_failures']}/{row['trials']} failing, "
                      f"fixed {row['fixed_failures']}/{row['trials']} failing")
            print(f"Benchmark: {summary['detected']}/{summary['cases']} detected. Results: {args.output.resolve() / 'benchmark.json'}")
            return code
        if args.command == "serve":
            cases = load_cases(args.case)
            server, thread, base = start_server(args.port)
            print("Seeded apps (append ?fixed=1 for the corrected variant). Ctrl+C stops the server.")
            for case in cases:
                print(f"  {base}{case['id']}/")
            try:
                thread.join()
            except KeyboardInterrupt:
                return 0
            finally:
                server.shutdown()
                server.server_close()
        matches = json.loads(args.matches.read_text(encoding="utf-8")) if args.matches else None
        if matches is not None and not isinstance(matches, dict):
            raise ValueError("--matches must be a JSON object")
        events = None
        if args.usage:
            events = [json.loads(line) for line in args.usage.read_text(encoding="utf-8-sig").splitlines() if line.strip()]
        result = score(args.findings, load_cases(args.case), matches, events)
        text = json.dumps(result, ensure_ascii=False, indent=2)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(text, encoding="utf-8")
        print(text)
        return 0
    except (OSError, ValueError) as error:
        print(f"chaosfolk benchmark: {error}", file=sys.stderr)
        return 2
