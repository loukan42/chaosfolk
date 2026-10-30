"""Disk-backed journal projection and incremental standalone report rendering."""
from collections.abc import Mapping
from contextlib import closing
import hashlib
import json
from pathlib import Path
import re
import shutil
import sqlite3
import tempfile

INLINE_JOURNAL_BYTES = 4 * 1024 * 1024
DETAIL_CHUNK_BYTES = 256 * 1024
DETAIL_CHUNK_EVENTS = 128
DETAIL_CACHE_BYTES = 1024 * 1024
DETAIL_CACHE_CHUNKS = 4
INDEX_FIELDS = ("type", "h", "n", "t", "action", "resultat", "capture", "gravite", "id", "panne")
_SCOUT = re.compile(r"e\d+").fullmatch


def _encoder(ensure_ascii=False):
    # NaN/Infinity are not JSON: JSON.parse would fail and leave an empty report.
    return json.JSONEncoder(ensure_ascii=ensure_ascii, allow_nan=False)


def _literal(chunk):
    """Escape a JSON fragment for a double-quoted JavaScript string inside a script element."""
    return (json.dumps(chunk, ensure_ascii=False)[1:-1].replace("<", "\\u003c")
            .replace("\u2028", "\\u2028").replace("\u2029", "\\u2029"))


class IndexedJournal:
    """Playback metadata only; full projected events remain in local chunks."""
    fields = INDEX_FIELDS

    def __init__(self, journal):
        self.journal = journal

    def encoded_events(self):
        # The summary column was projected at insertion; append the detail position.
        with closing(self.journal.db.execute("SELECT summary FROM events ORDER BY seq")) as rows:
            for index, (summary,) in enumerate(rows):
                yield f'{summary[:-1]},"_detail":{index}}}'

    def __iter__(self):
        for encoded in self.encoded_events():
            yield json.loads(encoded)


def write_detail_chunk(folder, payload):
    encoded = payload.encode("utf-8")
    identity = hashlib.sha256(encoded).hexdigest()
    relative = f"assets/journal/{identity}.js"
    target = Path(folder) / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    # Content-addressed: an existing file with this name already holds this payload.
    if not target.is_file():
        # JSON.parse prevents object-literal __proto__ semantics. No supplied text
        # becomes code; scripts are used so reports also work from file:// URLs.
        script = ("window.__chaosfolkReceiveDetails(" + json.dumps(identity) + ",JSON.parse("
                  + _encoder().encode(payload).replace("\u2028", "\\u2028").replace("\u2029", "\\u2029") + "));\n")
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="\n", dir=target.parent,
                                             prefix=".details-", suffix=".tmp", delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(script)
            temporary.replace(target)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
    return {"id": identity, "file": relative, "bytes": len(encoded)}


