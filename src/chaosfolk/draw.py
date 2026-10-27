"""Draw personas and reachable fault schedules from user goals.

The seed, count, squad, objectives, jobs, catalog and action budget together
determine the draw. Browser exploration itself is not deterministic.
"""
import json
import random
from pathlib import Path

CATALOGUE = Path(__file__).resolve().parent / "profiles.json"
ESCOUADES = {"ux": "UX et ergonomie : compréhension, parcours, clavier, mobile, jargon, erreurs"}

# Extra fault types are opt-in because they can mutate storage, clear a session,
# or send a backend write whose response is then dropped. Existing seeded draws
# keep their original catalogue and weights when no selection is provided.
EXTRA_FAULTS = [
    {"type": "http-error", "poids": 2, "apres_actions": [3, 12], "duree": [20, 45]},
    {"type": "lost-response", "poids": 1, "apres_actions": [3, 12], "params": {"fois": [1]}},
    {"type": "storage-corrupt", "poids": 1, "apres_actions": [3, 12]},
    {"type": "cookies-cleared", "poids": 1, "apres_actions": [3, 12]},
]


def lire_catalogue():
    return json.loads(CATALOGUE.read_text(encoding="utf-8"))


def graine_aleatoire():
    return random.SystemRandom().randint(100000, 999999)


def choisir_pondere(rng, options, poids):
    total = sum(poids)
    seuil = rng.uniform(0, total)
    cumul = 0
    for option, p in zip(options, poids):
        cumul += p
        if seuil <= cumul:
            return option
    return options[-1]


