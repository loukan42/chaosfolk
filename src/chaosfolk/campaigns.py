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
from contextlib import contextmanager
from copy import deepcopy
import errno
import hashlib
import json
import os
import re
import sqlite3
import stat
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit, urlunsplit

from chaosfolk import checks as catalog

SEVERITY = {"bloquant": 3, "blocking": 3, "genant": 2, "gênant": 2, "annoying": 2, "mineur": 1, "minor": 1}
ID_SEGMENT = re.compile(r"^(\d+|[0-9a-f]{8}-[0-9a-f-]{27,}|[0-9a-f]{16,}|[A-Za-z0-9_-]{22,})$", re.I)
PENDING_FILE = ".campaign-pending.json"
MAX_PENDING_BYTES = 64 * 1024 * 1024
MAX_PENDING_FILES = 10003


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
    from .private_state import read_json
    path = Path(path)
    return read_json(path) if path.is_file() else default


def write(path, data):
    _atomic_write(path, data)


def sync_directory(path):
    """Persist directory entries where the OS and filesystem support it."""
    if os.name == "nt":
        return  # Python exposes no portable directory fsync on Windows.
    descriptor = None
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        os.fsync(descriptor)
    except OSError as error:
        if error.errno not in {errno.EINVAL, errno.ENOTSUP, errno.EBADF}:
            raise
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _atomic_write(path, data, max_bytes=None):
    """Serialize incrementally; a failed write leaves the previous file intact."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="wb", dir=path.parent,
                                         prefix=f".{path.name}.", suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            written = 0
            for part in json.JSONEncoder(ensure_ascii=False, indent=2).iterencode(data):
                encoded = part.encode("utf-8")
                written += len(encoded)
                if max_bytes is not None and written > max_bytes:
                    raise ValueError("Campaign transaction exceeds 64 MiB")
                stream.write(encoded)
            stream.flush()
            if os.name != "nt":
                os.fchmod(stream.fileno(), _published_mode(path))
            os.fsync(stream.fileno())
        temporary.replace(path)
        sync_directory(path.parent)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _published_mode(path):
    """Temporary files are private (0600); published snapshots keep the usual permissions."""
    try:
        return stat.S_IMODE(os.stat(path).st_mode)
    except FileNotFoundError:
        mask = os.umask(0)
        os.umask(mask)
        return 0o666 & ~mask


@contextmanager
def project_lock(root):
    """Serialize project read/modify/write operations across CLI processes."""
    lock = Path(root) / ".campaign-lock.sqlite3"
    try:
        db = sqlite3.connect(lock, timeout=10)
    except sqlite3.Error as error:
        raise ValueError(f"Project folder {Path(root).as_posix()} is not writable; "
                         "campaign commands need to create its lock file") from error
    try:
        try:
            db.execute("BEGIN IMMEDIATE")
        except sqlite3.OperationalError as error:
            if "locked" in str(error) or "busy" in str(error):
                raise ValueError("Project memory is busy; retry after the current campaign update finishes") from error
            raise ValueError(f"Project lock file {lock.as_posix()} is not writable") from error
        except sqlite3.DatabaseError as error:
            raise ValueError(f"Project lock file {lock.as_posix()} is unreadable; "
                             "remove it while no campaign command is running") from error
        recover_project(root)
        yield
    finally:
        db.close()


def transaction_targets(root, payload):
    """Validate all journal destinations before publishing any snapshot."""
    if (not isinstance(payload, dict) or set(payload) != {"version", "files"}
            or type(payload["version"]) is not int or payload["version"] != 1
            or not isinstance(payload["files"], dict) or not 3 <= len(payload["files"]) <= MAX_PENDING_FILES
            or not {"campaigns.json", "findings.json", "map.json"}.issubset(payload["files"])):
        raise ValueError("Invalid pending campaign transaction")
    root = Path(root).resolve()
    targets = []
    for name, data in payload["files"].items():
        if (not isinstance(name, str) or (name not in {"campaigns.json", "findings.json", "map.json"}
                and not re.fullmatch(r"scenarios/(?:[a-f0-9]{12}|[a-f0-9]{64})\.json", name))):
            raise ValueError("Unsafe path in pending campaign transaction")
        target = root / name
        if not target.resolve().is_relative_to(root) or not isinstance(data, dict):
            raise ValueError("Unsafe destination or snapshot in pending campaign transaction")
        targets.append((target, data))
    return targets


def recover_project(root):
    """Finish an interrupted publication while holding the project lock."""
    pending = Path(root) / PENDING_FILE
    if not pending.is_file():
        return
    if pending.is_symlink() or not pending.resolve().is_relative_to(Path(root).resolve()):
        raise ValueError("Pending campaign transaction must stay inside its project")
    with pending.open("rb") as stream:
        raw = stream.read(MAX_PENDING_BYTES + 1)
    if len(raw) > MAX_PENDING_BYTES:
        raise ValueError("Pending campaign transaction exceeds 64 MiB")
    targets = transaction_targets(root, json.loads(raw))
    del raw
    _publish_targets(pending, targets)


def _publish_targets(pending, targets):
    for target, data in targets:
        write(target, data)
    pending.unlink()
    sync_directory(pending.parent)


def publish_project(root, files):
    """Stage a recoverable batch before replacing its JSON destinations."""
    payload = {"version": 1, "files": files}
    targets = transaction_targets(root, payload)
    pending = Path(root) / PENDING_FILE
    if pending.exists() or pending.is_symlink():
        raise ValueError("Recover the pending campaign transaction before publishing another")
    # Complete the bounded recovery journal before exposing any new snapshot.
    # Reuse the validated objects instead of immediately decoding a second copy.
    _atomic_write(pending, payload, max_bytes=MAX_PENDING_BYTES)
    _publish_targets(pending, targets)


def fingerprint_filename(key):
    """Explicit fingerprints are identities, not filesystem paths."""
    return key if re.fullmatch(r"[a-f0-9]{12}", key) else hashlib.sha256(key.encode("utf-8")).hexdigest()


def route(url):
    """Route template: identifiers become :id and query values are dropped, so /orders/42?tab=2 is /orders/:id?tab."""
    parts = urlsplit(url or "")
    path = "/".join(":id" if ID_SEGMENT.match(segment) else segment for segment in (parts.path or "/").split("/")) or "/"
    keys = sorted({key for key, _ in parse_qsl(parts.query, keep_blank_values=True)})
    return path + ("?" + "&".join(keys) if keys else "")


def session_events(folder):
    from chaosfolk import engine
    return engine.iterer_journal(Path(folder), obligatoire=False)


def journey_map(folder, events=None):
    """Routes and transitions of one session, from the journal and from pages saved by `fields --save`."""
    routes, edges = {}, {}
    previous = {}
    for event in session_events(folder) if events is None else events:
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
    # Keep sparse per-session contributions so rerunning map or recording the
    # same session replaces its counters. Legacy aggregates remain intact.
    contributions = total.setdefault("_campaigns", {})
    previous = contributions.get(campaign, {"routes": {}, "edges": {}})
    contribution = {"routes": {name: [node["visits"], node["failures"]] for name, node in part["routes"].items()},
                    "edges": {key: edge["count"] for key, edge in part["edges"].items()}}
    changed = contribution != previous
    for name, counts in previous["routes"].items():
        known = total["routes"].get(name)
        if known is None:
            continue  # An edited aggregate lost the route; nothing to subtract.
        known["visits"] -= counts[0]
        known["failures"] -= counts[1]
        known["campaigns"] -= bool(counts[0])
        if known.get("last_campaign") == campaign and not part["routes"].get(name, {}).get("visits"):
            known["last_campaign"] = next((key for key in reversed(contributions) if key != campaign
                and contributions[key]["routes"].get(name, [0])[0]), None)
    for key, count in previous["edges"].items():
        if key in total["edges"]:
            total["edges"][key]["count"] -= count
    for name, node in part["routes"].items():
        known = total["routes"].setdefault(name, {"visits": 0, "failures": 0, "campaigns": 0, "last_campaign": None})
        known["visits"] += node["visits"]
        known["failures"] += node["failures"]
        if node["visits"]:
            known["campaigns"] += 1
            if changed:
                known["last_campaign"] = campaign
    for key, edge in part["edges"].items():
        known = total["edges"].setdefault(key, {"from": edge["from"], "to": edge["to"], "count": 0, "via": []})
        known["count"] += edge["count"]
        known["via"] = list(dict.fromkeys(known["via"] + edge["via"]))[:8]
    total["discovered"] = sorted(set(total.get("discovered", [])) | set(part["discovered"]))
    if changed:
        contributions.pop(campaign, None)
    contributions[campaign] = contribution
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
        root = project_dir(opts.project)
        target = root / "map.json"
        with project_lock(root):
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


def action_index(events):
    return {(e.get("h"), e.get("n")): e for e in events if e.get("type") == "action"}


def session_summary(folder, findings):
    """Map the journal once, keeping only URLs used to identify findings."""
    needed = set()
    for finding in findings:
        if not isinstance(finding, dict) or finding.get("fingerprint") or finding.get("empreinte"):
            continue
        first = next((item for item in finding.get("evenements") or [] if isinstance(item, dict)), {})
        needed.add((first.get("h"), first.get("n")))
    actions = {}

    def events():
        for event in session_events(folder):
            key = (event.get("h"), event.get("n"))
            if event.get("type") == "action" and key in needed:
                actions[key] = {"url": event.get("url")}
            yield event

    return actions, journey_map(folder, events())


def fingerprint(finding, events=(), *, actions=None):
    """Stable identity of a finding across campaigns: an explicit `fingerprint`, or check id + route + title words."""
    if finding.get("fingerprint") or finding.get("empreinte"):
        return str(finding.get("fingerprint") or finding.get("empreinte"))
    if actions is None:
        actions = action_index(events)
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
    folder = Path(opts.dossier).resolve()
    config = read(folder / "config.json", {})
    project = project_name(opts.project or config.get("projet"))
    root = project_dir(project)
    with project_lock(root):
        return _record(opts, folder, config, project, root)


def _record(opts, folder, config, project, root):
    findings = read(folder / "constats.json", {}).get("constats", [])
    actions, session_map = session_summary(folder, findings)
    campaign_id = opts.label or datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    history = read(root / "campaigns.json", {"project": project, "campaigns": []})
    if any(c["id"] == campaign_id for c in history["campaigns"]):
        raise ValueError(f"Campaign {campaign_id} is already recorded for {project}")
    registry = read(root / "findings.json", {})
    entries = []
    files = {}
    for finding in findings:
        if not isinstance(finding, dict):
            continue
        key = fingerprint(finding, actions=actions)
        proofs = {name: proof_summary(folder, (value or {}).get("source") if isinstance(value, dict) else value)
                  for name, value in (finding.get("preuves") or {}).items()}
        scenario = next((p["scenario"] for p in proofs.values() if p and p.get("scenario")), None)
        kept = None
        if scenario and Path(scenario).is_file():
            filename = fingerprint_filename(key)
            kept = root / "scenarios" / f"{filename}.json"
            data = read(scenario, {})
            data.setdefault("dossier_horde", folder.as_posix())
            files[f"scenarios/{filename}.json"] = data
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
            known["assertions"] = len(data.get("attendu") or data.get("expect") or [])
    history["campaigns"].append({"id": campaign_id, "folder": folder.as_posix(), "date": datetime.now().isoformat(timespec="seconds"),
                                 "url": config.get("url"), "revision": git_revision(opts.repo or Path.cwd()),
                                 "themes": read(folder / "tirage.json", {}).get("themes"), "findings": entries,
                                 "coverage": read(folder / "coverage.json", {}).get("results", [])})
    files["campaigns.json"] = history
    files["findings.json"] = registry
    files["map.json"] = merge_map(read(root / "map.json", {"routes": {}, "edges": {}, "discovered": []}),
                                   session_map, folder.as_posix())
    publish_project(root, files)
    engine_note = "" if config.get("projet") == project else f" (launch with --project {project} to tag the session itself)"
    print(f"Recorded campaign {campaign_id} for {project}: {len(entries)} findings, "
          f"{sum(1 for e in entries if registry[e['fingerprint']]['seen'] > 1)} already seen before{engine_note}.")
    return 0


def command_compare(opts):
    """campaign compare: what is new, still there or gone between two recorded campaigns."""
    root = project_dir(opts.project)
    with project_lock(root):
        history = read(root / "campaigns.json", {}).get("campaigns", [])
        registry = read(root / "findings.json", {})
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

    scenario = deepcopy(scenario)
    scenario["url"] = move(scenario.get("url"))
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
    with project_lock(root):
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
    run = root / "replays" / datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    code = 0
    updates = {}
    for key, item in chosen:
        original = deepcopy(item)
        scenario = rebase(read(item["scenario"], {}), opts.url)
        if not (scenario.get("attendu") or scenario.get("expect")):
            print(f"{key}: skipped, its scenario has no assertion")
            continue
        filename = fingerprint_filename(key)
        path = run / "scenarios" / f"{filename}.json"
        write(path, scenario)
        args = argparse.Namespace(scenario=[str(path)], fois=opts.times, fail_on_bug=False, temoin=False, avec_temoin=False,
                                  sequentiel=True, nom=filename, sortie=str(run), visible=False, canal=None, persist=None)
        asyncio.run(engine.rejouer(args))
        result = read(run / f"{filename}.json", {})
        if result.get("fois") == opts.times and result.get("casses") == 0:
            item.update(state="fixed", fixed_in=datetime.now().isoformat(timespec="seconds"))
        elif result.get("fois") == opts.times and result.get("casses") == opts.times:
            item.update(state="open")
            code = 1
        else:
            item.setdefault("notes", []).append(f"{datetime.now():%Y-%m-%d}: replay {result.get('verdict', 'inconclusive')}")
            code = max(code, 1)
        item["last_replay"] = {"date": datetime.now().isoformat(timespec="seconds"), "verdict": result.get("verdict"),
                               "failures": result.get("casses"), "trials": result.get("fois"), "file": (run / f"{filename}.json").as_posix()}
        updates[key] = (original, item)
        print(f"{key}: {item['state']} ({result.get('casses')}/{result.get('fois')} failing)")
    with project_lock(root):
        current = read(root / "findings.json", {})
        for key, (original, updated) in updates.items():
            if current.get(key) == original:
                current[key] = updated
            else:
                # A new observation or another replay wins over stale evidence.
                print(f"{key}: project memory changed during replay; recorded state retained")
                code = max(code, 1)
        write(root / "findings.json", current)
    return code


def command_status(opts):
    """campaign status: the project's findings with their state."""
    root = project_dir(opts.project)
    with project_lock(root):
        registry = read(root / "findings.json", {})
        history = read(root / "campaigns.json", {}).get("campaigns", [])
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
