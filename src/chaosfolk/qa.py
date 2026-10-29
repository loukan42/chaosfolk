"""Deterministic QA commands: page field analysis, data-driven variation and differential replay.

`fields` reads the structure of a user's current tab. `vary` replays one recorded
scenario once per test value typed into one field. `compare` replays two
scenarios and checks whether their outcomes are the same, which is how account
enumeration on sign-in or password reset is proven. None of them calls a model.
"""
import copy
import json
import re
import statistics
import sys
import time
from datetime import datetime
from pathlib import Path

from chaosfolk import checks as catalog
from chaosfolk import engine

OBSERVER_JS = r"""() => {
  const clip = (s, n) => (s || '').replace(/\s+/g, ' ').trim().slice(0, n);
  const name = el => clip((el.labels && el.labels[0] && el.labels[0].textContent) || el.getAttribute('aria-label')
    || el.getAttribute('placeholder') || el.name || el.id || el.tagName.toLowerCase(), 60);
  const invalid = [...document.querySelectorAll('input,select,textarea,[aria-invalid="true"]')]
    .filter(el => el.getAttribute('aria-invalid') === 'true' || (el.willValidate && !el.checkValidity()))
    .map(el => ({field: name(el), message: clip(el.validationMessage || '', 120)})).slice(0, 10);
  return {url: location.href, title: document.title, invalid,
          text: (document.body ? document.body.innerText : '').slice(0, 20000)};
}"""


def read_json_option(text, option):
    """A JSON value given inline or as the path of a JSON file."""
    text = str(text).strip()
    if text and text[0] not in "[{\"" and Path(text).is_file():
        text = Path(text).read_text(encoding="utf-8-sig")
    try:
        return json.loads(text)
    except ValueError as error:
        raise ValueError(f"{option}: unreadable JSON ({error})") from None


def command_fields(opts):
    """fields: classify the controls of a user's current tab and list the matching checks."""
    reply = engine.envoyer({"cmd": "inspect", "h": opts.humain, "js": catalog.FIELDS_JS})
    if not reply.get("ok"):
        print(reply.get("texte", ""))
        return 1
    try:
        page = json.loads(reply.get("texte") or "{}")
    except ValueError:
        print("The page structure was too large to read. Open a smaller page or a single form.")
        return 1
    analysis = catalog.analyze_page(page)
    if opts.save:
        saved = catalog.save_page(opts.save, analysis)
        print(f"Saved to {saved.as_posix()}", file=sys.stderr)
        if saved.name == "fields.json":
            from .audit_session import existing
            session = existing(saved.parent)
            if session:
                session.refresh()
                import hashlib
                payload = json.dumps(analysis, ensure_ascii=False, sort_keys=True)
                relative = "audit-evidence/fields-" + hashlib.sha256(payload.encode()).hexdigest()[:16] + ".json"
                engine.ecrire_json(session.folder / relative, analysis)
                session.measure("fields", analysis["url"], [relative])
    print(json.dumps(analysis, ensure_ascii=False, indent=2) if opts.json else catalog.page_report(analysis))
    return 0


def find_step(scenario, step=None, field=None):
    """Index of the type step to vary, by source action number or by the label of its target."""
    steps = scenario["etapes"]
    if step is not None:
        for index, item in enumerate(steps):
            if item.get("n") == step:
                break
        else:
            raise ValueError(f"No step with action number {step} in this scenario")
    else:
        wanted = catalog.normalize(field)
        matches = [index for index, item in enumerate(steps) if item["action"] == "type" and wanted in catalog.normalize(
            " ".join(str(v) for v in (item.get("cible") or {}).values() if isinstance(v, str)))]
        if not matches:
            raise ValueError(f'No type step targets a field named "{field}"')
        index = matches[-1]
    if steps[index]["action"] != "type":
        raise ValueError(f"Step {steps[index].get('n')} is a {steps[index]['action']} action, not a type action")
    return index