def tirer_horde(escouade, nombre, objectifs, graine, application, metiers=None, budget=20, fault_types=None, themes=None,
                checks="auto", detected=None, countries=None, explore=None, sessions="independent", shared=None,
                roles=None):
    """Retourne (personas, tirage) : la fiche des humains et les pannes à programmer.
    `checks` (auto, all, none ou des identifiants) donne à chaque humain sa part du catalogue de vérifications ;
    `detected` restreint auto aux types de champs et de pages relevés par `fields --save`."""
    if escouade not in ESCOUADES:
        raise ValueError(f"escouade inconnue : {escouade} (connues : {', '.join(ESCOUADES)})")
    if not objectifs:
        raise ValueError("au moins un objectif d'utilisateur est nécessaire (--objectives)")
    if type(nombre) is not int or not 1 <= nombre <= 100:
        raise ValueError("--count must be between 1 and 100")
    if type(budget) is not int or not 1 <= budget <= 10000:
        raise ValueError("--budget must be between 1 and 10000")
    if not isinstance(objectifs, list) or any(not isinstance(x, str) or not x.strip() for x in objectifs):
        raise ValueError("Objectives must be a non-empty list of non-empty strings")
    if metiers is not None and (not isinstance(metiers, list) or not metiers or any(not isinstance(x, str) or not x.strip() for x in metiers)):
        raise ValueError("Jobs must be a non-empty list of strings")
    cat = lire_catalogue()
    from .themes import THEMES, resolve
    selected_themes = resolve(themes) if themes is not None else ["ux"]
    from . import checks as catalogue_checks
    pool = catalogue_checks.select(checks, selected_themes, detected=detected, themes_given=themes is not None)
    if sessions == "coordinated" and checks == "auto":
        pool += [c for c in catalogue_checks.load()["checks"] if c["scope"] == "coordinated" and c not in pool]
    pays = catalogue_checks.countries(countries)
    parts = catalogue_checks.assign(graine, pool, nombre, budget, pays)
    available_faults = cat["pannes"] + EXTRA_FAULTS
    if fault_types is None:
        fault_options = cat["pannes"]
    else:
        if not isinstance(fault_types, list) or not fault_types or any(not isinstance(x, str) or not x for x in fault_types):
            raise ValueError("--faults requires comma-separated fault names")
        selected = {"aucune" if name == "none" else name for name in fault_types}
        supported = {item["type"] for item in available_faults}
        if selected == {"all"}:
            selected = supported
        invalid = selected - supported
        if invalid:
            raise ValueError(f"Unknown draw fault(s): {', '.join(sorted(invalid))}. app-stop is a global fault; schedule it separately.")
        fault_options = [item for item in available_faults if item["type"] in selected]
    rng = random.Random(graine)
    profils = list(cat["profils"])
    rng.shuffle(profils)
    metiers = metiers or cat["metiers"]
    names = [f"{first} {last}" for first in cat["prenoms"] for last in cat["noms"]]
    if nombre > len(set(names)):
        raise ValueError("Not enough unique names in the profile catalog")
    names = rng.sample(sorted(set(names)), nombre)
    humains, pannes = [], []
    for i in range(nombre):
        profil = profils[i % len(profils)]
        nom = names[i]
        hid = f"h{i + 1:02d}"
        appareil = profil.get("appareil") or choisir_pondere(
            rng, list(cat["appareils"]), list(cat["appareils"].values()))
        autres = [m for m in cat["manies_communes"] if m not in profil["manies"]]
        manies = rng.sample(profil["manies"], k=min(len(profil["manies"]), 3)) + rng.sample(autres, k=2)
        ordered_goals = list(objectifs)
        rng.shuffle(ordered_goals)
        question = rng.choice(cat["questions_comprehension"])
        intention = ("Explore all of these goals, starting in this order: "
                     + "; ".join(f"{number}. {goal}" for number, goal in enumerate(ordered_goals, 1))
                     + f". Stay within {budget} actions and report any unfinished goals. "
                     + "The budget does not guarantee that every goal will be covered. " + question)
        if profil.get("regle"):
            intention += f" {profil['regle']}"
        if themes is not None:
            intention += " Focus: " + " ".join(THEMES[name]["focus"] for name in selected_themes)
        if parts[i]:
            intention += " Also run the QA checks listed on this sheet when a matching screen appears."
        if explore:
            # chaque humain reçoit d'autres routes peu explorées : moins de répétitions d'une campagne à l'autre
            mine = [explore[(i * 3 + k) % len(explore)] for k in range(min(3, len(explore)))]
            intention += " Before your goals, visit these less explored areas if you can reach them: " + ", ".join(mine) + "."
        if sessions == "coordinated":
            intention += (" Other users work on the same test objects at the same time: " + "; ".join(shared)
                          + ". Open them, change them, and report when someone else's change is lost, hidden or conflicting.")
        else:
            intention += (f" Keep your data separate: add {hid.upper()} to the name of everything you create,"
                          " and change only records that carry it.")
        role = roles[i % len(roles)] if roles else None
        if role:
            intention += f" Your role in the app is {role[0]}: try what this role should and should not be allowed to do."
        fiche = {
            "id": hid, "nom": nom, "age": rng.randint(22, 64), "metier": rng.choice(metiers),
            "profil": profil["nom"], "escouade": escouade,
            "profil_id": profil["id"], "skin": cat["profils"].index(profil),
            "aisance": rng.choice(profil["aisance"]), "patience": rng.choice(profil["patience"]),
            "appareil": appareil, "intention": intention, "objectifs": ordered_goals, "themes": selected_themes,
            "habitudes": profil["habitudes"], "manies": manies,
            "histoire": "First visit; no previous experience with this app", "checks": parts[i],
        }
        if role:
            fiche["role"] = role[0]
            if role[1]:
                fiche["etat"] = role[1]
        panne = choisir_pondere(rng, fault_options, [p["poids"] for p in fault_options])
        fiche["condition"] = "aucune" if panne["type"] == "aucune" else panne["type"]
        if panne["type"] != "aucune":
            # Leave at least one action under the injected condition. A one-action
            # session injects at action 0, which the daemon applies immediately.
            latest = budget - 1
            start, end = (min(value, latest) for value in panne["apres_actions"])
            entree = {"type": panne["type"], "humains": hid,
                      "apres_actions": rng.randint(start, end)}
            if "duree" in panne:
                entree["duree"] = rng.randint(*panne["duree"])
            for cle, valeur in (panne.get("params") or {}).items():
                entree[cle] = rng.randint(*valeur) if (len(valeur) == 2 and all(isinstance(v, int) for v in valeur)) \
                    else rng.choice(valeur)
            pannes.append(entree)
            if panne.get("horloge"):
                fiche["horloge"] = True
        humains.append(fiche)
    from .reproducibility import draw_provenance
    personas = {"application": application, "escouade": escouade, "graine": graine, "budget": budget, "humains": humains}
    tirage = {"escouade": escouade, "graine": graine, "nombre": nombre, "budget": budget, "objectifs": objectifs, "pannes": pannes}
    personas["provenance"] = tirage["provenance"] = draw_provenance()
    personas["themes"] = tirage["themes"] = selected_themes
    tirage["sessions"] = {"mode": sessions, "shared": shared or [], "roles": [r[0] for r in roles or []]}
    tirage["checks"] = {"selection": checks, "countries": pays or "all", "pool": [check["id"] for check in pool],
                        "assigned": {h["id"]: [c["id"] for c in h["checks"]] for h in humains}}
    if fault_types is not None:
        tirage["fault_types"] = sorted(selected)
    return personas, tirage
