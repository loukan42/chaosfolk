"""Read-only change planning, evidence-based coverage and reviewable finding groups."""
import argparse
from collections import Counter
from copy import deepcopy
from fnmatch import fnmatchcase
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

from .campaigns import route


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def git(repo, *args):
    result = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, timeout=30)
    if result.returncode:
        raise ValueError(result.stderr.decode("utf-8", errors="replace").strip() or "Git command failed")
    return result.stdout.decode("utf-8", errors="replace")


def changed_files(repo, base):
    """Compare a resolved base commit with tracked working-tree content, plus untracked files."""
    revision = git(repo, "rev-parse", "--verify", "--end-of-options", base + "^{commit}").strip()
    raw = git(repo, "diff", "--name-status", "-z", "--find-renames", revision, "--").split("\0")
    changes = []
    index = 0
    while index < len(raw) and raw[index]:
        status = raw[index]
        index += 1
        count = 2 if status.startswith(("R", "C")) else 1
        paths = raw[index:index + count]
        if len(paths) != count or any(not path for path in paths):
            raise ValueError("Unexpected git diff output")
        index += count
        changes.append({"status": status, "paths": paths})
    changes.extend({"status": "?", "paths": [path]} for path in
                   git(repo, "ls-files", "--others", "--exclude-standard", "-z").split("\0") if path)
    return revision, changes


def known_routes(data):
    if not isinstance(data, dict) or not isinstance(data.get("routes", {}), dict):
        raise ValueError("Map must be an object with a routes object")
    if any(not isinstance(key, str) or not key for key in data.get("routes", {})):
        raise ValueError("Map routes must have non-empty string names")
    discovered = data.get("discovered", [])
    if not isinstance(discovered, list) or any(not isinstance(item, str) for item in discovered):
        raise ValueError("Map discovered must be a list of route strings")
    return sorted(set(data.get("routes", {})) | set(discovered))


def mappings(data):
    entries = data.get("mappings", []) if isinstance(data, dict) else data
    if not isinstance(entries, list):
        raise ValueError("Mappings must be a list")
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("Each mapping must be an object")
        for key in ("paths", "routes"):
            values = entry.get(key)
            if not isinstance(values, list) or not values or any(not isinstance(v, str) or not v for v in values):
                raise ValueError(f"Mapping {key} must be a non-empty list of strings")
        if any(path.startswith(("/", "\\")) or ".." in path.split("/") for path in entry["paths"]):
            raise ValueError("Mapping paths must be repository-relative patterns")
    return entries


def plan_changes(repo, base, map_data, rules=None, all_routes=False):
    routes = known_routes(map_data)
    entries = mappings(rules if rules is not None else map_data)
    revision, changes = changed_files(repo, base)
    suggestions = {}
    unmapped = []
    for change in changes:
        explicit = []
        for entry in entries:
            matching = [path for path in change["paths"] if any(fnmatchcase(path, pattern) for pattern in entry["paths"])]
            if matching:
                for target in entry["routes"]:
                    explicit.append(target)
                    suggestions.setdefault(target, []).append({"files": matching, "confidence": "explicit",
                        "reason": entry.get("reason") or "Matched a user-supplied file-to-route mapping"})
        if explicit:
            continue
        # A route-name match is only a weak suggestion, never an inferred dependency graph.
        hints = []
        for target in routes:
            tokens = {part.lower() for part in re.split(r"[/?:&.\-_]", target) if len(part) >= 3 and part != "id"}
            matching = [path for path in change["paths"] if tokens & set(re.split(r"[/\.\-_]", path.lower()))]
            if matching:
                hints.append(target)
                suggestions.setdefault(target, []).append({"files": matching, "confidence": "low",
                    "reason": "A route name occurs in a changed path; dependency is unverified"})
        unmapped.append({**change, "suggested_routes": hints, "reason": "No explicit mapping covers this change"})
    if all_routes:
        for target in routes:
            suggestions.setdefault(target, []).append({"files": [], "confidence": "user-selected",
                                                       "reason": "Full known-route scope requested"})
    selected = [{"route": name, "reasons": reasons, "status": "proposed", "tested": False}
                for name, reasons in sorted(suggestions.items())]
    return {"schema_version": 1, "kind": "change-plan", "base": revision,
            "head": git(repo, "rev-parse", "HEAD").strip(), "comparison": "base-to-working-tree-including-untracked",
            "scope": "all-known-routes" if all_routes else "suggested", "changes": changes,
            "routes": selected, "unmapped_changes": unmapped, "requires_review": True,
            "full_scope_recommended": bool(unmapped),
            "note": "A suggestion is not coverage. Unmapped changes may affect routes not listed in this map."}


