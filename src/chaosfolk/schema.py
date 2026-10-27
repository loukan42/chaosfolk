"""Translate the public English replay schema to the engine's stored format.

Aliases are explicit and scoped. User text and arbitrary JavaScript are never
rewritten. Existing saved traces remain readable.
"""
from copy import deepcopy
from urllib.parse import urlsplit


def aliases(data, mapping):
    if not isinstance(data, dict):
        raise ValueError("Expected a JSON object")
    result = deepcopy(data)
    for public, stored in mapping.items():
        if public in result:
            if stored in result and result[stored] != result[public]:
                raise ValueError(f"Conflicting fields: {public} and {stored}")
            result[stored] = result.pop(public)
    return result


def normalize_assertion(rule):
    return aliases(rule, {"text": "texte", "key": "cle", "contains": "contient", "equals": "egal",
                          "field": "champ", "value": "valeur"})


def normalize_scenario(scenario):
    result = aliases(scenario, {"steps": "etapes", "expect": "attendu", "faults": "pannes",
                               "device": "appareil", "start": "depart", "state": "etat",
                               "session_dir": "dossier_horde", "clock": "horloge", "recipe": "recette"})
    url = result.get("url")
    if not isinstance(url, str) or urlsplit(url).scheme not in ("http", "https") or not urlsplit(url).hostname:
        raise ValueError("Scenario url must be an absolute HTTP(S) address")
    sessions = result.get("sessions") or {}
    if not isinstance(sessions, dict) or any(not isinstance(v, dict) for v in sessions.values()):
        raise ValueError("Scenario sessions must map a name to its settings")
    result["sessions"] = {name: aliases(v, {"state": "etat", "device": "appareil", "start": "depart"}) for name, v in sessions.items()}
    steps = result.get("etapes")
    if not isinstance(steps, list):
        raise ValueError("Scenario steps must be a list")
    from .engine import GESTES, ALIAS_ACTIONS, ALIAS_PANNES, PANNES
    for index, step in enumerate(steps):
        if not isinstance(step, dict) or not isinstance(step.get("action"), str):
            raise ValueError(f"Step {index + 1} needs an action")
        action = ALIAS_ACTIONS.get(step["action"], step["action"])
        if action not in GESTES:
            raise ValueError(f"Step {index + 1}: unknown action {step['action']!r}")
        step = aliases(step, {"target": "cible"})
        step["args"] = aliases(step.get("args", {}), {"text": "texte", "key": "touche",
            "direction": "sens", "times": "fois", "seconds": "secondes", "path": "chemin",
            "slow": "lent", "enter": "entree"})
        if "cible" in step:
            step["cible"] = aliases(step["cible"], {"name": "nom", "text": "texte"})
        required = {"goto": "url", "type": "texte", "select": "option", "key": "touche", "upload": "chemin"}
        if action in required and not isinstance(step["args"].get(required[action]), str):
            raise ValueError(f"Step {index + 1}: {action} requires a string {required[action]} argument")
        if action in {"click", "type", "select", "tick", "hover", "upload"}:
            target = step.get("cible", {})
            if not any(isinstance(target.get(key), str) and target[key] for key in ("testid", "role", "placeholder", "css", "texte")):
                raise ValueError(f"Step {index + 1}: {action} requires a replayable target descriptor")
        steps[index] = step
    faults = result.get("pannes", [])
    if not isinstance(faults, list) or any(not isinstance(f, dict) for f in faults):
        raise ValueError("Scenario faults must be a list of objects")
    result["pannes"] = [aliases(f, {"start_action": "debut_n", "end_action": "fin_n"}) for f in faults]
    for fault in result["pannes"]:
        if ALIAS_PANNES.get(fault.get("type"), fault.get("type")) not in PANNES:
            raise ValueError(f"Unknown fault: {fault.get('type')!r}")
        for field in ("debut_n", "fin_n", "debut_etape", "fin_etape"):
            if field in fault and (type(fault[field]) is not int or fault[field] < 0):
                raise ValueError(f"Fault {field} must be a non-negative integer")
        if "debut_n" in fault and "fin_n" in fault and fault["fin_n"] < fault["debut_n"]:
            raise ValueError("Fault ends before it starts")
    expected = result.get("attendu", [])
    if isinstance(expected, dict):
        expected = [expected]
    if not isinstance(expected, list):
        raise ValueError("Scenario expect must be an assertion or list of assertions")
    result["attendu"] = [normalize_assertion(rule) for rule in expected]
    return result
