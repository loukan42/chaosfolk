"""Portable Playwright tests and deterministic CI gates for recorded scenarios."""
import argparse
import asyncio
from copy import deepcopy
import json
import math
from pathlib import Path
import re
import sys
import time
from types import SimpleNamespace
from urllib.parse import parse_qsl, urlsplit
from xml.etree import ElementTree as ET


EXPORT_ACTIONS = {
    "goto": {"url"}, "click": {"fois", "double", "droit"},
    "type": {"texte", "lent", "ajouter", "entree"}, "select": {"option"},
    "tick": {"decocher"}, "key": {"touche", "fois"}, "hover": set(),
    "scroll": {"sens"}, "back": set(), "forward": set(), "reload": set(),
    "wait": {"secondes"},
}
SECRET = re.compile(r"password|passwd|secret|token|api.?key|authorization", re.I)


def load_scenario(path):
    from . import engine
    try:
        file, scenario, folder = engine.charger_scenario(path)
    except SystemExit as error:
        raise ValueError(str(error)) from None
    if not scenario.get("attendu"):
        raise ValueError("A regression test requires at least one explicit assertion")
    return file, scenario, folder


def portable_scenario(scenario):
    """Reject unsupported semantics before writing anything; never drop a step."""
    from . import engine
    sc = deepcopy(scenario)
    if sc.get("sessions") or any(s.get("session") for s in sc["etapes"]):
        raise ValueError("Portable export does not yet support multiple sessions; use regression run")
    if any(r.get("session") for r in sc["attendu"]):
        raise ValueError("Portable export does not yet support session-scoped assertions")
    if sc.get("horloge"):
        raise ValueError("Portable export does not yet support virtual clock setup")
    if sc.get("recette") not in (None, "", *engine.RECETTES):
        raise ValueError("Unknown persistence recipe")
    if sc.get("etat") is not None and not isinstance(sc["etat"], str):
        raise ValueError("Inline browser state cannot be exported: use an external state file")
    for url in [sc["url"], sc.get("depart"), *[s.get("args", {}).get("url") for s in sc["etapes"]]]:
        if not url:
            continue
        parsed = urlsplit(url)
        if parsed.username or parsed.password or any(SECRET.search(k) for k, _ in parse_qsl(parsed.query)):
            raise ValueError("An address contains authentication data; remove it before exporting")
    for index, step in enumerate(sc["etapes"], 1):
        action = step["action"]
        if action not in EXPORT_ACTIONS:
            raise ValueError(f"Step {index}: portable export does not support {action}; use regression run")
        if step.get("echec_original"):
            raise ValueError(f"Step {index}: tolerant/failed original steps need regression run")
        args = step.get("args") or {}
        unknown = set(args) - EXPORT_ACTIONS[action] - {"ref"}
        if unknown:
            raise ValueError(f"Step {index}: unsupported arguments: {', '.join(sorted(unknown))}")
        if "fois" in args and (type(args["fois"]) is not int or not 1 <= args["fois"] <= 100):
            raise ValueError(f"Step {index}: times must be between 1 and 100")
        if "secondes" in args and (not isinstance(args["secondes"], (int, float)) or
                                  not math.isfinite(args["secondes"]) or args["secondes"] < 0):
            raise ValueError(f"Step {index}: seconds must be finite and non-negative")
        target = step.get("cible") or {}
        if action == "type" and SECRET.search(" ".join(str(target.get(k, "")) for k in ("nom", "placeholder", "testid", "css"))):
            raise ValueError(f"Step {index}: credential input must be supplied by an external authenticated state")
        if "index" in target and (type(target["index"]) is not int or target["index"] < 0):
            raise ValueError(f"Step {index}: target index must be a non-negative integer")
        if action == "scroll" and args.get("sens", "down") not in ("down", "up", "left", "right", "top", "bottom"):
            raise ValueError(f"Step {index}: unknown scroll direction")
    for fault in sc.get("pannes", []):
        if fault["type"] not in ("offline", "storage-full"):
            raise ValueError(f"Portable export does not support fault {fault['type']}; use regression run")
        if set(fault) - {"type", "id", "debut_n", "fin_n", "debut_etape", "fin_etape"}:
            raise ValueError("Portable fault export supports timing only, not extra fault parameters")
    plan, warnings = engine.planifier_pannes(sc)
    if warnings:
        raise ValueError("Resolve fault schedule warnings before exporting: " + "; ".join(warnings))
    # A single offline switch and storage prototype are scoped per context. Overlapping
    # instances would need reference counting, so reject them rather than change meaning.
    if len({f["type"] for f in plan}) != len(plan):
        raise ValueError("Repeated faults of one type need regression run")
    device = sc.get("appareil") or "desktop"
    if device not in engine.APPAREILS:
        raise ValueError(f"Unknown device: {device}")
    return {
        "url": sc["url"], "start": sc.get("depart"), "context": engine.APPAREILS[device],
        "requires_state": bool(sc.get("etat")), "steps": [
            {"action": s["action"], "args": {k: v for k, v in (s.get("args") or {}).items() if k != "ref"},
             "target": s.get("cible")} for s in sc["etapes"]],
        "faults": plan, "expect": sc["attendu"], "recipe": sc.get("recette"),
    }


