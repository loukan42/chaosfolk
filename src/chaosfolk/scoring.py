"""The session's evidence-weighted score, normalized over available pillars.

This is a report heuristic, not a probability of correctness or total coverage.
Actual results and an optional modeled after-fix projection stay separate.
"""
import math
import re
import unicodedata


def normalized(value):
    return "".join(c for c in unicodedata.normalize("NFD", str(value or "")) if not unicodedata.combining(c)).lower()


def severity(value):
    value = normalized(value)
    if re.match(r"bloq|block|crit|majeur", value):
        return "blocking"
    if re.match(r"gen|annoy", value):
        return "annoying"
    return "minor"


def status(value):
    value = normalized(value)
    if re.search(r"non\W*reprodu|ecart|rejet|excluded|rejected|not\W*reprodu", value):
        return "excluded"
    if re.search(r"repar|fixed|repaired", value):
        return "fixed"
    if re.search(r"decid|trancher|decision", value):
        return "decision"
    if "intermittent" in value:
        return "intermittent"
    return "observed"


def complete(series, mode):
    """A summary must identify the right series and every requested trial."""
    if (not isinstance(series, dict) or series.get("introuvable") or series.get("mode") != mode
            or series.get("trial_integrity") is False):
        return False
    count, requested, failed = (series.get(key) for key in ("fois", "demandes", "casses"))
    counts_ok = (type(count) is int and type(requested) is int and type(failed) is int
                 and count >= 3 and count == requested and 0 <= failed <= count)
    if not counts_ok:
        return False
    if "essais" in series:
        trials = series["essais"]
        return (isinstance(trials, list) and len(trials) == count
                and all(isinstance(t, dict) and type(t.get("ok")) is bool and not t.get("divergence") for t in trials)
                and sum(t["ok"] is False for t in trials) == failed)
    return True


def passes(series, mode="traitement"):
    return complete(series, mode) and series["casses"] == 0


def fails(series, mode="traitement"):
    return complete(series, mode) and series["casses"] == series["fois"]


def finding_info(finding):
    declared = status(finding.get("statut"))
    proof = finding.get("preuves") or {}
    if not isinstance(proof, dict):
        proof = {}
    before, control, after, removed = (proof.get(key) for key in ("avant", "temoin", "apres", "demontee"))
    condition = normalized(finding.get("condition")).strip() not in ("", "none", "aucune", "no fault")
    reproduced = fails(before) and (not condition or passes(control, "temoin"))
    intermittent = complete(before, "traitement") and 0 < before["casses"] < before["fois"]
    qualification = finding.get("qualification")
    basis = finding.get("expected_basis")
    qualified = qualification == "defect" and isinstance(basis, str) and bool(basis.strip())
    qualified = qualified and declared not in ("excluded", "decision")
    repair = None
    if declared == "fixed" and qualified and reproduced and passes(after):
        after_control_ok = "after_control" not in proof or passes(proof["after_control"], "temoin")
        if after_control_ok:
            repair = "complete" if fails(removed) else "partial"
    evidence = ("excluded" if declared == "excluded" else "proven" if reproduced else
                "not-reproduced" if passes(before) else "intermittent" if intermittent else "observed")
    stage = ("excluded" if evidence == "excluded" else "decision" if declared == "decision" or qualification == "product-decision"
             else "suggestion" if qualification == "suggestion" else "fixed" if repair
             else "proven" if qualified and reproduced else "pending")
    factor = (0 if stage in ("excluded", "decision", "suggestion") else 0.15 if repair == "complete"
              else 0.3 if repair == "partial" else 1 if stage == "proven"
              else 0.6 if qualified and intermittent and (not condition or passes(control, "temoin")) else 0)
    return {"id": str(finding.get("id", "")), "severity": severity(finding.get("gravite")),
            "evidence": evidence, "repair": repair, "stage": stage, "factor": factor}


def cap_for(items):
    checks = [
        (59, "proven-blocker", lambda x: x["severity"] == "blocking" and x["stage"] == "proven"),
        (74, "open-blocker", lambda x: x["severity"] == "blocking" and x["stage"] == "fixed"),
        (89, "proven-annoying", lambda x: x["severity"] == "annoying" and x["stage"] == "proven"),
    ]
    for value, reason, predicate in checks:
        ids = [item["id"] for item in items if predicate(item)]
        if ids:
            return {"value": value, "ids": ids, "reason": reason}
    return {"value": 100, "ids": [], "reason": None}


def property_status(value):
    value = normalized(value)
    if re.search(r"non\W*test|not\W*test|untested", value):
        return "untested"
    if re.search(r"repar|fixed|repaired", value):
        return "fixed"
    if re.search(r"cass|^ko|echou|failed|broken", value):
        return "failed"
    if re.search(r"tenu|tient|^ok|passed|holds", value):
        return "passed"
    return "untested"


