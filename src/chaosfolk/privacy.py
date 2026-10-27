"""Capture masks and reviewable, sanitized copies of report evidence."""
import argparse
import json
import os
import re
import shutil
from pathlib import Path

MASKS = ['input[type="password"]', '[autocomplete^="cc-"]',
         '[autocomplete="one-time-code"]', '[data-chaosfolk-private]']
SECRET = re.compile(r"password|passwd|secret|authorization|cookie|token|api.?key|jeton", re.I)
EMAIL = re.compile(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}")
URL_SECRET = re.compile(r"([?&](?:token|access_token|password|secret|api_key|email)=)[^&#\s]+", re.I)
BEARER = re.compile(r"(?i)Bearer\s+[A-Za-z0-9._~+/-]+=*")


def screenshot_masks(page, extra=()):
    configured = json.loads(os.environ.get("CHAOSFOLK_MASK_SELECTORS", "[]"))
    if not isinstance(configured, list) or any(not isinstance(x, str) or not x for x in configured):
        raise ValueError("CHAOSFOLK_MASK_SELECTORS must be a JSON list of CSS selectors")
    # Frame locators also cover passwords in embedded sign-in forms.
    return [frame.locator(selector) for frame in page.frames for selector in (*MASKS, *configured, *extra)]


def sanitize(value, literals=()):
    if isinstance(value, dict):
        return {key: "[redacted]" if SECRET.search(key) else sanitize(item, literals)
                for key, item in value.items()
                if key not in {"etat", "state", "storage_state", "localStorage", "sessionStorage"}}
    if isinstance(value, list):
        return [sanitize(x, literals) for x in value]
    if isinstance(value, str):
        value = BEARER.sub("Bearer [redacted]", value)
        value = URL_SECRET.sub(r"\1[redacted]", value)
        value = EMAIL.sub("[email]", value)
        for literal in sorted(literals, key=len, reverse=True):
            if literal:
                value = value.replace(literal, "[redacted]")
    return value


def export_report(source, destination, language, literals=(), include_captures=False):
    from . import engine
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if destination == source or source in destination.parents or destination in source.parents:
        raise ValueError("Export to a separate directory outside the source session")
    if destination.exists() and any(destination.iterdir()):
        raise ValueError("Output must be empty")
    if not (source / "constats.json").is_file():
        raise ValueError("No constats.json in the source session")
    destination.mkdir(parents=True, exist_ok=True)
    files = ["constats.json", "config.json", "personas.json", "coverage.json", "tirage.json"]
    findings = json.loads((source / "constats.json").read_text(encoding="utf-8-sig"))
    for finding in findings.get("constats", []):
        for proof in (finding.get("preuves") or {}).values():
            if isinstance(proof, str) and proof.endswith(".json"):
                files.append(proof)
    for name in dict.fromkeys(files):
        path = (source / name).resolve()
        if not path.is_relative_to(source) or path.is_symlink():
            raise ValueError("Evidence path escapes the source session")
        if not path.is_file():
            continue
        value = sanitize(json.loads(path.read_text(encoding="utf-8-sig")), literals)
        if name == "config.json":
            value = {k: value[k] for k in ("url", "demo", "project", "navigateur", "debut") if k in value}
        def remove_captures(obj):
            if isinstance(obj, dict):
                for key in list(obj):
                    if key in {"capture", "captures", "scenario", "dossier_horde", "command", "commande"}:
                        obj[key] = None
                    else:
                        remove_captures(obj[key])
            elif isinstance(obj, list):
                for item in obj:
                    remove_captures(item)
        # Reproduction captures can be absolute. Keep them out of the exported proofs.
        remove_captures(value)
        out = destination / path.relative_to(source)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    events = []
    for event in engine.lire_journal(source):
        event = sanitize(event, literals)
        event.pop("ecran", None)
        event.pop("args", None)  # Typed values are unnecessary in a public replay.
        capture = event.get("capture")
        event["capture"] = None
        if include_captures and isinstance(capture, str):
            path = (source / capture).resolve()
            if path.is_relative_to(source) and path.is_file() and path.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}:
                relative = Path("captures") / f"{len(events):06d}{path.suffix.lower()}"
                (destination / relative).parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(path, destination / relative)
                event["capture"] = relative.as_posix()
        events.append(event)
    (destination / "journal.jsonl").write_text("".join(json.dumps(e, ensure_ascii=False) + "\n" for e in events), encoding="utf-8")
    engine.rapport(destination, language)
    (destination / "PRIVACY-REVIEW.txt").write_text(
        "Review before sharing. Automated redaction is incomplete. Screenshots were " +
        ("explicitly included; inspect every image." if include_captures else "excluded.") +
        " Original evidence stays private. This copy is not a replay scenario.\n", encoding="utf-8")
    return destination


def main(argv=None):
    parser = argparse.ArgumentParser(prog="chaosfolk privacy")
    parser.add_argument("--folder", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--lang", choices=("en", "fr"), required=True)
    parser.add_argument("--redact-file", type=Path, help="JSON list of exact sensitive strings; kept local")
    parser.add_argument("--include-reviewed-captures", action="store_true",
                        help="include only after inspecting every screenshot yourself")
    args = parser.parse_args(argv)
    try:
        literals = json.loads(args.redact_file.read_text(encoding="utf-8")) if args.redact_file else []
        if not isinstance(literals, list) or any(not isinstance(x, str) for x in literals):
            raise ValueError("Redaction file must contain a list of strings")
        result = export_report(args.folder, args.output, args.lang, literals, args.include_reviewed_captures)
        print(f"Review the sanitized copy before sharing: {result / 'rapport.html'}")
        return 0
    except (OSError, ValueError) as error:
        print(f"privacy: {error}")
        return 2
