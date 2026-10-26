"""Draw personas and reachable fault schedules from user goals.

The seed, count, squad, objectives, jobs, catalog and action budget together
determine the draw. Browser exploration itself is not deterministic.
"""
import json
import random
from pathlib import Path

CATALOGUE = Path(__file__).resolve().parent / "profiles.json"
ESCOUADES = {"ux": "UX et ergonomie : compréhension, parcours, clavier, mobile, jargon, erreurs"}


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


def tirer_horde(escouade, nombre, objectifs, graine, application, metiers=None, budget=20):
    """Retourne (personas, tirage) : la fiche des humains et les pannes à programmer."""
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
        fiche = {
            "id": hid, "nom": nom, "age": rng.randint(22, 64), "metier": rng.choice(metiers),
            "profil": profil["nom"], "escouade": escouade,
            "profil_id": profil["id"], "skin": cat["profils"].index(profil),
            "aisance": rng.choice(profil["aisance"]), "patience": rng.choice(profil["patience"]),
            "appareil": appareil, "intention": intention, "objectifs": ordered_goals,
            "habitudes": profil["habitudes"], "manies": manies,
            "histoire": "First visit; no previous experience with this app",
        }
        panne = choisir_pondere(rng, cat["pannes"], [p["poids"] for p in cat["pannes"]])
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
    personas = {"application": application, "escouade": escouade, "graine": graine, "budget": budget, "humains": humains}
    tirage = {"escouade": escouade, "graine": graine, "nombre": nombre, "budget": budget, "objectifs": objectifs, "pannes": pannes}
    return personas, tirage
