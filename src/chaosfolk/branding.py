"""Copy bundled companion artwork into portable local reports."""
import json
import shutil
from pathlib import Path


def report_branding(folder):
    source = Path(__file__).parent
    destination = Path(folder) / "assets"
    destination.mkdir(exist_ok=True)
    for name in ("mascot.png", "companions.png"):
        shutil.copyfile(source / "templates" / name, destination / name)
    profiles = json.loads((source / "profiles.json").read_text(encoding="utf-8"))["profils"]
    french = [
        ("Premier essai", "Découvre l'application"), ("Pressé", "Veut finir sans attendre"),
        ("Tout au clavier", "Navigue avec les touches"), ("Sur mobile", "Utilise son téléphone d'une main"),
        ("Lecteur attentif", "Lit avant d'agir"), ("Allergique au jargon", "Questionne les mots inconnus"),
        ("Distrait", "Interrompt souvent son parcours"), ("Pointilleux", "Vérifie chaque modification"),
        ("Prudent", "Cherche à éviter les erreurs"), ("Explorateur", "Essaie les chemins moins visibles"),
        ("Multitâche", "Travaille dans plusieurs onglets"), ("Attentif aux libellés", "S'appuie sur le texte"),
        ("Copier-coller", "Colle des textes aux formats variés"), ("Retour en arrière", "Revient pendant une saisie"),
        ("Recherche d'abord", "Commence par chercher et filtrer"), ("Récupération", "Essaie d'annuler et de reprendre"),
    ]
    return {"mascot": "assets/mascot.png", "skins": "assets/companions.png", "columns": 4, "rows": 4,
            "catalog": [{"skin": i, "name": p["nom"], "habits": p.get("habitudes", []),
                         "translations": {"fr": {"name": french[i][0], "habits": [french[i][1]]}}}
                        for i, p in enumerate(profiles)]}
