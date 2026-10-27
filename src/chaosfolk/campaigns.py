"""Project memory across local campaigns: journey map, finding history and scenario selection.

A project is named explicitly (`--project shop-front`), never inferred from its
address: several applications can answer on localhost:3000 at different times.
Its memory lives in <state directory>/projects/<name>/ and keeps:

- map.json: routes and transitions seen in every campaign, and links discovered
  by `fields --save` but never visited, so the next draw can aim users at them;
- campaigns.json: one entry per recorded campaign, with its findings and proofs;
- findings.json: each finding by fingerprint, with first and last campaign, how
  often it was seen, its replay scenario and an open or fixed status;
- scenarios/: copies of the proven scenarios, replayable after the session folder
  is gone, even when the app has moved to another port (`--url`).
"""
import argparse
import hashlib
import json
import re
import subprocess
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit, urlunsplit

from chaosfolk import checks as catalog

SEVERITY = {"bloquant": 3, "blocking": 3, "genant": 2, "gênant": 2, "annoying": 2, "mineur": 1, "minor": 1}
ID_SEGMENT = re.compile(r"^(\d+|[0-9a-f]{8}-[0-9a-f-]{27,}|[0-9a-f]{16,}|[A-Za-z0-9_-]{22,})$", re.I)


def home():
    from chaosfolk import engine
    return Path(engine.FICHIER_ACTIF).parent


def project_name(value):
    name = str(value or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}", name):
        raise ValueError("Project names use letters, digits, dot, dash or underscore, such as shop-front")
    return name


def project_dir(project):
    folder = home() / "projects" / project_name(project)
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def read(path, default):
    path = Path(path)
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else default


def write(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def route(url):
    """Route template: identifiers become :id and query values are dropped, so /orders/42?tab=2 is /orders/:id?tab."""
    parts = urlsplit(url or "")
    path = "/".join(":id" if ID_SEGMENT.match(segment) else segment for segment in (parts.path or "/").split("/")) or "/"
    keys = sorted({key for key, _ in parse_qsl(parts.query, keep_blank_values=True)})
    return path + ("?" + "&".join(keys) if keys else "")


def session_events(folder):
    from chaosfolk import engine
    return engine.lire_journal(Path(folder), obligatoire=False)


def journey_map(folder):
    """Routes and transitions of one session, from the journal and from pages saved by `fields --save`."""
    routes, edges = {}, {}
    previous = {}
    for event in session_events(folder):
        if event.get("type") != "action" or not event.get("url") or str(event.get("h", "")).startswith("e"):
            continue
        here = route(event["url"])
        node = routes.setdefault(here, {"visits": 0, "users": [], "failures": 0})
        node["visits"] += 1
        if event["h"] not in node["users"]:
            node["users"].append(event["h"])
        if event.get("resultat") == "echec":
            node["failures"] += 1
        before = previous.get(event["h"])
        if before and before != here:
            target = (event.get("cible") or {}).get("nom") or event.get("action")
            key = f"{before} -> {here}"
            edge = edges.setdefault(key, {"from": before, "to": here, "count": 0, "via": []})
            edge["count"] += 1
            if target and target not in edge["via"] and len(edge["via"]) < 5:
                edge["via"].append(str(target)[:60])
        previous[event["h"]] = here
    discovered = set()
    for page in read(Path(folder) / "fields.json", {}).get("pages", []):
        routes.setdefault(route(page.get("url")), {"visits": 0, "users": [], "failures": 0})
        discovered |= {route(link) for link in page.get("links") or []}
    return {"routes": routes, "edges": edges, "discovered": sorted(discovered)}


def merge_map(total, part, campaign):
    for name, node in part["routes"].items():
        known = total["routes"].setdefault(name, {"visits": 0, "failures": 0, "campaigns": 0, "last_campaign": None})
        known["visits"] += node["visits"]
        known["failures"] += node["failures"]
        if node["visits"] and known.get("last_campaign") != campaign:
            known["campaigns"] += 1
            known["last_campaign"] = campaign
    for key, edge in part["edges"].items():
        known = total["edges"].setdefault(key, {"from": edge["from"], "to": edge["to"], "count": 0, "via": []})
        known["count"] += edge["count"]
        known["via"] = list(dict.fromkeys(known["via"] + edge["via"]))[:8]
    total["discovered"] = sorted(set(total.get("discovered", [])) | set(part["discovered"]))
    return total


def unexplored(map_data, limit=12):
    """Routes worth a visit: discovered but never visited first, then the least visited, then frequent failures."""
    routes = map_data.get("routes", {})
    never = [name for name in map_data.get("discovered", []) if not routes.get(name, {}).get("visits")]
    seldom = sorted((name for name, node in routes.items() if node.get("visits")),
                    key=lambda name: (routes[name]["visits"] - 3 * routes[name].get("failures", 0), name))
    return list(dict.fromkeys(never + seldom))[:limit]


def command_map(opts):
    """map: print the journey map of a session and, with --project, merge it into the project's memory."""
    folder = Path(opts.dossier)
    part = journey_map(folder)
    write(folder / "map.json", part)
    data = part
    if opts.project:
        target = project_dir(opts.project) / "map.json"
        data = merge_map(read(target, {"routes": {}, "edges": {}, "discovered": []}), part, folder.resolve().as_posix())
        write(target, data)
    routes = data["routes"]
    print(f"{len(routes)} routes, {len(data['edges'])} transitions" + (f" (project {opts.project}, all campaigns)" if opts.project else ""))
    for name, node in sorted(routes.items(), key=lambda item: -item[1]["visits"]):
        failures = f", {node['failures']} failed actions" if node.get("failures") else ""
        print(f"  {node['visits']:>4} actions  {name}{failures}")
    repeated = sorted(data["edges"].values(), key=lambda edge: -edge["count"])[:5]
    if repeated:
        print("Most repeated transitions: " + "; ".join(f"{e['from']} -> {e['to']} x{e['count']}" for e in repeated))
    gaps = unexplored(data)
    print("Explore next: " + (", ".join(gaps) if gaps else "nothing recorded yet; run fields --save on key pages"))
    return 0


def fingerprint(finding, events):
    """Stable identity of a finding across campaigns: an explicit `fingerprint`, or check id + route + title words."""
    if finding.get("fingerprint") or finding.get("empreinte"):
        return str(finding.get("fingerprint") or finding.get("empreinte"))
    actions = {(e.get("h"), e.get("n")): e for e in events if e.get("type") == "action"}
    first = next((x for x in finding.get("evenements") or [] if isinstance(x, dict)), {})
    where = route((actions.get((first.get("h"), first.get("n"))) or {}).get("url"))
    title = str(finding.get("titre") or finding.get("title") or "")
    check = re.match(r"\s*\[([a-z0-9-]+)\]", title)
    words = " ".join(catalog.normalize(re.sub(r"^\s*\[[^\]]*\]", "", title)).split()[:8])
    basis = "|".join([check.group(1) if check else str(finding.get("condition") or ""), where, words])
    return hashlib.sha1(basis.encode("utf-8")).hexdigest()[:12]


def git_revision(folder):
    try:
        result = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=folder, capture_output=True, text=True, timeout=5)
        return result.stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def proof_summary(folder, path):
    data = read(Path(folder) / path, None) if path else None
    if not isinstance(data, dict):
        return None
    return {k: data.get(k) for k in ("nom", "mode", "fois", "demandes", "casses", "verdict", "scenario")}