def console_penalty(journal):
    noise = (r"\[vite\]", r"Vite server", r"wss?://localhost[^ ]*token=", r"/@vite/", r"\[hmr\]")
    groups = {}
    for event in journal:
        if event.get("type") != "anomalie":
            continue
        message, genre = str(event.get("message") or ""), event.get("genre")
        if any(re.search(pattern, message) for pattern in noise) or event.get("induite") or event.get("apres"):
            continue
        weight = 2 if genre in ("erreur-js", "crash") else 1 if genre == "console" else 2 if genre == "http" and re.match(r"5\d\d", message) else 0
        normalized_message = re.sub(r"\d{3,}", "N", re.sub(r"(?:https?|wss?)://[^ ]+", "URL", message.split("\n")[0]))[:180]
        groups[(genre, normalized_message)] = weight
    return sum(groups.values())


def fault_pillar(journal, by_user, *, storage="memory"):
    from .fault_index import FaultIndex
    faults = {}
    for event in journal:
        if event.get("type") == "panne-debut" and event.get("id") is not None:
            faults[str(event["id"])] = {"h": event.get("h"), "start": event.get("t", 0), "end": None, "error": event.get("erreur")}
        elif event.get("type") == "panne-fin" and str(event.get("id")) in faults:
            faults[str(event["id"])]["end"] = event.get("t", 0)
    judged = []
    with FaultIndex(storage, lambda value: severity(value) == "blocking") as index:
        for fault in faults.values():
            if fault["error"]:
                continue  # A failed injection cannot establish app resilience.
            touched = []
            candidates = [fault["h"]] if fault["h"] else by_user
            for user in candidates:
                outcome = index.outcome(user, by_user, fault["start"], fault["end"])
                if outcome is not None:
                    touched.append(outcome)
            if touched:
                judged.append(all(touched))
    return {"id": "faults", "value": 15 * sum(judged) / len(judged), "max": 15} if judged else None


def score_report(data, *, journal_metrics=None):
    report = data.get("constats") or {}
    reviewed = isinstance(report.get("constats"), list)
    findings = [finding for finding in report.get("constats", []) if isinstance(finding, dict)]
    properties = [prop for prop in report.get("proprietes", []) if isinstance(prop, dict)]
    if journal_metrics is None:
        journal = [dict(event, t=event.get("t") or 0) for event in data.get("journal", [])
                   if isinstance(event, dict) and not re.fullmatch(r"e\d+", str(event.get("h", "")))]
        journal.sort(key=lambda event: event["t"])
        by_user = {}
        for event in journal:
            if event.get("type") == "action" and event.get("h"):
                by_user.setdefault(event["h"], []).append(event)
        journal_metrics = {"fault": fault_pillar(journal, by_user),
                           "missions": 10 * sum(actions[-1].get("action") == "done" for actions in by_user.values()) / len(by_user) if by_user else 0,
                           "console_errors": console_penalty(journal), "has_actions": bool(by_user)}
    items = [finding_info(dict(finding, id=finding.get("id", f"C{index}"))) for index, finding in enumerate(findings, 1)]
    fault = journal_metrics["fault"]
    missions = journal_metrics["missions"]
    console_errors = journal_metrics["console_errors"]
    console = 5 * math.exp(-console_errors / 4)
    weights = {"blocking": 10, "annoying": 4, "minor": 1}
    has_evidence = bool(findings or journal_metrics["has_actions"] or any(property_status(p.get("statut")) != "untested" for p in properties) or console_errors or fault)
    provisional = not reviewed or not has_evidence or any(item["stage"] == "pending" for item in items)
    audit = data.get("audit_session")
    if isinstance(audit, dict):
        provisional = provisional or audit.get("completion") != "complete"
        if not audit.get("tested"):
            has_evidence = False

    def calculate(scored_items, scored_properties):
        penalty = sum(weights[item["severity"]] * item["factor"] for item in scored_items)
        pillars = [{"id": "defects", "value": 50 * math.exp(-penalty / 30), "max": 50}]
        tested = [property_status(prop.get("statut")) for prop in scored_properties if property_status(prop.get("statut")) != "untested"]
        if tested:
            passed = tested.count("passed") + 0.8 * tested.count("fixed")
            pillars.append({"id": "properties", "value": 20 * passed / len(tested), "max": 20})
        if fault:
            pillars.append(fault)
        pillars.append({"id": "journeys", "value": missions + console, "max": 15})
        cap = cap_for(scored_items) if reviewed else {"value": 100, "ids": [], "reason": None}
        raw = 100 * sum(p["value"] for p in pillars) / sum(p["max"] for p in pillars)
        note = math.floor(min(raw, cap["value"]) + 0.5) if has_evidence else None
        level = next((label for threshold, label in ((90, "tested"), (75, "solid"), (60, "fair"), (40, "unstable"), (0, "fragile")) if note is not None and note >= threshold), None)
        return {"note": note, "raw": raw if has_evidence else None, "level": level, "provisional": provisional,
                "cap": cap, "pillars": pillars if has_evidence else [], "penalty": penalty}

    result = calculate(items, properties)
    repairable = {item["id"] for item in items if item["stage"] == "proven"}
    if repairable:
        projected_items = [dict(item, repair="complete", stage="fixed", factor=0.15) if item["id"] in repairable else item for item in items]
        projected_properties = [dict(prop, statut="fixed") if str(prop.get("constat")) in repairable else prop for prop in properties]
        projected = calculate(projected_items, projected_properties)
        result["after_fix"] = {key: projected[key] for key in ("note", "raw", "cap")}
        result["after_fix"]["projected"] = True
    return result