# The generated test contains no Chaosfolk dependency. Keep its small runtime here
# so installed wheels can export tests without another package-data resource.
RUNTIME = r'''
import json
import os
import time
from urllib.parse import urljoin, urlsplit, urlunsplit

from playwright.sync_api import sync_playwright


def target(page, desc):
    candidates = []
    if desc.get("testid"):
        candidates.append((page.get_by_test_id(desc["testid"]), False))
    if desc.get("role") and desc["role"] != "clickable" and desc.get("nom"):
        candidates.append((page.get_by_role(desc["role"], name=desc["nom"], exact=True), True))
        candidates.append((page.get_by_role(desc["role"], name=desc["nom"]), True))
    if desc.get("placeholder"):
        candidates.append((page.get_by_placeholder(desc["placeholder"], exact=True), False))
    if desc.get("css"):
        candidates.append((page.locator(desc["css"]), False))
    if desc.get("texte"):
        candidates.append((page.get_by_text(desc["texte"], exact=True), False))
    deadline = time.monotonic() + 5
    while True:
        for locator, indexed in candidates:
            visible = locator.filter(visible=True)
            count = visible.count()
            index = desc.get("index", 0)
            if indexed and count:
                if index < count:
                    return visible.nth(index)
                break
            if count == 1:
                return visible.first
        if time.monotonic() >= deadline:
            raise RuntimeError("Target is missing or ambiguous: " + json.dumps(desc))
        page.wait_for_timeout(100)


def address(value):
    value = urljoin(SCENARIO["url"], value)
    override = os.environ.get("CHAOSFOLK_BASE_URL")
    if override and urlsplit(value).netloc == urlsplit(SCENARIO["url"]).netloc:
        old, new = urlsplit(value), urlsplit(override)
        if new.scheme not in ("http", "https") or not new.netloc:
            raise ValueError("CHAOSFOLK_BASE_URL must be an absolute HTTP(S) URL")
        value = urlunsplit((new.scheme, new.netloc, old.path, old.query, old.fragment))
    return value


def perform(page, step):
    action, args = step["action"], step["args"]
    loc = target(page, step["target"]) if step.get("target") else None
    if action == "goto":
        response = page.goto(address(args["url"]), wait_until="domcontentloaded")
        if response is not None and response.status >= 500:
            raise RuntimeError("Navigation returned HTTP " + str(response.status))
    elif action == "click":
        if args.get("double"):
            loc.dblclick(button="right" if args.get("droit") else "left")
        else:
            for _ in range(args.get("fois") or 1):
                loc.click(button="right" if args.get("droit") else "left")
    elif action == "type":
        if args.get("lent") or args.get("ajouter"):
            if not args.get("ajouter"):
                loc.fill("")
            loc.press_sequentially(args["texte"], delay=70 if args.get("lent") else 10)
        else:
            loc.fill(args["texte"])
        if args.get("entree"):
            loc.press("Enter")
    elif action == "select":
        if loc.evaluate("e => e.tagName") == "SELECT":
            loc.select_option(label=args["option"])
        else:
            loc.click()
            page.get_by_role("option", name=args["option"], exact=True).click()
    elif action == "tick":
        loc.set_checked(not args.get("decocher", False))
    elif action == "key":
        for _ in range(args.get("fois") or 1):
            for key in args["touche"].split():
                page.keyboard.press(key)
    elif action == "hover":
        loc.hover()
    elif action == "scroll":
        direction = args.get("sens", "down")
        if direction in ("top", "bottom"):
            page.keyboard.press("Home" if direction == "top" else "End")
        else:
            size = page.viewport_size or {"width": 1200, "height": 800}
            page.mouse.move(size["width"] * .6, size["height"] * .55)
            page.mouse.wheel(500 if direction == "right" else -500 if direction == "left" else 0,
                             700 if direction == "down" else -700 if direction == "up" else 0)
    elif action in ("back", "forward", "reload"):
        method = {"back": page.go_back, "forward": page.go_forward, "reload": page.reload}[action]
        method(wait_until="domcontentloaded")
    elif action == "wait":
        page.wait_for_timeout(min(args.get("secondes") or 3, 10) * 1000)
    else:
        raise ValueError("Unsupported action: " + action)
    page.wait_for_timeout(300)


def check(page, rule, errors):
    kind = rule["type"]
    if kind == "no-page-error":
        ok = not errors
    elif kind == "page-not-blank":
        ok = bool(page.locator("body").inner_text().strip())
    elif kind in ("text-visible", "text-absent", "count"):
        n = page.get_by_text(rule["texte"], exact=bool(rule.get("exact"))).filter(visible=True).count()
        ok = n > 0 if kind == "text-visible" else n == 0 if kind == "text-absent" else (
            n == rule.get("egal", n) and n >= rule.get("min", n) and n <= rule.get("max", n))
    elif kind == "storage":
        value = page.evaluate("k => localStorage.getItem(k)", rule["cle"])
        ok = value is not None and ("contient" not in rule or rule["contient"] in value)
        if rule.get("json"):
            try:
                json.loads(value or "")
            except ValueError:
                ok = False
    elif kind == "url-contains":
        ok = rule["texte"] in page.url
    elif kind == "field-value":
        locator = page.get_by_label(rule["champ"], exact=bool(rule.get("exact")))
        if not locator.count():
            locator = page.get_by_placeholder(rule["champ"], exact=bool(rule.get("exact")))
        if not locator.count():
            raise RuntimeError("Assertion field is missing: " + rule["champ"])
        value = locator.first.input_value()
        ok = value == rule["valeur"] if "valeur" in rule else rule["contient"] in value
    elif kind == "js":
        ok = bool(page.evaluate(rule["expression"]))
    else:
        raise ValueError("Unsupported assertion: " + kind)
    assert ok, "Expectation failed: " + json.dumps(rule, ensure_ascii=False)


def set_fault(context, page, fault, enabled):
    if fault["type"] == "offline":
        context.set_offline(enabled)
    elif fault["type"] == "storage-full":
        script = """(() => {
            window.__chaosfolkSetItem ||= Storage.prototype.setItem;
            Storage.prototype.setItem = function () { throw new DOMException('Storage full', 'QuotaExceededError'); };
        })()"""
        if enabled:
            fault["handle"] = context.add_init_script(script=script)
            for current in context.pages:
                current.evaluate(script)
        else:
            fault.pop("handle").dispose()
            for current in context.pages:
                current.evaluate("""() => {
                    if (window.__chaosfolkSetItem) {
                        Storage.prototype.setItem = window.__chaosfolkSetItem;
                        delete window.__chaosfolkSetItem;
                    }
                }""")
    else:
        raise ValueError("Unsupported fault")


def test_recorded_regression():
    state = os.environ.get("CHAOSFOLK_STORAGE_STATE")
    if SCENARIO["requires_state"] and not state:
        raise RuntimeError("Set CHAOSFOLK_STORAGE_STATE to an external Playwright storage-state file")
    engine = os.environ.get("CHAOSFOLK_BROWSER", "chromium")
    if engine not in ("chromium", "firefox", "webkit"):
        raise ValueError("CHAOSFOLK_BROWSER must be chromium, firefox or webkit")
    with sync_playwright() as playwright:
        browser = getattr(playwright, engine).launch()
        context = browser.new_context(**SCENARIO["context"], storage_state=state)
        context.set_default_timeout(5000)
        page = context.new_page()
        errors = []
        context.on("page", lambda new_page: new_page.on("pageerror", lambda e: errors.append(str(e))))
        page.on("pageerror", lambda e: errors.append(str(e)))
        try:
            response = page.goto(address(SCENARIO["start"] or SCENARIO["url"]), wait_until="domcontentloaded")
            if response is not None and response.status >= 400:
                raise RuntimeError("Initial page returned HTTP " + str(response.status))
            page.wait_for_timeout(300)
            for index, step in enumerate(SCENARIO["steps"], 1):
                for fault in SCENARIO["faults"]:
                    if fault["avant_etape"] == index:
                        set_fault(context, page, fault, True)
                perform(page, step)
                for fault in SCENARIO["faults"]:
                    if fault["apres_etape"] == index:
                        set_fault(context, page, fault, False)
            recipe = SCENARIO["recipe"]
            if recipe in ("reload", "back"):
                perform(page, {"action": recipe, "args": {}})
            elif recipe == "revisit":
                perform(page, {"action": "goto", "args": {"url": SCENARIO["start"] or SCENARIO["url"]}})
            elif recipe == "local-only":
                page.evaluate("() => { localStorage.clear(); sessionStorage.clear(); }")
                perform(page, {"action": "reload", "args": {}})
            elif recipe == "new-tab":
                old_url = page.url
                page = context.new_page()
                page.goto(old_url, wait_until="domcontentloaded")
                page.wait_for_timeout(300)
            elif recipe == "retry":
                perform(page, SCENARIO["steps"][-1])
            for assertion in SCENARIO["expect"]:
                check(page, assertion, errors)
        finally:
            context.close()
            browser.close()


if __name__ == "__main__":
    test_recorded_regression()
    print("Regression passed")
'''