def command_record(opts):
    """campaign record: store a finished session's findings and proofs in the project's memory."""
    from chaosfolk import engine
    folder = Path(opts.dossier).resolve()
    findings = read(folder / "constats.json", {}).get("constats", [])
    config = read(folder / "config.json", {})
    project = project_name(opts.project or config.get("projet"))
    root = project_dir(project)
    events = session_events(folder)
    campaign_id = opts.label or datetime.now().strftime("%Y%m%d-%H%M%S")
    history = read(root / "campaigns.json", {"project": project, "campaigns": []})
    if any(c["id"] == campaign_id for c in history["campaigns"]):
        raise ValueError(f"Campaign {campaign_id} is already recorded for {project}")
    registry = read(root / "findings.json", {})
    entries = []
    for finding in findings:
        if not isinstance(finding, dict):
            continue
        key = fingerprint(finding, events)
        proofs = {name: proof_summary(folder, (value or {}).get("source") if isinstance(value, dict) else value)
                  for name, value in (finding.get("preuves") or {}).items()}
        scenario = next((p["scenario"] for p in proofs.values() if p and p.get("scenario")), None)
        kept = None
        if scenario and Path(scenario).is_file():
            kept = root / "scenarios" / f"{key}.json"
            data = read(scenario, {})
            data.setdefault("dossier_horde", folder.as_posix())
            write(kept, data)
        status = (finding.get("statut") or "observed").lower()
        entries.append({"fingerprint": key, "id": finding.get("id"), "title": finding.get("titre"),
                        "severity": finding.get("gravite"), "status": status, "proofs": proofs})
        known = registry.setdefault(key, {"title": finding.get("titre"), "first_seen": campaign_id, "seen": 0,
                                          "campaigns": [], "state": "open"})
        known.update({"title": finding.get("titre"), "severity": finding.get("gravite"), "last_seen": campaign_id,
                      "seen": known["seen"] + 1, "state": "open"})
        known["campaigns"] = (known["campaigns"] + [campaign_id])[-10:]
        if kept:
            known["scenario"] = kept.as_posix()
            known["assertions"] = len(read(kept, {}).get("attendu") or read(kept, {}).get("expect") or [])
    history["campaigns"].append({"id": campaign_id, "folder": folder.as_posix(), "date": datetime.now().isoformat(timespec="seconds"),
                                 "url": config.get("url"), "revision": git_revision(opts.repo or Path.cwd()),
                                 "themes": read(folder / "tirage.json", {}).get("themes"), "findings": entries,
                                 "coverage": read(folder / "coverage.json", {}).get("results", [])})
    write(root / "campaigns.json", history)
    write(root / "findings.json", registry)
    write(root / "map.json", merge_map(read(root / "map.json", {"routes": {}, "edges": {}, "discovered": []}),
                                       journey_map(folder), folder.as_posix()))
    engine_note = "" if config.get("projet") == project else f" (launch with --project {project} to tag the session itself)"
    print(f"Recorded campaign {campaign_id} for {project}: {len(entries)} findings, "
          f"{sum(1 for e in entries if registry[e['fingerprint']]['seen'] > 1)} already seen before{engine_note}.")
    return 0