def value_list(opts):
    """[(value, "valid"|"invalid"|None, country)] from --check or --values."""
    if opts.check:
        return catalog.values(opts.check, selected=catalog.countries(opts.countries))
    data = read_json_option(opts.values, "--values")
    if isinstance(data, list) and all(isinstance(v, str) for v in data) and data:
        return [(v, None, None) for v in data]
    if isinstance(data, dict) and set(data) <= {"valid", "invalid"} and any(data.values()):
        result = []
        for name in ("valid", "invalid"):
            items = data.get(name) or []
            if not isinstance(items, list) or any(not isinstance(v, str) for v in items):
                raise ValueError(f"--values: {name} must be a list of strings")
            result += [(v, name, None) for v in items]
        return result
    raise ValueError('--values: expected a list of strings or {"valid": [...], "invalid": [...]}')


def series_verdict(results):
    """Verdict of one value: pass, fail, intermittent, observed (no assertion) or invalid."""
    valid = [r for r in results if r["ok"] is not None]
    if len(valid) < len(results):
        return "invalid"
    failures = sum(1 for r in valid if not r["ok"])
    return "fail" if failures == len(valid) else "intermittent" if failures else "pass"


def run_trials(opts, jobs, observer, parallel, strict=True):
    """Run (name, scenario, folder, output) jobs in one browser; returns their results in order.
    strict: a trial that leaves the recorded path is invalid. Otherwise its assertions still count and the
    blocked step is kept, since a refused value often stops the next step of the form."""
    asyncio = engine.asyncio
    from playwright.async_api import async_playwright

    async def run():
        places = asyncio.Semaphore(engine.REJEUX_SIMULTANES if parallel else 1)

        async def one(browser, name, scenario, folder, output):
            limit = max(engine.ESSAI_MAX, 12 * len(scenario["etapes"]) + 60)
            async with places:
                started = time.perf_counter()
                try:
                    result = await asyncio.wait_for(
                        engine.rejouer_un(browser, scenario, False, output, name, folder, observer=observer), limit)
                except asyncio.TimeoutError:
                    result = {"ok": None, "raisons": [], "rejeu_impossible": f"stopped after {limit} s", "capture": None}
                except Exception as error:
                    result = {"ok": None, "raisons": [], "rejeu_impossible": engine.traduire_erreur(error), "capture": None}
                result["duree_ms"] = round((time.perf_counter() - started) * 1000)
                if strict and result.get("divergence") and result["ok"] is not None:
                    step = result["divergence"]
                    result = dict(result, ok=None, rejeu_impossible=f"the replay left the recorded path at step {step['etape']} "
                                                                    f"({step['action']}: {step['message']})")
                return result

        async with async_playwright() as playwright:
            browser, _ = await engine.lancer_navigateur(playwright, opts.visible, opts.canal)
            try:
                if parallel:
                    return list(await asyncio.gather(*(one(browser, *job) for job in jobs)))
                return [await one(browser, *job) for job in jobs]
            finally:
                await browser.close()

    return run()