def prepare_browser_data(folder, data, journal):
    """Externalize large journals while retaining every event and proof field."""
    if not isinstance(journal, JournalSpool):
        return data, journal
    size = journal.db.execute("SELECT COALESCE(SUM(length(CAST(payload AS BLOB))),0) FROM events").fetchone()[0]
    if size <= INLINE_JOURNAL_BYTES:
        encoder = _encoder()
        size += sum(len(encoder.encode(key)) + 2 + len(encoder.encode(value).encode("utf-8")) for key, value in data.items())
        if size <= INLINE_JOURNAL_BYTES:
            return data, journal
    manifest = {"version": 1, "chunks": [], "proofs": {}, "total_events": 0,
                "cache_bytes": DETAIL_CACHE_BYTES, "cache_chunks": DETAIL_CACHE_CHUNKS}
    batch, batch_size, start = [], 0, 0

    def flush():
        nonlocal batch, batch_size, start
        if not batch:
            return
        descriptor = write_detail_chunk(folder, '{"events":[' + ",".join(batch) + "]}")
        manifest["chunks"].append(dict(descriptor, start=start, count=len(batch)))
        start += len(batch)
        batch, batch_size = [], 0

    for encoded, event_size in journal.encoded_events(with_size=True):
        if batch and (len(batch) >= DETAIL_CHUNK_EVENTS or batch_size + event_size > DETAIL_CHUNK_BYTES):
            flush()
        batch.append(encoded)
        batch_size += event_size
    flush()
    manifest["total_events"] = start
    # Finding labels and proof counters stay immediately available. Captures,
    # reasons and full trial/manifest evidence are read when opened.
    result = dict(data)

    def defer_proof(proof):
        descriptor = write_detail_chunk(folder, _encoder().encode({"proof": proof}))
        manifest["proofs"][descriptor["id"]] = descriptor
        summary = {name: proof[name] for name in ("nom", "mode", "fois", "demandes", "casses", "verdict",
                   "trial_integrity", "introuvable", "source", "reproducibility") if name in proof}
        if "essais" in proof:
            from .scoring import complete
            summary["trial_integrity"] = complete(proof, proof.get("mode"))
        summary["_proof_detail"] = descriptor["id"]
        return summary

    if isinstance(data.get("constats"), dict):
        result["constats"] = dict(data["constats"])
        findings = []
        for finding in data["constats"].get("constats", []):
            if not isinstance(finding, dict):
                findings.append(finding)
                continue
            copy = dict(finding)
            proofs = {}
            for key, proof in (finding.get("preuves") or {}).items():
                if not isinstance(proof, dict):
                    proofs[key] = proof
                    continue
                proofs[key] = defer_proof(proof)
            if "preuves" in finding:
                copy["preuves"] = proofs
            findings.append(copy)
        if "constats" in data["constats"]:
            result["constats"]["constats"] = findings
    if isinstance(data.get("replay_matrices"), list):
        matrices = []
        for matrix in data["replay_matrices"]:
            if not isinstance(matrix, dict) or not isinstance(matrix.get("cells"), dict):
                matrices.append(matrix)
                continue
            cells = {}
            for key, cell in matrix["cells"].items():
                if not isinstance(cell, dict):
                    cells[key] = cell
                    continue
                summary = defer_proof(cell)
                trials = cell.get("essais") if isinstance(cell.get("essais"), list) else []
                summary["_preparation_verified"] = bool(trials) and all(
                    isinstance(trial, dict) and isinstance(trial.get("preparation"), dict)
                    and trial["preparation"].get("status") == "reset-verified" for trial in trials)
                cells[key] = summary
            matrices.append(dict(matrix, cells=cells))
        result["replay_matrices"] = matrices
    result["journal_details"] = manifest
    return result, IndexedJournal(journal)


