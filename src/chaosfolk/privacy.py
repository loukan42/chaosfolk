"""Capture masks and reviewable, sanitized copies of report evidence."""
import argparse
from contextlib import redirect_stdout
import io
import json
import os
import re
import shutil
import tempfile
from pathlib import Path
from urllib.parse import unquote_plus

MASKS = ['input[type="password"]', '[autocomplete^="cc-"]',
         '[autocomplete="one-time-code"]', '[data-chaosfolk-private]']
SECRET = re.compile(r"password|passwd|secret|authorization|cookie|token|api.?key|jeton", re.I)
EMAIL = re.compile(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}")
# A value stops at the closing quote or bracket of HTML attributes, Markdown links and JSON-in-strings.
URL_PARAMETER = re.compile(r"([?&#])([^=&#\s]+)=([^&#\s\"'<>)\]}\\]*)")
# Any scheme carries credentials in its authority: wss, postgres, redis, amqp, mongodb...
URL_CREDENTIALS = re.compile(r"(\w[\w+.-]*://)[^\s/@]+@")
BEARER = re.compile(r"(?i)Bearer\s+[A-Za-z0-9._~+/-]+=*")
# Whole parameter names (case-insensitive) that carry credentials without matching SECRET.
CREDENTIAL_PARAMETERS = frozenset(name.casefold() for name in (
    "email", "code", "session", "sessionid", "session_id", "sid",
    "sig", "signature", "X-Amz-Signature", "X-Amz-Credential", "X-Amz-Security-Token",
    "pwd", "pass", "auth", "key", "apikey", "access_key", "otp", "SAMLResponse", "assertion",
    "id_token", "access_token", "refresh_token", "client_secret", "private_key"))


def screenshot_masks(page, extra=()):
    configured = json.loads(os.environ.get("CHAOSFOLK_MASK_SELECTORS", "[]"))
    if not isinstance(configured, list) or any(not isinstance(x, str) or not x for x in configured):
        raise ValueError("CHAOSFOLK_MASK_SELECTORS must be a JSON list of CSS selectors")
    # Frame locators also cover passwords in embedded sign-in forms.
    return [frame.locator(selector) for frame in page.frames for selector in (*MASKS, *configured, *extra)]


def sanitize(value, literals=()):
    return _sanitize(value, tuple(sorted(literals, key=len, reverse=True)))


def _sanitize(value, literals):
    if isinstance(value, dict):
        return {key: "[redacted]" if SECRET.search(key) else _sanitize(item, literals)
                for key, item in value.items()
                if key not in {"etat", "state", "storage_state", "localStorage", "sessionStorage"}}
    if isinstance(value, list):
        return [_sanitize(x, literals) for x in value]
    if isinstance(value, str):
        value = BEARER.sub("Bearer [redacted]", value)
        value = URL_CREDENTIALS.sub(r"\1[redacted]@", value)
        def redact_parameter(match):
            key = unquote_plus(match[2])
            sensitive = SECRET.search(key) or key.casefold() in CREDENTIAL_PARAMETERS
            return f"{match[1]}{match[2]}=[redacted]" if sensitive else match[0]
        value = URL_PARAMETER.sub(redact_parameter, value)
        value = EMAIL.sub("[email]", value)
        for literal in literals:
            if literal:
                value = value.replace(literal, "[redacted]")
    return value


def export_report(source, destination, language, literals=(), include_captures=False):
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if destination == source or source in destination.parents or destination in source.parents:
        raise ValueError("Export to a separate directory outside the source session")
    if destination.exists() and (not destination.is_dir() or any(destination.iterdir())):
        raise ValueError("Output must be empty")
    if language not in ("en", "fr"):
        raise ValueError("Report language must be en or fr")
    if not _evidence_path(source, "constats.json").is_file():
        raise ValueError("No constats.json in the source session")
    _evidence_path(source, "journal.jsonl")
    destination.parent.mkdir(parents=True, exist_ok=True)
    ordered_literals = tuple(sorted(literals, key=len, reverse=True))
    with tempfile.TemporaryDirectory(prefix=f".{destination.name}-export-", dir=destination.parent) as temporary:
        stage = Path(temporary) / "report"
        stage.mkdir()
        output = io.StringIO()
        with redirect_stdout(output):
            _export_contents(source, stage, language, ordered_literals, include_captures)
        removed_empty = False
        if destination.exists():
            # rmdir refuses a concurrently populated folder; no recursive removal.
            destination.rmdir()
            removed_empty = True
        try:
            stage.rename(destination)
        except BaseException:
            if removed_empty and not destination.exists():
                destination.mkdir(exist_ok=True)
            raise
        print(output.getvalue().replace(stage.as_posix(), destination.as_posix()), end="")
    return destination