def command_compare(opts):
    """campaign compare: what is new, still there or gone between two recorded campaigns."""
    history = read(project_dir(opts.project) / "campaigns.json", {}).get("campaigns", [])
    if len(history) < 2 and not (opts.before and opts.after):
        print("Record at least two campaigns first.")
        return 1
    by_id = {c["id"]: c for c in history}
    before = by_id.get(opts.before) if opts.before else history[-2]
    after = by_id.get(opts.after) if opts.after else history[-1]
    if not before or not after:
        raise ValueError(f"Unknown campaign. Recorded: {', '.join(by_id)}")
    old = {f["fingerprint"]: f for f in before["findings"]}
    new = {f["fingerprint"]: f for f in after["findings"]}
    registry = read(project_dir(opts.project) / "findings.json", {})
    print(f"{opts.project}: {before['id']} ({before.get('revision') or 'no revision'}) -> {after['id']} ({after.get('revision') or 'no revision'})")
    for label, keys in (("New", new.keys() - old.keys()), ("Still present", new.keys() & old.keys()),
                        ("Not seen again", old.keys() - new.keys())):
        print(f"{label}: {len(keys)}")
        for key in sorted(keys):
            finding = new.get(key) or old.get(key)
            state = registry.get(key, {}).get("state")
            hint = ""
            if label == "Not seen again":
                hint = " fixed (replay passed)" if state == "fixed" else " not proven fixed: run campaign select --replay"
            print(f"  {key} [{finding.get('severity') or '-'}] {finding.get('title')}{hint}")
    themes = {r.get("theme"): r.get("status") for r in after.get("coverage") or []}
    previous = {r.get("theme"): r.get("status") for r in before.get("coverage") or []}
    changed = [f"{theme}: {previous.get(theme, 'none')} -> {status}" for theme, status in themes.items() if previous.get(theme) != status]
    if changed:
        print("Coverage changes: " + "; ".join(changed))
    return 0


def rebase(scenario, url):
    """Point a scenario at another origin, keeping paths: the project moved to another port or host."""
    if not url:
        return scenario
    new = urlsplit(url)
    old = urlsplit(scenario.get("url") or "")

    def move(address):
        parts = urlsplit(address or "")
        if parts.netloc != old.netloc:
            return address
        return urlunsplit((new.scheme, new.netloc, parts.path, parts.query, parts.fragment))

    scenario = dict(scenario, url=move(scenario.get("url")))
    if scenario.get("depart"):
        scenario["depart"] = move(scenario["depart"])
    for step in scenario.get("etapes") or scenario.get("steps") or []:
        args = step.get("args") or {}
        if step.get("action") == "goto" and args.get("url"):
            args["url"] = move(args["url"])
    return scenario


def selection(registry, limit):
    """Scenarios to replay: open findings first, weighted by severity, recurrence and recency; then recent fixes."""
    order = sorted({c for item in registry.values() for c in item.get("campaigns", [])})
    rank = {campaign: index for index, campaign in enumerate(order)}

    def score(item):
        recency = rank.get(item.get("last_seen"), 0) / max(len(order), 1)
        open_bonus = 10 if item.get("state") == "open" else 0
        return open_bonus + 3 * SEVERITY.get(str(item.get("severity") or "").lower(), 1) + item.get("seen", 1) + 2 * recency

    candidates = [(key, item) for key, item in registry.items() if item.get("scenario") and Path(item["scenario"]).is_file()]
    return sorted(candidates, key=lambda pair: -score(pair[1]))[:limit]