class JournalSpool:
    """Keep event order and evidence on disk, with a bounded SQLite page cache.

    Scoring columns (verb, outcome, severity) and the playback summary are
    projected once at insertion so later passes never decode full payloads.
    """

    def __init__(self, events, *, collapse_anomalies=True):
        self.db = sqlite3.connect("")
        try:
            # A throwaway database: no rollback journal, no fsync.
            self.db.execute("PRAGMA cache_size=-2048")
            self.db.execute("PRAGMA temp_store=FILE")
            self.db.execute("PRAGMA journal_mode=OFF")
            self.db.execute("PRAGMA synchronous=OFF")
            self.db.execute("CREATE TABLE events (seq INTEGER PRIMARY KEY, kind TEXT, human TEXT, stamp REAL, scout INTEGER, "
                            "action_key TEXT, anomaly TEXT UNIQUE, count INTEGER, verb TEXT, outcome TEXT, severity TEXT, "
                            "summary TEXT, payload TEXT)")
            self.db.executemany(
                "INSERT INTO events(kind,human,stamp,scout,action_key,anomaly,count,verb,outcome,severity,summary,payload) "
                "VALUES (?,?,?,?,?,?,1,?,?,?,?,?) ON CONFLICT(anomaly) DO UPDATE SET count=count+1",
                self._rows(events, collapse_anomalies))
            # (kind, human) serves kind-only and per-user queries; the action key resolves finding references.
            self.db.execute("CREATE INDEX events_kind_human ON events(kind,human,stamp,seq)")
            self.db.execute("CREATE INDEX events_action_key ON events(action_key,seq)")
            self.db.commit()
        except BaseException:
            self.db.close()
            raise

    @staticmethod
    def _rows(events, collapse_anomalies):
        dumps = _encoder().encode
        for original in events:
            event = dict(original)
            kind = event["type"]
            anomaly = action_key = None
            if kind == "action":
                for key in ("ecran", "duree_ms", "taille_reponse"):
                    event.pop(key, None)
                target = event.pop("cible", None) or {}
                event["cible_nom"] = target.get("nom")
                if event.get("action") == "type" and target.get("sensitive") is True and isinstance(event.get("args"), dict):
                    # Password and one-time-code values stay in the private journal only, never in a report.
                    event["args"] = {**event["args"], "texte": "[masked]"}
                action_key = dumps([event.get("h"), event.get("n")])
            elif kind == "anomalie" and collapse_anomalies:
                anomaly = dumps([event.get("h"), event.get("genre"), event.get("message"),
                                 dumps(event.get("induite") or []), dumps(event.get("apres") or [])])
                event["nombre"] = 1
            summary = {key: event[key] for key in INDEX_FIELDS if key in event}
            if "erreur" in event:
                summary["erreur"] = bool(event["erreur"])
            severity = event.get("gravite")
            yield (kind, event.get("h"), event.get("t") or 0, bool(_SCOUT(str(event.get("h", "")))), action_key, anomaly,
                   event.get("action"), event.get("resultat"), severity if isinstance(severity, str) else dumps(severity),
                   dumps(summary), dumps(event))

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.db.close()

    def __iter__(self):
        return self.events()

    def encoded_events(self, *, with_size=False):
        sql = "SELECT payload,anomaly,count,length(CAST(payload AS BLOB)) FROM events ORDER BY seq"
        with closing(self.db.execute(sql)) as rows:
            for payload, anomaly, count, size in rows:
                if anomaly is not None:
                    event = json.loads(payload)
                    event["nombre"] = count
                    payload = _encoder().encode(event)
                    size = len(payload.encode("utf-8"))
                yield (payload, size) if with_size else payload

    def events(self, *, kind=None, human=None, scored=False, chronological=False):
        conditions, values = [], []
        if kind is not None:
            kinds = kind if isinstance(kind, tuple) else (kind,)
            conditions.append("kind IN (" + ",".join("?" for _ in kinds) + ")")
            values.extend(kinds)
        if human is not None:
            conditions.append("human=?")
            values.append(human)
        if scored:
            conditions.append("scout=0")
        where = " WHERE " + " AND ".join(conditions) if conditions else ""
        order = "stamp,seq" if chronological else "seq"
        with closing(self.db.execute(f"SELECT payload,anomaly,count FROM events{where} ORDER BY {order}", values)) as rows:
            for payload, anomaly, count in rows:
                event = json.loads(payload)
                if anomaly is not None:
                    event["nombre"] = count
                if scored:
                    event["t"] = event.get("t") or 0
                yield event

    def scored_actions(self, human):
        """The fields fault judgments read, in chronological order, without decoding payloads."""
        sql = "SELECT stamp,verb,outcome,severity FROM events WHERE kind='action' AND human=? AND scout=0 ORDER BY stamp,seq"
        with closing(self.db.execute(sql, (human,))) as rows:
            for stamp, verb, outcome, severity in rows:
                yield {"t": stamp, "action": verb, "resultat": outcome, "gravite": severity}

    def action_urls(self, references):
        found = {}
        for human, number in references:
            # Event numbers can restart after arrival. Keep the final matching
            # event, as the original dictionary-based report lookup did.
            row = self.db.execute("SELECT payload FROM events WHERE action_key=? ORDER BY seq DESC LIMIT 1",
                                  (json.dumps([human, number]),)).fetchone()
            if row is not None:
                found[(human, number)] = {"url": json.loads(row[0]).get("url")}
        return found

    def scoring_metrics(self):
        from .scoring import console_penalty, fault_pillar
        users = [row[0] for row in self.db.execute(
            "SELECT human FROM events WHERE kind='action' AND scout=0 AND human IS NOT NULL AND human!='' "
            "GROUP BY human ORDER BY MIN(stamp),MIN(seq)")]
        by_user = _UserActions(self, users)
        completed = sum(self.db.execute(
            "SELECT verb FROM events WHERE kind='action' AND human=? ORDER BY stamp DESC,seq DESC LIMIT 1",
            (human,)).fetchone()[0] == "done" for human in users)
        faults = self.events(kind=("panne-debut", "panne-fin"), scored=True, chronological=True)
        return {"fault": fault_pillar(faults, by_user, storage="disk"), "missions": 10 * completed / len(users) if users else 0,
                "console_errors": console_penalty(self.events(kind="anomalie", scored=True, chronological=True)),
                "has_actions": bool(users)}


