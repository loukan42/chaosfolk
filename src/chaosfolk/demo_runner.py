"""A reproducible local demonstration using real browser trials, with no LLM."""
import argparse
import functools
import json
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *_):
        pass


def main(argv=None):
    parser = argparse.ArgumentParser(prog="chaosfolk demo", description=__doc__)
    parser.add_argument("--output", type=Path, default=Path(".horde/demo"))
    args = parser.parse_args(argv)
    folder = args.output.resolve()
    if folder.exists() and any(folder.iterdir()):
        parser.error("Output is not empty. Choose a new --output directory to preserve previous evidence.")
    folder.mkdir(parents=True, exist_ok=True)
    from . import engine
    engine.charger_moteur()
    handler = functools.partial(QuietHandler, directory=str(Path(__file__).parent / "demo"))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_port}/"
    def write(name, data):
        engine.ecrire_json(folder / name, data)
    expectation = {"type": "js", "expression": "document.querySelector('#name').value === 'Weekend project' || document.querySelector('#status').textContent === 'Project saved'",
                   "description": "Save the project or preserve the draft when storage fails"}
    scenario = {"url": url, "session_dir": str(folder), "device": "desktop", "steps": [
        {"n": 1, "action": "type", "target": {"role": "textbox", "name": "Project name"}, "args": {"text": "Weekend project"}},
        {"n": 2, "action": "click", "target": {"role": "button", "name": "Save project"}, "args": {}}
    ], "faults": [{"type": "storage-full", "start_action": 1}], "expect": [expectation]}
    write("scenarios/before.json", scenario)
    write("scenarios/after.json", dict(scenario, url=url + "?fixed=1"))
    try:
        for name in ("before", "after"):
            result = engine.principal(["replay", str(folder / f"scenarios/{name}.json"),
                "--times", "3", "--with-control", "--name", name, "--output", str(folder / "reproductions")])
            if result:
                return result
        evidence = {name: engine.lire_json(folder / f"reproductions/{name}.json")
                    for name in ("before", "before-temoin", "after", "after-temoin")}
        for name, failures in (("before", 3), ("before-temoin", 0), ("after", 0), ("after-temoin", 0)):
            run = evidence[name]
            if run["fois"] != 3 or run["casses"] != failures:
                print(f"Demo did not produce the expected evidence: {name}. Inspect {folder}.")
                return 2
        write("config.json", {"url": url, "demo": True})
        write("personas.json", {"application": {"nom": "Fieldnotes"}, "humains": []})
        # These are replay events, not invented user thoughts or a simulated exploration.
        events = []
        for index, (name, run) in enumerate(evidence.items()):
            for attempt, trial in enumerate(run["essais"], 1):
                events.append({"type": "action", "h": name, "n": attempt,
                    "t": (index * 3 + attempt) * 1000, "action": "replay",
                    "resultat": "ok" if trial["ok"] else "echec", "args": {},
                    "message": "; ".join(trial["raisons"]),
                    "capture": Path(trial["capture"]).relative_to(folder).as_posix() if trial.get("capture") else None})
        (folder / "journal.jsonl").write_text("\n".join(json.dumps(e) for e in events) + "\n", encoding="utf-8")
        write("constats.json", {"lang": "en", "titre": "A failed save should keep your draft.", "application": "Fieldnotes",
            "translations": {"fr": {"titre": "Un échec d'enregistrement doit préserver la saisie.",
                "resume": "Douze essais réels dans le navigateur : la version initiale perd la saisie lorsque le stockage est plein ; la version corrigée la conserve. Cette démo déterministe n'utilise aucun testeur simulé.",
                "constats": [{"id": "QH-001", "titre": "Une panne de stockage efface le nom du projet non enregistré",
                    "resume": "Le formulaire vide le champ avant d'écrire dans localStorage. Une erreur de quota fait alors perdre la saisie.",
                    "condition": "Stockage plein", "correctif": {"consigne": "Vider le champ seulement après un enregistrement réussi. En cas d'échec, conserver la saisie et afficher une erreur.",
                    "attendu": "Le projet est enregistré ou la saisie d'origine reste disponible."}}]}},
            "resume": "Twelve real browser trials: the original loses a draft when storage is full; the corrected version preserves it. This deterministic demo uses no simulated users.",
            "constats": [{"id": "QH-001", "titre": "A storage failure clears the unsaved project name", "gravite": "bloquant",
                "statut": "réparé", "resume": "The original form clears its input before writing to localStorage. A quota error then loses the draft.",
                "condition": "storage-full", "preuves": {"avant": "reproductions/before.json", "temoin": "reproductions/before-temoin.json",
                "apres": "reproductions/after.json", "after_control": "reproductions/after-temoin.json"},
                "correctif": {"consigne": "Clear the field only after a successful save. On failure, keep the draft and display an error.",
                              "attendu": "The project is saved or the original draft remains available."}}]})
        engine.rapport(folder)
        print(f"Demo verified: 12/12 valid trials. Open {folder / 'rapport.html'}")
        return 0
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