STATUSES = ("not-tested", "attempted", "passed", "failed", "inconclusive")


def objects(data, key):
    values = data.get(key) if isinstance(data, dict) else data
    if not isinstance(values, list) or any(not isinstance(v, dict) for v in values):
        raise ValueError(f"Expected a list of {key} objects")
    return values


def aggregate_status(results):
    observed = {entry["status"] for entry in results} - {"skipped", "not-tested", "expected"}
    if not observed:
        return "not-tested"
    if "inconclusive" in observed or {"passed", "failed"}.issubset(observed):
        return "inconclusive"
    # An unfinished attempt does not turn into a pass because another attempt passed.
    if "attempted" in observed:
        return "attempted"
    return next(iter(observed))


def coverage(plan, result_data):
    checks = objects(plan, "checks")
    results = objects(result_data, "results")
    ids = [check.get("id") for check in checks]
    if any(not isinstance(key, str) or not key.strip() for key in ids) or len(set(ids)) != len(ids):
        raise ValueError("Every planned check needs a unique non-empty string id")
    for check in checks:
        if not isinstance(check.get("expectation"), str) or not check["expectation"].strip():
            raise ValueError(f"Check {check['id']} needs an explicit expectation")
    by_id = {key: [] for key in ids}
    unplanned = []
    for original in results:
        entry = deepcopy(original)
        key = entry.get("id")
        status = entry.get("status")
        if not isinstance(key, str) or not key:
            raise ValueError("Each result needs a check id")
        if status not in (*STATUSES, "skipped", "expected"):
            raise ValueError(f"Unknown result status for {key}: {status!r}")
        if status in ("passed", "failed"):
            evidence = entry.get("evidence")
            if not isinstance(evidence, list) or not evidence or any(not isinstance(x, str) or not x.strip() for x in evidence):
                raise ValueError(f"Result {key} marked {status} needs a non-empty evidence list")
        if key in by_id:
            by_id[key].append(entry)
        else:
            unplanned.append(entry)
    items = [{**deepcopy(check), "status": aggregate_status(by_id[check["id"]]),
              "results": by_id[check["id"]]} for check in checks]
    counts = {name: sum(item["status"] == name for item in items) for name in STATUSES}
    groups = {}
    for dimension in ("theme", "route", "role", "state"):
        bucket = {}
        for item in items:
            name = str(item.get(dimension) or "unspecified")
            row = bucket.setdefault(name, {"expected": 0, **dict.fromkeys(STATUSES, 0)})
            row["expected"] += 1
            row[item["status"]] += 1
        groups[dimension] = bucket
    return {"schema_version": 1, "kind": "check-coverage", "checks": items,
            "summary": {"expected": len(items), **counts}, "groups": groups, "unplanned_results": unplanned,
            "note": "Counts describe declared checks and supplied evidence references, not whole-application coverage. Evidence content is not verified by this command."}


def normal(value):
    return " ".join(re.findall(r"\w+", str(value).casefold()))


def finding_list(data):
    if isinstance(data, dict):
        data = data.get("findings", data.get("constats"))
    return objects(data, "findings")


def candidate_basis(finding):
    """Conservative shared symptom identity; different evidence sources are not discarded."""
    title = finding.get("title", finding.get("titre", ""))
    tagged = re.match(r"\s*\[([a-z0-9-]+)\]", str(title))
    check = finding.get("check_id") or finding.get("check") or (tagged.group(1) if tagged else None)
    location = finding.get("route") or finding.get("url")
    # A title alone is insufficient: require an explicit shared expected/observed condition.
    signature = finding.get("evidence_signature") or finding.get("error") or finding.get("assertion") or finding.get("condition")
    if not (isinstance(check, str) and check.strip() and isinstance(location, str) and location.strip() and signature):
        return None
    symptom = json.dumps(signature, ensure_ascii=False, sort_keys=True) if isinstance(signature, (dict, list)) else str(signature)
    # Keep URL host (when supplied), role and app state: the same route can carry different bugs.
    from urllib.parse import urlsplit
    host = urlsplit(location).netloc
    return [check, host, route(location), normal(title), " ".join(symptom.split()),
            str(finding.get("role") or ""), str(finding.get("state") or ""),
            json.dumps(finding.get("target", finding.get("cible", {})), sort_keys=True)]