def _evidence_path(source, name):
    path = (source / name).resolve()
    if not path.is_relative_to(source):
        raise ValueError("Evidence path escapes the source session")
    return path


def _export_contents(source, destination, language, literals, include_captures):
    from . import engine
    files = {name: _evidence_path(source, name)
             for name in ("constats.json", "config.json", "personas.json", "coverage.json", "tirage.json")}
    original = json.loads(files["constats.json"].read_text(encoding="utf-8-sig"))
    if not isinstance(original, dict) or not isinstance(original.get("constats", []), list):
        raise ValueError("constats.json must be an object with a constats list")
    findings = _sanitize(original, literals)
    proof_names = {}
    for index, finding in enumerate(original.get("constats", [])):
        if not isinstance(finding, dict) or not isinstance(finding.get("preuves") or {}, dict):
            raise ValueError("Each finding and its preuves must be JSON objects")
        for key, proof in (finding.get("preuves") or {}).items():
            reference = proof.get("source") if isinstance(proof, dict) else proof
            if isinstance(proof, dict) and reference is not None and not isinstance(reference, str):
                raise ValueError("Proof source must reference a JSON file")
            if not isinstance(reference, str) or not reference.endswith(".json"):
                if isinstance(proof, dict):
                    cleaned = findings["constats"][index]["preuves"][key]
                    if isinstance(cleaned, dict):
                        cleaned.pop("source", None)
                continue
            path = _evidence_path(source, reference)
            if path not in proof_names:
                proof_names[path] = f"reproductions/proof-{len(proof_names) + 1:06d}.json"
                files[proof_names[path]] = path
            # Generated links bypass text redaction so filenames and references
            # remain consistent even when a private name occurs in the source path.
            if isinstance(proof, str):
                findings["constats"][index]["preuves"][key] = proof_names[path]
            else:
                cleaned = findings["constats"][index]["preuves"][key]
                if isinstance(cleaned, dict):
                    cleaned["source"] = proof_names[path]
    for name, path in files.items():
        if not path.is_file():
            continue
        value = findings if name == "constats.json" else _sanitize(json.loads(path.read_text(encoding="utf-8-sig")), literals)
        if name == "config.json":
            value = {k: value[k] for k in ("url", "demo", "project", "navigateur", "debut") if k in value}
        def remove_captures(obj):
            if isinstance(obj, dict):
                for key in list(obj):
                    if key in {"capture", "captures", "scenario", "dossier_horde", "command", "commande", "live_evidence"}:
                        obj[key] = None
                    else:
                        remove_captures(obj[key])
            elif isinstance(obj, list):
                for item in obj:
                    remove_captures(item)
        # Reproduction captures can be absolute. Keep them out of the exported proofs.
        remove_captures(value)
        out = destination / name
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    with (destination / "journal.jsonl").open("w", encoding="utf-8") as journal:
        for index, event in enumerate(engine.iterer_journal(source)):
            capture = event.get("capture")
            # Screen text, typed values and live evidence never reach the public copy;
            # drop them before paying for their redaction.
            for key in ("ecran", "args", "live_evidence"):
                event.pop(key, None)
            event = _sanitize(event, literals)
            if event.get("type") == "evidence-spilled":
                event.pop("path", None)
                event.pop("records_preserved", None)
                event["private_evidence_excluded"] = True
            event["capture"] = None
            if include_captures and isinstance(capture, str):
                path = (source / capture).resolve()
                if path.is_relative_to(source) and path.is_file() and path.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}:
                    relative = Path("captures") / f"{index:06d}{path.suffix.lower()}"
                    (destination / relative).parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(path, destination / relative)
                    event["capture"] = relative.as_posix()
            journal.write(json.dumps(event, ensure_ascii=False) + "\n")
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