async def vary(opts):
    """vary: replay a scenario once per test value typed into one field, without faults."""
    file, scenario, folder = engine.charger_scenario(opts.scenario)
    index = find_step(scenario, opts.step, opts.field)
    entries = value_list(opts)
    accept = engine.valider_attendu(read_json_option(opts.accept, "--accept"), "--accept") if opts.accept else []
    reject = engine.valider_attendu(read_json_option(opts.reject, "--reject"), "--reject") if opts.reject else []
    if opts.fail_on_bug and not (accept or reject):
        print("--fail-on-bug requires --accept or --reject assertions", file=sys.stderr)
        return 2
    name = opts.nom or f"{file.stem}-vary-{opts.check or 'values'}"
    output = Path(opts.sortie or folder / "reproductions")
    output.mkdir(parents=True, exist_ok=True)
    jobs, plans = [], []
    for k, (value, kind, country) in enumerate(entries, 1):
        variant = copy.deepcopy(scenario)
        variant["etapes"][index]["args"] = dict(variant["etapes"][index].get("args") or {}, texte=value)
        variant["pannes"] = []
        variant["recette"] = opts.persist
        variant["attendu"] = accept if kind == "valid" else reject if kind == "invalid" else []
        plans.append((value, kind, country, variant))
        jobs += [(f"{name}-{k}-{i}", variant, folder, output) for i in range(1, opts.fois + 1)]
    results = await run_trials(opts, jobs, OBSERVER_JS, opts.parallel, strict=False)
    rows, failing = [], []
    for k, (value, kind, country, variant) in enumerate(plans):
        trials = results[k * opts.fois:(k + 1) * opts.fois]
        verdict = series_verdict(trials) if variant["attendu"] else (
            "invalid" if any(r["ok"] is None for r in trials) else "observed")
        last = next((r for r in reversed(trials) if r.get("observation")), {})
        seen = last.get("observation") or {}
        blocked = next((r["divergence"] for r in trials if r.get("divergence")), None)
        row = {"value": value, "class": kind, "country": country, "verdict": verdict, "url": seen.get("url"),
               "blocked_at": blocked and f"step {blocked['etape']} ({blocked['action']}: {blocked['message']})",
               "invalid_fields": seen.get("invalid") or [], "page_errors": last.get("erreurs_page") or [],
               "reasons": [r.get("raisons") or r.get("rejeu_impossible") for r in trials],
               "captures": [r.get("capture") for r in trials]}
        if verdict in ("fail", "intermittent"):
            variant_file = file.parent / f"{name}-{k + 1}.json"
            engine.ecrire_json(variant_file, dict(variant, nom=f"{name}-{k + 1}"))
            row["scenario"] = variant_file.as_posix()
            failing.append(row)
        rows.append(row)
        marks = f" invalid: {', '.join(x['field'] for x in row['invalid_fields'])}" if row["invalid_fields"] else ""
        marks += f" blocked at {row['blocked_at']}" if blocked else ""
        print(f"{verdict:<12} {kind or '-':<8} {country or '':<3} {catalog.show(value, 50):<54} {engine.urlparse(seen.get('url') or '').path or ''}{marks}")
    target = output / f"{name}.json"
    engine.ecrire_json(target, {"scenario": file.resolve().as_posix(), "nom": name, "mode": "variation",
                                "etape": scenario["etapes"][index].get("n"), "check": opts.check, "fois": opts.fois,
                                "valeurs": rows, "date": datetime.now().isoformat(timespec="seconds")})
    print(f"{len(rows)} values, {len(failing)} breaking their assertions: {target.as_posix()}")
    for row in failing:
        print(f"  prove {catalog.show(row['value'], 40)} with: chaosfolk replay {row['scenario']} --times 3")
    if not (accept or reject):
        print("No assertion given: read each outcome above (URL, invalid fields) before calling anything a bug.")
    if opts.fail_on_bug:
        if any(row["verdict"] == "invalid" for row in rows):
            return 2
        return 1 if failing else 0
    return 0


def typed_values(scenario):
    return [str((step.get("args") or {}).get("texte")) for step in scenario["etapes"]
            if step["action"] == "type" and (step.get("args") or {}).get("texte")]


def normalized(observation, masks, patterns):
    """Comparable outcome: URL and visible lines, with typed values and ignored patterns masked."""
    def clean(text):
        for value in sorted(masks, key=len, reverse=True):
            if len(value.strip()) >= 4:
                text = text.replace(value.strip(), "<typed>")
        for pattern in patterns:
            text = re.sub(pattern, "<ignored>", text)
        return re.sub(r"[ \t]+", " ", text).strip()

    lines = [clean(line) for line in (observation.get("text") or "").splitlines()]
    return clean(observation.get("url") or ""), [line for line in lines if line]