def export_test(path, output):
    _, scenario, _ = load_scenario(path)
    portable = portable_scenario(scenario)
    if portable["recipe"] == "retry" and not portable["steps"]:
        raise ValueError("The retry recipe requires a step")
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive create avoids overwriting a user-maintained regression test.
    with output.open("x", encoding="utf-8", newline="\n") as file:
        file.write('# Portable Playwright regression. Review synthetic inputs and reset app data before each run.\n')
        file.write('# Install: python -m pip install "playwright>=1.63,<2"\n')
        file.write('# Then: python -m playwright install chromium\n')
        file.write('SCENARIO = ' + repr(portable) + '\n')
        file.write(RUNTIME)
    return output


def xml_text(value):
    return re.sub(r"[^\x09\x0a\x0d\x20-\ud7ff\ue000-\ufffd\U00010000-\U0010ffff]", "", str(value))


def write_results(output, results):
    root = ET.Element("testsuite", name="Chaosfolk regressions", tests=str(len(results)),
                      failures=str(sum(r["status"] == "failed" for r in results)),
                      errors=str(sum(r["status"] == "error" for r in results)),
                      time=f'{sum(r["seconds"] for r in results):.3f}')
    for result in results:
        case = ET.SubElement(root, "testcase", classname="chaosfolk.regression", name=xml_text(result["name"]),
                             time=f'{result["seconds"]:.3f}')
        if result["status"] != "passed":
            ET.SubElement(case, "failure" if result["status"] == "failed" else "error",
                          message=xml_text(result["message"])).text = xml_text(result["message"])
    ET.indent(root)
    ET.ElementTree(root).write(Path(output) / "junit.xml", encoding="utf-8", xml_declaration=True)
    (Path(output) / "summary.json").write_text(json.dumps({"schema_version": 1, "results": results},
                                                        ensure_ascii=False, indent=2), encoding="utf-8")