def triage(data, overrides=None):
    findings = finding_list(data)
    ids = [str(f.get("id")) if f.get("id") is not None else f"entry-{i + 1}" for i, f in enumerate(findings)]
    if len(set(ids)) != len(ids) or any(not key for key in ids):
        raise ValueError("Finding IDs must be unique; assign IDs before grouping")
    overrides = overrides or {}
    if not isinstance(overrides, dict):
        raise ValueError("Overrides must be an object")
    split = overrides.get("split", [])
    manual = overrides.get("groups", [])
    if not isinstance(split, list) or any(key not in ids for key in split):
        raise ValueError("Split entries must name existing finding IDs")
    if not isinstance(manual, list):
        raise ValueError("Override groups must be a list")
    assigned = {}
    group_ids = set()
    for group in manual:
        if not isinstance(group, dict) or not isinstance(group.get("id"), str) or not group["id"]:
            raise ValueError("Each override group needs a non-empty id")
        if group["id"] in group_ids:
            raise ValueError("Override group ids must be unique")
        group_ids.add(group["id"])
        members = group.get("members")
        if not isinstance(members, list) or len(members) < 2:
            raise ValueError("An override group needs at least two member IDs")
        for member in members:
            if member not in ids or member in assigned or member in split:
                raise ValueError(f"Unknown, repeated or split group member: {member}")
            assigned[member] = group["id"]
    buckets = {}
    for key, finding in zip(ids, findings):
        basis = candidate_basis(finding)
        mode = "candidate"
        if key in assigned:
            identity = "manual:" + assigned[key]
            mode = "manual"
        elif key in split or basis is None:
            identity = "single:" + key
            mode = "separate"
        else:
            identity = "candidate:" + hashlib.sha256(json.dumps(basis, ensure_ascii=False).encode()).hexdigest()[:16]
        bucket = buckets.setdefault(identity, {"id": identity, "grouping": mode, "members": [],
            "reason": "User override" if mode == "manual" else "Matching check, route and symptom; review required" if mode == "candidate" else "Insufficient shared evidence or explicitly split"})
        bucket["members"].append({"entry_id": key, "finding": deepcopy(finding)})
    groups = list(buckets.values())
    for group in groups:
        group["occurrence_count"] = len(group["members"])
        group["statuses"] = dict(Counter(str(m["finding"].get("status", m["finding"].get("statut", "unspecified"))) for m in group["members"]))
        group["requires_review"] = group["grouping"] == "candidate" and len(group["members"]) > 1
    return {"schema_version": 1, "kind": "finding-groups", "finding_count": len(findings),
            "groups": groups, "note": "Groups are triage suggestions. Original findings, statuses and evidence are retained; no finding is promoted or deleted."}


def main(argv=None):
    parser = argparse.ArgumentParser(prog="chaosfolk planning", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    changes = sub.add_parser("changes", help="Suggest routes to inspect from a git diff")
    changes.add_argument("--repo", required=True)
    changes.add_argument("--base", required=True)
    changes.add_argument("--map", required=True)
    changes.add_argument("--rules", help="JSON file with explicit file-to-route mappings")
    changes.add_argument("--all", action="store_true", help="Include every known route")
    checks = sub.add_parser("coverage", help="Aggregate declared checks and recorded results")
    checks.add_argument("--plan", required=True)
    checks.add_argument("--results", required=True)
    groups = sub.add_parser("triage", help="Suggest finding groups without modifying their status")
    groups.add_argument("--findings", required=True)
    groups.add_argument("--overrides", help="Explicit split and group choices")
    for child in (changes, checks, groups):
        child.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    try:
        inputs = [getattr(args, name, None) for name in ("map", "rules", "plan", "results", "findings", "overrides")]
        if any(Path(value).resolve() == Path(args.output).resolve() for value in inputs if value):
            raise ValueError("Output must differ from input files")
        if args.command == "changes":
            value = plan_changes(args.repo, args.base, read_json(args.map), read_json(args.rules) if args.rules else None, args.all)
        elif args.command == "coverage":
            value = coverage(read_json(args.plan), read_json(args.results))
        else:
            value = triage(read_json(args.findings), read_json(args.overrides) if args.overrides else None)
        write_json(args.output, value)
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print(f"chaosfolk planning: {error}", file=sys.stderr)
        return 2
    print(f"Wrote {value['kind']}: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