def command_select(opts):
    """campaign select: choose the scenarios worth replaying and, with --replay, run them and update each status."""
    import asyncio
    from chaosfolk import engine
    root = project_dir(opts.project)
    registry = read(root / "findings.json", {})
    chosen = selection(registry, opts.limit)
    if not chosen:
        print("No recorded finding has a replayable scenario yet.")
        return 1
    for key, item in chosen:
        print(f"  {key} [{item.get('state')}] seen {item.get('seen')}x, last {item.get('last_seen')}: {item.get('title')}")
    if not opts.replay:
        print("Add --replay to run them (three trials each) and update their status.")
        return 0
    engine.charger_moteur()
    run = root / "replays" / datetime.now().strftime("%Y%m%d-%H%M%S")
    code = 0
    for key, item in chosen:
        scenario = rebase(read(item["scenario"], {}), opts.url)
        if not (scenario.get("attendu") or scenario.get("expect")):
            print(f"{key}: skipped, its scenario has no assertion")
            continue
        path = run / "scenarios" / f"{key}.json"
        write(path, scenario)
        args = argparse.Namespace(scenario=[str(path)], fois=opts.times, fail_on_bug=False, temoin=False, avec_temoin=False,
                                  sequentiel=True, nom=key, sortie=str(run), visible=False, canal=None, persist=None)
        asyncio.run(engine.rejouer(args))
        result = read(run / f"{key}.json", {})
        if result.get("fois") == opts.times and result.get("casses") == 0:
            item.update(state="fixed", fixed_in=datetime.now().isoformat(timespec="seconds"))
        elif result.get("fois") == opts.times and result.get("casses") == opts.times:
            item.update(state="open")
            code = 1
        else:
            item.setdefault("notes", []).append(f"{datetime.now():%Y-%m-%d}: replay {result.get('verdict', 'inconclusive')}")
            code = max(code, 1)
        item["last_replay"] = {"date": datetime.now().isoformat(timespec="seconds"), "verdict": result.get("verdict"),
                               "failures": result.get("casses"), "trials": result.get("fois"), "file": (run / f"{key}.json").as_posix()}
        print(f"{key}: {item['state']} ({result.get('casses')}/{result.get('fois')} failing)")
    write(root / "findings.json", registry)
    return code


def command_status(opts):
    """campaign status: the project's findings with their state."""
    registry = read(project_dir(opts.project) / "findings.json", {})
    history = read(project_dir(opts.project) / "campaigns.json", {}).get("campaigns", [])
    print(f"{opts.project}: {len(history)} campaigns, {len(registry)} findings "
          f"({sum(1 for f in registry.values() if f.get('state') == 'open')} open)")
    for key, item in sorted(registry.items(), key=lambda pair: (pair[1].get("state") != "open", pair[1].get("last_seen") or "")):
        replay = (item.get("last_replay") or {}).get("verdict")
        print(f"  {key} {item.get('state'):<6} seen {item.get('seen')}x {item.get('first_seen')} -> {item.get('last_seen')}"
              f"{' replay ' + replay if replay else ''}: {item.get('title')}")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(prog="chaosfolk campaign", description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="action", required=True)
    p = sub.add_parser("record", help="store a finished session in the project's memory")
    p.add_argument("--folder", dest="dossier", required=True)
    p.add_argument("--project", help="explicit project name (default: the one given to launch --project)")
    p.add_argument("--label", help="campaign name (default: date and time)")
    p.add_argument("--repo", help="git repository of the tested app, to record its revision (default: current folder)")
    p.set_defaults(fn=command_record)
    p = sub.add_parser("compare", help="new, persistent and vanished findings between two campaigns")
    p.add_argument("--project", required=True)
    p.add_argument("--before")
    p.add_argument("--after")
    p.set_defaults(fn=command_compare)
    p = sub.add_parser("select", help="choose scenarios to replay; --replay runs them and updates statuses")
    p.add_argument("--project", required=True)
    p.add_argument("--limit", type=int, default=10)
    p.add_argument("--replay", action="store_true")
    p.add_argument("--times", type=int, default=3)
    p.add_argument("--url", help="new base address of the app, when it moved to another port or host")
    p.set_defaults(fn=command_select)
    p = sub.add_parser("status", help="list the project's findings and their state")
    p.add_argument("--project", required=True)
    p.set_defaults(fn=command_status)
    args = parser.parse_args(argv)
    try:
        return args.fn(args)
    except ValueError as error:
        print(f"error: {error}")
        return 1