def run_suite(paths, output, times=3, channel="chromium", with_control=False):
    from . import engine
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    # Never consume stale files from an earlier run to decide a CI outcome.
    import tempfile
    run_dir = Path(tempfile.mkdtemp(prefix="run-", dir=output))
    results = []
    for index, path in enumerate(paths, 1):
        started = time.monotonic()
        name = Path(path).name
        result = {"name": name, "scenario": str(Path(path).resolve()), "status": "error", "message": ""}
        try:
            _, scenario, _ = load_scenario(path)
            # An inactive fault makes a supposed treatment meaningless.
            _, warnings = engine.planifier_pannes(scenario)
            if warnings:
                raise ValueError("Resolve fault schedule warnings: " + "; ".join(warnings))
            folder = run_dir / f"{index:03}"
            folder.mkdir()
            options = SimpleNamespace(scenario=[str(path)], nom="regression", sortie=str(folder),
                                      fois=times, temoin=False, avec_temoin=with_control,
                                      sequentiel=True, visible=False, canal=channel,
                                      persist=None, fail_on_bug=True)
            engine.charger_moteur()
            code = asyncio.run(engine.rejouer(options))
            series = [json.loads(p.read_text(encoding="utf-8")) for p in folder.glob("*.json")]
            if not series or any(s.get("demandes") != times or s.get("fois") != times for s in series):
                code = 2
            if any(0 < s.get("casses", 0) < times for s in series):
                code = 2
            result["status"] = "passed" if code == 0 else "failed" if code == 1 else "error"
            result["evidence"] = folder.relative_to(output).as_posix()
            result["message"] = "; ".join(
                trial.get("rejeu_impossible") or "; ".join(trial.get("raisons") or [])
                for s in series for trial in s.get("essais", []) if trial.get("ok") is not True)
            if code == 2 and not result["message"]:
                result["message"] = "Incomplete or invalid replay"
        except (Exception, SystemExit) as error:
            result["message"] = str(error)
        result["seconds"] = round(time.monotonic() - started, 3)
        results.append(result)
    write_results(output, results)
    return 2 if any(r["status"] == "error" for r in results) else 1 if any(r["status"] == "failed" for r in results) else 0


def positive(value):
    number = int(value)
    if not 1 <= number <= 100:
        raise argparse.ArgumentTypeError("Expected an integer from 1 to 100")
    return number


def main(argv=None):
    parser = argparse.ArgumentParser(prog="chaosfolk regression", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    export = sub.add_parser("export", help="write an independent Python Playwright test")
    export.add_argument("scenario")
    export.add_argument("--output", required=True)
    run = sub.add_parser("run", help="run deterministic scenarios and write JUnit results")
    run.add_argument("scenarios", nargs="+")
    run.add_argument("--output", required=True)
    run.add_argument("--times", type=positive, default=3)
    run.add_argument("--channel", default="chromium")
    run.add_argument("--with-control", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.command == "export":
            print(export_test(args.scenario, args.output))
            return 0
        code = run_suite(args.scenarios, args.output, args.times, args.channel, args.with_control)
        print(f"Regression results: {Path(args.output).resolve() / 'junit.xml'}")
        return code
    except (OSError, ValueError) as error:
        print(f"chaosfolk regression: {error}", file=sys.stderr)
        return 2