class _UserActions(Mapping):
    def __init__(self, spool, users):
        self.spool, self.users = spool, dict.fromkeys(users)

    def __iter__(self):
        return iter(self.users)

    def __len__(self):
        return len(self.users)

    def __getitem__(self, key):
        if key not in self.users:
            raise KeyError(key)
        return self.spool.scored_actions(key)


def data_chunks(data, journal):
    """Encode metadata and journal events without constructing one JSON string."""
    encoder = _encoder()
    yield "{"
    for index, (key, value) in enumerate(data.items()):
        if index:
            yield ", "
        yield encoder.encode(key) + ": "
        if key == "journal":
            yield "["
            events = journal.encoded_events() if hasattr(journal, "encoded_events") else map(encoder.encode, journal)
            for number, event in enumerate(events):
                if number:
                    yield ", "
                yield event
            yield "]"
        else:
            # Metadata values are bounded; the C encoder is several times faster than iterencode.
            yield encoder.encode(value)
    yield "}"


def write_reports(folder, template, data, journal, default_language):
    filenames = {"en": "report-en.html", "fr": "rapport-fr.html"}
    if default_language not in filenames:
        raise ValueError("Report language must be en or fr")  # The value is interpolated into <html lang>.
    marker = "/*__DONNEES__*/null"
    if template.count(marker) != 1:
        raise ValueError("Report template must contain exactly one data marker")
    prefix, suffix = template.split(marker)
    folder = Path(folder)
    data, journal = prepare_browser_data(folder, data, journal)
    data = {key: value for key, value in data.items() if key != "lang"}
    body = None
    try:
        # Parse JSON instead of evaluating an object literal: __proto__ must
        # remain an ordinary evidence field, never a prototype. The escaped
        # body is written once; only the trailing language value differs.
        with tempfile.NamedTemporaryFile(mode="wb", dir=folder, prefix=".report-body-", suffix=".tmp", delete=False) as stream:
            body = Path(stream.name)
            stream.write(b'JSON.parse("')
            for chunk in data_chunks(data, journal):
                if chunk != "}":
                    stream.write(_literal(chunk).encode("utf-8"))
        # The default report is written from the same body rather than copied
        # from a report just closed: reopening a fresh file waits for antivirus scans on Windows.
        outputs = [*filenames.items(), (default_language, "rapport.html")]
        for language, filename in outputs:
            tail = _literal((", " if data else "") + '"lang": ' + json.dumps(language) + "}") + '")'
            temporary = None
            try:
                with tempfile.NamedTemporaryFile(mode="wb", dir=folder, prefix=".report-", suffix=".tmp", delete=False) as stream:
                    temporary = Path(stream.name)
                    stream.write(prefix.replace('<html lang="en">', f'<html lang="{language}">', 1).encode("utf-8"))
                    with body.open("rb") as source:
                        shutil.copyfileobj(source, stream, 1024 * 1024)
                    stream.write(tail.encode("utf-8"))
                    stream.write(suffix.encode("utf-8"))
                temporary.replace(folder / filename)
            finally:
                if temporary is not None:
                    temporary.unlink(missing_ok=True)
    finally:
        if body is not None:
            body.unlink(missing_ok=True)
