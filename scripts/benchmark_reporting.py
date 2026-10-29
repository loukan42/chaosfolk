"""Measure complete report generation on synthetic local journals.

The baseline reconstructs the former eager projection and three full HTML
strings. Each variant runs in a fresh process. RSS includes SQLite's native
cache; tracemalloc reports Python allocations separately. No model or browser
requests are made, and the generated evidence is checked for equality.
"""
import argparse
from contextlib import redirect_stdout
from datetime import datetime
import gc
import io
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import threading
import time
import tracemalloc

import psutil

from chaosfolk import engine
from chaosfolk.branding import report_branding
from chaosfolk.scoring import score_report


def baseline_report(folder):
    events = engine.lire_journal(folder)
    journal, anomalies = [], {}
    for original in events:
        event = dict(original)
        if event["type"] == "action":
            for key in ("ecran", "duree_ms", "taille_reponse"):
                event.pop(key, None)
            event["cible_nom"] = (event.pop("cible", None) or {}).get("nom")
        elif event["type"] == "anomalie":
            key = (event.get("h"), event.get("genre"), event.get("message"),
                   json.dumps(event.get("induite") or []), json.dumps(event.get("apres") or []))
            if key in anomalies:
                anomalies[key]["nombre"] += 1
                continue
            event["nombre"] = 1
            anomalies[key] = event
        journal.append(event)
    config = engine.lire_json(folder / "config.json", {})
    personas = engine.lire_json(folder / "personas.json", {})
    findings = engine.lire_json(folder / "constats.json", {})
    data = {"config": config, "personas": personas, "coverage": {"requested": [], "results": []},
            "replay_matrices": [], "journal": journal, "constats": findings,
            "genere": datetime.now().isoformat(timespec="seconds"),
            "application": {"nom": None, "version": None, "url": config.get("url"), "commande": None},
            "horde": "chaosfolk", "constats_infos": engine.infos_constats(folder, findings, events, personas),
            "branding": report_branding(folder)}
    data["score"] = score_report(data)
    template = engine.MODELE_RAPPORT.read_text(encoding="utf-8")
    rendered = {}
    for language, filename in (("en", "report-en.html"), ("fr", "rapport-fr.html")):
        encoded = json.dumps(dict(data, lang=language), ensure_ascii=False).replace("<", "\\u003c").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
        html = template.replace("/*__DONNEES__*/null", encoded).replace('<html lang="en">', f'<html lang="{language}">', 1)
        rendered[language] = html
        (folder / filename).write_text(html, encoding="utf-8")
    (folder / "rapport.html").write_text(rendered["en"], encoding="utf-8")


def worker(variant, folder):
    gc.collect()
    process = psutil.Process()
    rss = [process.memory_info().rss]
    done = threading.Event()

    def sample():
        while not done.wait(0.005):
            rss.append(process.memory_info().rss)

    thread = threading.Thread(target=sample, daemon=True)
    thread.start()
    tracemalloc.start()
    started = time.perf_counter()
    try:
        with redirect_stdout(io.StringIO()):
            (baseline_report if variant == "baseline" else engine.rapport)(folder)
        elapsed = time.perf_counter() - started
        peak = tracemalloc.get_traced_memory()[1]
        rss.append(process.memory_info().rss)
    finally:
        tracemalloc.stop()
        done.set()
        thread.join()
    print(json.dumps({"seconds_with_tracing": elapsed, "python_peak_bytes": peak,
                      "rss_start_bytes": rss[0], "rss_peak_bytes": max(rss),
                      "rss_growth_bytes": max(rss) - rss[0]}))


def embedded(path):
    text = path.read_text(encoding="utf-8")
    marker = re.search(r"\bconst\s+data\s*=\s*", text)
    encoded = text[marker.end():]
    if encoded.startswith("JSON.parse("):
        value = json.loads(json.JSONDecoder().raw_decode(encoded[len("JSON.parse("):])[0])
    else:
        value = json.JSONDecoder().raw_decode(encoded)[0]
    value.pop("genere")
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--events", type=int, default=5000)
    parser.add_argument("--screen-bytes", type=int, default=4096)
    parser.add_argument("--worker", choices=("baseline", "streamed"))
    parser.add_argument("--folder", type=Path)
    args = parser.parse_args()
    if args.worker:
        worker(args.worker, args.folder)
        return
    if args.events < 1 or args.screen_bytes < 0:
        parser.error("Use a positive event count and non-negative screen size")
    with tempfile.TemporaryDirectory(prefix="chaosfolk-report-benchmark-") as temporary:
        root = Path(temporary)
        results = {}
        for variant in ("baseline", "streamed"):
            folder = root / variant
            folder.mkdir()
            engine.ecrire_json(folder / "config.json", {"url": "http://localhost/"})
            engine.ecrire_json(folder / "personas.json", {"humains": [{"id": f"h{i:02}", "appareil": "desktop"} for i in range(4)]})
            engine.ecrire_json(folder / "constats.json", {"constats": []})
            with (folder / "journal.jsonl").open("w", encoding="utf-8") as stream:
                for n in range(args.events):
                    event = {"type": "action", "h": f"h{n % 4:02}", "n": n, "t": n * 100,
                             "action": "click", "args": {"texte": "Synthetic text"}, "resultat": "ok",
                             "url": f"http://localhost/{n % 12}", "capture": f"captures/{n}.png",
                             "cible": {"nom": "Save"}, "ecran": "s" * args.screen_bytes,
                             "pense": "A synthetic reaction retained in the report."}
                    stream.write(json.dumps(event) + "\n")
            command = [sys.executable, str(Path(__file__).resolve()), "--worker", variant, "--folder", str(folder)]
            result = subprocess.run(command, capture_output=True, text=True, check=True)
            results[variant] = json.loads(result.stdout)
        progressive = False
        for name in ("report-en.html", "rapport-fr.html", "rapport.html"):
            expected, actual = embedded(root / "baseline" / name), embedded(root / "streamed" / name)
            if "journal_details" in actual:
                # Above the inline threshold the streamed report loads events from
                # assets/journal; compare the metadata and the event count only.
                progressive = True
                assert actual.pop("journal_details")["total_events"] == len(expected["journal"]) == len(actual["journal"])
                expected.pop("journal"), actual.pop("journal")
            assert expected == actual
        results["evidence_equal"] = True
        results["progressive_report"] = progressive
        results["events"] = args.events
        results["screen_bytes_per_event"] = args.screen_bytes
        results["scope"] = "Complete local report generation; synthetic evidence; no model/browser calls. RSS sampled every 5 ms."
        print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