def differences(a, b):
    """Short human-readable differences between two normalized outcomes."""
    found = []
    if a[0] != b[0]:
        found.append(f"address: {a[0]}  vs  {b[0]}")
    only_a = [line for line in a[1] if line not in b[1]]
    only_b = [line for line in b[1] if line not in a[1]]
    found += [f"only in A: {line[:160]}" for line in only_a[:4]] + [f"only in B: {line[:160]}" for line in only_b[:4]]
    if not found and a[1] != b[1]:
        found.append("same lines in a different order")
    return found


async def compare(opts):
    """compare: replay two scenarios in pairs and check whether their final pages match."""
    file_a, scenario_a, folder = engine.charger_scenario(opts.scenario_a)
    file_b, scenario_b, _ = engine.charger_scenario(opts.scenario_b)
    patterns = []
    for pattern in opts.ignore:
        try:
            patterns.append(re.compile(pattern))
        except re.error as error:
            raise ValueError(f"--ignore {pattern!r}: {error}") from None
    for scenario in (scenario_a, scenario_b):
        scenario["pannes"] = []
    masks = typed_values(scenario_a) + typed_values(scenario_b)
    name = opts.nom or f"{file_a.stem}-vs-{file_b.stem}"
    output = Path(opts.sortie or folder / "reproductions")
    output.mkdir(parents=True, exist_ok=True)
    jobs = []
    for i in range(1, opts.fois + 1):
        jobs += [(f"{name}-{i}-a", scenario_a, folder, output), (f"{name}-{i}-b", scenario_b, folder, output)]
    results = await run_trials(opts, jobs, OBSERVER_JS, False)
    trials = []
    for i in range(opts.fois):
        a, b = results[2 * i], results[2 * i + 1]
        if a["ok"] is None or b["ok"] is None or not a.get("observation") or not b.get("observation"):
            reason = a.get("rejeu_impossible") or b.get("rejeu_impossible") or "no final page to compare"
            trials.append({"ok": None, "raisons": [], "rejeu_impossible": reason, "capture": a.get("capture"),
                           "capture_b": b.get("capture")})
            continue
        found = differences(normalized(a["observation"], masks, patterns), normalized(b["observation"], masks, patterns))
        broken = bool(found) if opts.attente == "same" else not found
        reasons = found if opts.attente == "same" else ["both scenarios end on the same page"] if broken else []
        trials.append({"ok": not broken, "raisons": reasons, "capture": a.get("capture"), "capture_b": b.get("capture"),
                       "duree_ms": a.get("duree_ms"), "duree_b_ms": b.get("duree_ms")})
    for i, trial in enumerate(trials, 1):
        state = ("INVALID: " + trial["rejeu_impossible"]) if trial["ok"] is None else (
            "holds" if trial["ok"] else "BROKEN: " + "; ".join(trial["raisons"]))
        print(f"{name} pair {i}/{opts.fois}: {state}")
    valid = [t for t in trials if t["ok"] is not None]
    broken = sum(1 for t in valid if not t["ok"])
    verdict = engine.verdict_rejeu(broken, len(valid), opts.fois, False)
    timing = None
    if valid:
        timing = {"a_ms": statistics.median(t["duree_ms"] for t in valid), "b_ms": statistics.median(t["duree_b_ms"] for t in valid)}
        print(f"median replay time A {timing['a_ms']} ms, B {timing['b_ms']} ms "
              "(a timing signal for the whole replay, not proof of a timing leak)")
    target = output / f"{name}.json"
    engine.ecrire_json(target, {"scenario": file_a.resolve().as_posix(), "scenario_b": file_b.resolve().as_posix(),
                                "nom": name, "mode": "traitement", "comparaison": opts.attente, "fois": len(valid),
                                "demandes": opts.fois, "casses": broken, "verdict": verdict, "essais": trials,
                                "durees_medianes": timing, "date": datetime.now().isoformat(timespec="seconds")})
    print(f"{name}: {verdict} ({broken}/{len(valid)} pairs break 'expect {opts.attente}'): {target.as_posix()}")
    if opts.fail_on_bug:
        if len(valid) < opts.fois:
            return 2
        return 1 if broken else 0
    return 0
