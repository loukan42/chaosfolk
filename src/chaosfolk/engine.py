#!/usr/bin/env python3
"""Chaosfolk: simulated users, real browsers, reproducible failures.

  chaosfolk setup                         Install the browser and add the skill to your coding agents
  chaosfolk install-browser               Download Chromium for this installation
  chaosfolk check                         Check Python, Playwright and Chromium
  chaosfolk demo --lang en                Run the local deterministic demo
  chaosfolk launch --url URL --folder DIR --budget 20
  chaosfolk draw --count 4 --seed 42 --objectives "Create a task;Find a task" --folder DIR
  chaosfolk humans DIR/personas.json
  chaosfolk sheets --folder DIR --data "Synthetic data only" --forbidden "External actions"
  chaosfolk h01 look                      See the browser's current screen
  chaosfolk h01 help                      List browser actions
  chaosfolk analyze --folder DIR
  chaosfolk replay scenario.json --times 3 --with-control --fail-on-bug
  chaosfolk replay scenario.json --times 3 --persist reload,local-only,retry
  chaosfolk checks [--id phone-formats]   QA check catalog
  chaosfolk fields e0 --save DIR/fields.json   Classify a page's fields, list checks
  chaosfolk audit e0 --keyboard           Responsive, keyboard and WCAG signals
  chaosfolk vary scenario.json --field "Phone" --check phone-formats
  chaosfolk compare known.json unknown.json   Same outcome expected (enumeration)
  chaosfolk map --folder DIR --project NAME   Journey map and routes to explore
  chaosfolk campaign record|compare|select|status --project NAME
  chaosfolk chaos --help                 Optional injection controls and finite recurring jobs
  chaosfolk report --folder DIR --lang en|fr
  chaosfolk stop                          Close browsers and the managed app

Use --help after a command for options. The agent host supplies the simulated
users. The engine runs browsers and replays without a model API key.
Use CHAOSFOLK_HOME or --state-dir DIR to isolate concurrent engine sessions.
Only run against local or explicitly authorized test environments.
"""
import argparse
import fnmatch
import hmac
import json
import hashlib
import os
import re
import socket
import sys
import time
from contextlib import suppress
from datetime import datetime
from pathlib import Path

ICI = Path(__file__).resolve().parent
FICHIER_ACTIF = Path(os.environ.get("CHAOSFOLK_HOME", str(Path.home() / ".chaosfolk"))) / "active.json"
MODELE_RAPPORT = ICI / "templates" / "report.html"
ECRAN_JS = ICI / "screen.js"

# Modules lourds : chargés par charger_moteur() seulement pour les commandes du chef.
# Un geste d'humain ne passe que par le client (json, socket, argparse).
asyncio = subprocess = secrets = urllib_request = urllib_error = urljoin = urlparse = None


def charger_moteur():
    """Importe ce que seul le moteur utilise (asyncio, subprocess, urllib...)."""
    global asyncio, subprocess, secrets, urllib_request, urllib_error, urljoin, urlparse
    if asyncio is not None:
        return
    import asyncio as _asyncio
    import secrets as _secrets
    import subprocess as _subprocess
    import urllib.error as _erreur
    import urllib.request as _requete
    from urllib.parse import urljoin as _urljoin
    from urllib.parse import urlparse as _urlparse
    asyncio, subprocess, secrets = _asyncio, _subprocess, _secrets
    urllib_request, urllib_error, urljoin, urlparse = _requete, _erreur, _urljoin, _urlparse


# --------------------------------------------------------------------------
# Constantes : commandes
# --------------------------------------------------------------------------

COMMANDES_CHEF = {
    "check", "launch", "start", "serve", "humans", "fault", "faults", "fault-end", "status",
    "network", "stop", "stop-app", "save-state", "inspect", "analyze", "trace", "extract", "replay", "report",
    "draw", "drawn-faults", "sheets", "install-agent", "fields", "vary", "compare", "audit", "chaos-control", "release",
}
# commandes qui exigent le jeton du chef (un humain n'en a pas besoin et ne doit pas pouvoir les lancer).
# Le client ne l'envoie que si la variable d'environnement CHAOSFOLK_LEADER_TOKEN le porte : un humain qui lirait
# serveur.json n'obtient rien en lançant la commande sans elle
COMMANDES_RESERVEES = {"stop", "fault", "fault-end", "inspect", "save-state", "humans", "audit", "chaos-control", "release"}
COMMANDES_LOURDES = {"check", "launch", "start", "serve", "stop-app", "analyze", "trace", "extract", "replay", "report",
                     "vary", "compare"}
# "draw" ne charge que tirage.py ; "drawn-faults" et "sheets" n'ont besoin que du client
GESTES = {
    "goto", "click", "type", "select", "tick", "key", "hover", "scroll",
    "back", "forward", "reload", "tab", "wait", "accept", "dismiss", "upload",
}
PAROLES = {"think", "flag", "giveup", "done", "check-start", "check-result"}
FINS = {"giveup", "done"}
BOITE = {"accept", "dismiss"}
GESTES_COMPTES = GESTES - {"wait"}
ACTIONS = GESTES | PAROLES | {"look", "help"}
NAVIGATION = {"goto", "reload", "back", "forward", "tab"}
TOUCHES_NAVIGATION = {"Tab", "PageUp", "PageDown", "Home", "End"}

APPAREILS = {
    "desktop": {"viewport": {"width": 1440, "height": 900}},
    "laptop": {"viewport": {"width": 1280, "height": 720}},
    "tablet": {"viewport": {"width": 820, "height": 1180}, "is_mobile": True, "has_touch": True,
                 "device_scale_factor": 2},
    "mobile": {"viewport": {"width": 390, "height": 844}, "is_mobile": True, "has_touch": True,
               "device_scale_factor": 3,
               "user_agent": "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 "
                             "(KHTML, like Gecko) Chrome/126.0 Mobile Safari/537.36"},
}
CANAUX = (None, "msedge", "chrome")

# Anciens mots français, encore présents dans les anciens fichiers (journal, personas, scénarios,
# tirage). Ils sont traduits à la lecture. En ligne de commande, seul l'anglais est accepté.
ALIAS_ACTIONS = {
    "voir": "look", "aller": "goto", "cliquer": "click", "saisir": "type", "choisir": "select",
    "cocher": "tick", "touche": "key", "survoler": "hover", "defiler": "scroll", "retour": "back",
    "avancer": "forward", "recharger": "reload", "onglet": "tab", "attendre": "wait",
    "accepter": "accept", "refuser": "dismiss", "deposer": "upload", "penser": "think",
    "signaler": "flag", "abandonner": "giveup", "fin": "done", "aide": "help",
}
ALIAS_PANNES = {
    "hors-ligne": "offline", "lenteur": "slow", "serveur-coupe": "server-down", "app-arret": "app-stop",
    "erreur-http": "http-error", "reponse-perdue": "lost-response", "stockage-plein": "storage-full",
    "stockage-vide": "storage-empty", "stockage-corrompu": "storage-corrupt", "horloge": "clock",
    "fenetre": "window", "cookies-vides": "cookies-cleared",
}
ALIAS_APPAREILS = {"ordinateur": "desktop", "portable": "laptop", "tablette": "tablet"}
ALIAS_ATTENDU = {
    "texte-visible": "text-visible", "texte-absent": "text-absent", "compte": "count",
    "aucune-erreur-page": "no-page-error", "page-non-blanche": "page-not-blank", "stockage": "storage",
    "url-contient": "url-contains",
}
ALIAS_SENS = {"bas": "down", "haut": "up", "droite": "right", "gauche": "left", "debut": "top", "fin": "bottom"}
ALIAS_ONGLET = {"nouveau": "new", "fermer": "close"}
ALIAS_GRAVITE = {"bloquant": "blocking", "genant": "annoying", "gênant": "annoying", "mineur": "minor"}
# anciennes commandes du chef : refusées en ligne de commande, avec le nom qui les remplace
ANCIENNES_COMMANDES_CHEF = {
    "verifier": "check", "demarrer": "launch", "serveur": "serve", "humains": "humans", "panne": "fault",
    "pannes": "faults", "panne-fin": "fault-end", "bilan": "status", "reseau": "network", "arreter": "stop",
    "etat-sauver": "save-state", "inspecter": "inspect", "analyser": "analyze", "extraire": "extract",
    "rejouer": "replay", "rapport": "report", "tirer": "draw", "pannes-tirees": "drawn-faults", "aide": "help",
}
ANCIENNES_OPTIONS = {
    "--pense": "--thought", "--dit": "--say", "--humeur": "--mood", "--fois": "--times", "--droit": "--right",
    "--lent": "--slow", "--ajouter": "--append", "--entree": "--enter", "--decocher": "--uncheck",
    "--complet": "--full", "--gravite": "--severity", "--humains": "--humans", "--a": "--at",
    "--apres-actions": "--after-actions", "--duree": "--duration", "--motif": "--pattern",
    "--methode": "--method", "--statut": "--status", "--delai": "--delay", "--cle": "--key",
    "--avance": "--advance", "--taille": "--size", "--dossier": "--folder", "--app-commande": "--app-command",
    "--app-dossier": "--app-folder", "--app-attente": "--app-wait", "--canal": "--channel",
    "--inactivite": "--idle", "--duree-humain": "--human-duration", "--duree-max": "--max-duration",
    "--objectifs": "--objectives", "--metiers": "--jobs", "--application": "--app-name",
    "--nombre": "--count", "--graine": "--seed", "--escouade": "--squad", "--sortie": "--output",
    "--temoin": "--control", "--avec-temoin": "--with-control", "--sequentiel": "--sequential",
    "--nom": "--name", "--jusqu-a": "--up-to", "--garder-app": "--keep-app",
}


def alias(valeur, table):
    """Mot anglais d'un ancien mot français (inchangé s'il est déjà en anglais ou inconnu)."""
    return table.get(valeur, valeur) if isinstance(valeur, str) else valeur


def normaliser_evenement(e):
    """Événement du journal : actions, pannes et gravités ramenées aux mots anglais (anciens journaux)."""
    if not isinstance(e, dict):
        return e
    if "action" in e:
        e["action"] = alias(e["action"], ALIAS_ACTIONS)
    if "panne" in e:
        e["panne"] = alias(e["panne"], ALIAS_PANNES)
    if "gravite" in e:
        e["gravite"] = alias(e["gravite"], ALIAS_GRAVITE)
    args = e.get("args")
    if isinstance(args, dict):
        normaliser_args(args)
    return e


def normaliser_args(args):
    """Arguments d'un geste : valeurs de sens (scroll), quoi (tab) et gravite ramenées à l'anglais."""
    if "sens" in args:
        args["sens"] = alias(args["sens"], ALIAS_SENS)
    if "quoi" in args:
        args["quoi"] = alias(args["quoi"], ALIAS_ONGLET)
    if "gravite" in args:
        args["gravite"] = alias(args["gravite"], ALIAS_GRAVITE)
    return args


def normaliser_scenario(sc):
    """Scénario (ancien ou nouveau) : gestes, pannes, appareil et attendus en anglais. Renvoie le scénario."""
    if "appareil" in sc:
        sc["appareil"] = alias(sc["appareil"], ALIAS_APPAREILS)
    for etape in sc.get("etapes") or []:
        etape["action"] = alias(etape.get("action"), ALIAS_ACTIONS)
        if isinstance(etape.get("args"), dict):
            normaliser_args(etape["args"])
    for panne in sc.get("pannes") or []:
        panne["type"] = alias(panne.get("type"), ALIAS_PANNES)
    for regle in valider_attendu(sc.get("attendu")):
        regle["type"] = alias(regle.get("type"), ALIAS_ATTENDU)
    return sc


def refus_ancien_mot(ancien, nouveau, genre):
    """Quitte en donnant le mot anglais qui remplace un ancien mot français."""
    raise SystemExit(f'"{ancien}" ({genre}) s\'appelle maintenant "{nouveau}" '
                     "(liste des commandes : chaosfolk help)")


def refuser_anciens_mots(argv):
    """Quitte avec un message si la ligne de commande utilise un ancien mot français (commande, option,
    type de panne, sens, onglet, gravité). Le message donne le mot qui le remplace.
    Les options ne sont vérifiées ici que pour les commandes du chef : le texte d'un humain peut commencer
    par un tiret (type r3 "-5 %"), commande_humain ne refuse une ancienne option que si elle ne peut pas être un texte."""
    if argv and argv[0] in ANCIENNES_COMMANDES_CHEF:
        refus_ancien_mot(argv[0], ANCIENNES_COMMANDES_CHEF[argv[0]], "commande")
    if len(argv) > 1 and argv[0] not in COMMANDES_CHEF and argv[1] in ALIAS_ACTIONS and argv[1] not in ACTIONS:
        refus_ancien_mot(argv[1], ALIAS_ACTIONS[argv[1]], "commande")
    if argv and argv[0] in COMMANDES_CHEF:
        for jeton in argv:
            nom = jeton.split("=", 1)[0]
            if nom in ANCIENNES_OPTIONS:
                refus_ancien_mot(nom, ANCIENNES_OPTIONS[nom], "option")
    if len(argv) > 1 and argv[0] == "fault" and argv[1] in ALIAS_PANNES:
        refus_ancien_mot(argv[1], ALIAS_PANNES[argv[1]], "type de panne")
    for i, jeton in enumerate(argv[:-1]):
        if jeton == "--severity" and argv[i + 1] in ALIAS_GRAVITE:
            refus_ancien_mot(argv[i + 1], ALIAS_GRAVITE[argv[i + 1]], "valeur de gravité")
    if len(argv) > 2 and argv[0] not in COMMANDES_CHEF:
        if argv[1] == "scroll" and argv[2] in ALIAS_SENS:
            refus_ancien_mot(argv[2], ALIAS_SENS[argv[2]], "valeur de sens")
        if argv[1] == "tab" and argv[2] in ALIAS_ONGLET:
            refus_ancien_mot(argv[2], ALIAS_ONGLET[argv[2]], "valeur d'onglet")


BRUIT_DEV = (r"\[vite\]", r"Vite server", r"wss?://localhost[^ ]*token=", r"/@vite/", r"\[hmr\]")

# --------------------------------------------------------------------------
# Constantes : garde-fous. La horde cherche des défauts, elle ne s'acharne pas dessus.
# Un défaut est attendu ; il se signale une fois, puis l'humain passe à autre chose.
# --------------------------------------------------------------------------

REPETITIONS_MAX = 2      # au 3e geste identique sans effet, le geste est refusé
MARGE_BUDGET = 5         # gestes tolérés au-delà du budget, puis refus
ALERTE_BUDGET = 5        # alerte quand il reste ce nombre de gestes
ECRAN_FIGE = 3           # gestes de suite sans changement avant l'alerte
ATTENTE_MAX = 60         # secondes d'attente cumulées par humain
ATTENTE_UNITAIRE = 10    # une attente ne dépasse pas cette durée, en secondes
RESEAU_KO_MAX = 3        # échecs réseau d'affilée avant une pause imposée
PAUSE_RESEAU = 20        # secondes pendant lesquelles la navigation est refusée
ERREURS_RESEAU = ("ne répond pas", "connexion refusée", "pas de connexion internet", "ne répond plus")
ESSAI_MAX = 150          # durée minimale accordée à un essai de rejeu, en secondes
MARGE_ARRET = 180        # le serveur s'arrête seul ce nombre de secondes après la durée maximale

# délais maximaux : rien ne doit pouvoir bloquer quand une boîte du navigateur est ouverte
DELAI_PAGE = 5           # secondes, une lecture ou une écriture dans la page
DELAI_LECTURE = 10       # secondes, la lecture de l'écran
DELAI_PANNE = 20         # secondes, l'application d'une panne
DELAI_VERROU = 20        # secondes d'attente du verrou d'un humain avant d'agir sans lui
DELAI_EXECUTION = 40     # secondes, un geste (navigation comprise)
DELAI_EXECUTION_LENT = 90  # secondes, un geste de saisie lente
DELAI_GESTE_MS = 5000    # millisecondes avant de déclarer un geste impossible (rejeu, panne réseau)
DELAI_GESTE_HUMAIN_MS = 2000  # idem pour un geste d'humain sans panne réseau
DELAI_NAVIGATION_MS = 30000
DELAI_HISTORIQUE_MS = 15000
HYDRATATION_MAX = 5.0    # secondes d'attente d'une page interactive (chargement puis réseau calme)
HYDRATATION_RESEAU_MAX = 1.5  # idem pendant une panne réseau
CALME_MS = 250           # silence du DOM qui vaut calme (rejeu, et saisie d'un humain)
CALME_NAVIGATION_MS = 100  # après une navigation d'humain (la page a déjà attendu le réseau calme)
CALME_GESTE_MS = 150     # après les autres gestes d'humain
CALME_MAX_MS = 1500
TOUCHES_FOIS_MAX = 20    # key --times N : N au plus
REJEUX_SIMULTANES = 12   # essais de rejeu ouverts en même temps (tous scénarios confondus)
PLAYWRIGHT_MIN = (1, 63)
PYTHON_MIN = (3, 12)
LIGNES_ECRAN = 170
LIGNES_ECRAN_COMPLET = 300
LIGNES_TRACE_ECRAN = 40  # lignes d'écran montrées par trace --around
AGENT_HUMAIN = "chaosfolk-user"  # agent dédié aux humains : <skill>/agents/horde-humain.md, copié par install-agent
LIGNES_JOURNAL = 60      # lignes d'écran gardées dans le journal
LIGNES_REPLI_MIN = 4     # nombre de lignes identiques qui valent un repli
LIMITE_LIGNE = 16 * 1024 * 1024  # taille maximale d'une requête du client
REFS_MEMOIRE_MAX = 3000

PANNES_RESEAU = {"server-down", "http-error", "lost-response", "slow"}
PANNES_DUREE = PANNES_RESEAU | {"offline", "storage-full"}
PANNES_INSTANT = {"storage-empty", "storage-corrupt", "clock", "window", "cookies-cleared"}
PANNES_GLOBALES = {"app-stop"}
PANNES = PANNES_DUREE | PANNES_INSTANT | PANNES_GLOBALES
PARAMS_PANNE = ("motif", "methode", "statut", "delai", "fois", "cle", "avance", "taille")

AIDE_HUMAIN = f"""Commandes (toujours : chaosfolk <toi> <commande> ...) :
  look [--full]                     regarder l'écran (texte), --full pour une page longue
  goto <adresse>                    taper une adresse (/offers ou http://...)
  click <ref> [--double] [--times N] [--right]    <ref> : le code [rN] ou le libellé exact
  type <ref> "<texte>" [--slow] [--append] [--enter]
  select <ref> "<option>"           dans une liste déroulante
  tick <ref> [--uncheck]
  key <Touche> [--times N]          Enter, Escape, Tab, Shift+Tab, Control+a, ArrowDown... (N au plus {TOUCHES_FOIS_MAX})
  hover <ref>
  scroll [down|up|right|left|top|bottom]
  back | forward | reload           boutons du navigateur
  tab new [adresse]                 ouvre un onglet (sans adresse : la même page)
  tab <n> | tab close               changer d'onglet, fermer l'onglet courant
  wait <secondes>                   ne rien faire (max {ATTENTE_UNITAIRE})
  accept ["texte"] | dismiss        répondre à une boîte du navigateur
  upload <ref> <chemin>             joindre un fichier (du dossier de la horde)
  think                             seulement penser ou parler (avec --thought / --say)
  flag "<ce qui ne va pas>" [--severity blocking|annoying|minor]
  giveup "<pourquoi>"               tu laisses tomber ta mission
  done "<ton bilan>"                tu as fini
À chaque commande : --thought "la réaction de ton personnage" ; --say "ce que tu dis" et --mood <mot> quand ils changent
"""

MESSAGE_RESERVEE = ("commande réservée au chef d'orchestre : préfixer par CHAOSFOLK_LEADER_TOKEN=<jeton> (affiché par launch).")

RE_REF = re.compile(r"\[?(r\d+)\]?")
RE_REFS = re.compile(r"\[(r\d+)\]")
RE_PANNE_NUM = re.compile(r"^p(\d+)")


# --------------------------------------------------------------------------
# Scripts injectés dans la page (la lecture de l'écran est dans ecran.js)
# --------------------------------------------------------------------------

# calme : le DOM ne bouge plus depuis o.calme ms et, si o.requetes, aucun fetch ni xhr n'est en vol (borné par o.max)
CALME_JS = r"""
(o) => new Promise(res => {
  let dernier = Date.now(); const debut = Date.now();
  const mo = new MutationObserver(() => { dernier = Date.now(); });
  try { mo.observe(document, {subtree: true, childList: true, characterData: true}); } catch (e) { res(false); return; }
  const enVol = () => o.requetes && (window.__hordeEnVol || 0) > 0;
  const tic = () => { const t = Date.now(); if ((t - dernier >= o.calme && !enVol()) || t - debut >= o.max) { mo.disconnect(); res(true); } else setTimeout(tic, 50); };
  setTimeout(tic, 50);
})
"""

# script d'initialisation de chaque page : stockage plein à la demande, et compte des fetch et xhr en vol
INIT_JS = r"""
(() => {
  const origine = Storage.prototype.setItem;
  Storage.prototype.setItem = function (k, v) {
    if (window.__hordeQuota) { throw new DOMException("Failed to execute 'setItem' on 'Storage': exceeded the quota.", 'QuotaExceededError'); }
    return origine.call(this, k, v);
  };
  let enVol = 0;
  const fin = () => { enVol = Math.max(0, enVol - 1); };
  try { Object.defineProperty(window, '__hordeEnVol', {get: () => enVol, configurable: true}); } catch (e) { return; }
  const fetchOrigine = window.fetch;
  if (typeof fetchOrigine === 'function') {
    window.fetch = function (...args) {
      enVol++;
      let promesse;
      try { promesse = fetchOrigine.apply(this, args); } catch (e) { fin(); throw e; }
      Promise.resolve(promesse).then(fin, fin);
      return promesse;
    };
  }
  const envoi = XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.send = function (...args) {
    enVol++;
    this.addEventListener('loadend', fin, {once: true});
    try { return envoi.apply(this, args); } catch (e) { fin(); throw e; }
  };
})();
"""

CORROMPRE_JS = r"""
(motif) => {
  const re = new RegExp('^' + motif.replace(/[.+^${}()|[\]\\]/g, '\\$&').replace(/\*/g, '.*').replace(/\?/g, '.') + '$');
  const touchees = [];
  for (let i = 0; i < localStorage.length; i++) {
    const cle = localStorage.key(i);
    if (re.test(cle)) touchees.push(cle);
  }
  for (const cle of touchees) { const v = localStorage.getItem(cle) || ''; localStorage.setItem(cle, v.slice(0, Math.floor(v.length / 2))); }
  return touchees;
}
"""

_script_ecran = []


def script_ecran():
    """Texte de ecran.js, lu une seule fois."""
    if not _script_ecran:
        _script_ecran.append(ECRAN_JS.read_text(encoding="utf-8"))
    return _script_ecran[0]


# --------------------------------------------------------------------------
# Outils communs
# --------------------------------------------------------------------------

def utf8():
    """Console en UTF-8, pour que les accents passent sous Windows."""
    for flux in (sys.stdout, sys.stderr):
        with suppress(Exception):
            flux.reconfigure(encoding="utf-8", errors="replace")


def premiere_ligne(erreur, n=300):
    """Première ligne du message d'une exception, jamais vide (au pire le nom de l'exception)."""
    lignes = str(erreur).splitlines()
    return (lignes[0] if lignes and lignes[0] else type(erreur).__name__)[:n]


def lire_json(chemin, defaut=None):
    """Lit un JSON (avec ou sans BOM). Fichier absent, vide ou `null` : renvoie `defaut`."""
    from .private_state import read_json
    try:
        donnees = read_json(chemin, encoding="utf-8-sig")
    except FileNotFoundError:
        return defaut
    except json.JSONDecodeError as e:
        raise ValueError(f"JSON illisible : {Path(chemin).as_posix()} ({e})") from e
    return defaut if donnees is None else donnees


def ecrire_json(chemin, donnees):
    """Écrit un JSON d'un coup (fichier temporaire puis remplacement) : jamais lu à moitié."""
    from .private_state import write_json
    write_json(chemin, donnees)


def iterer_journal(dossier, obligatoire=True):
    """Yield normalized events without retaining the journal or its source lines."""
    fichier = Path(dossier) / "journal.jsonl"
    try:
        source = fichier.open(encoding="utf-8", errors="replace")
    except FileNotFoundError:
        if obligatoire:
            raise SystemExit(f"pas de journal dans {dossier}")
        return
    # errors="replace" : une ligne coupée en plein caractère (arrêt brutal) est ignorée, pas un plantage
    with source:
        for ligne in source:
            with suppress(json.JSONDecodeError):
                e = json.loads(ligne)
                if isinstance(e, dict) and "type" in e:
                    yield normaliser_evenement(e)


def lire_journal(dossier, obligatoire=True):
    """Événements du journal.jsonl d'une horde (les lignes illisibles sont ignorées)."""
    return list(iterer_journal(dossier, obligatoire))


def lire_personas(dossier):
    """Fiches des humains d'une horde, par identifiant."""
    donnees = lire_json(Path(dossier) / "personas.json", {})
    return {h["id"]: h for h in donnees.get("humains", []) if isinstance(h, dict) and h.get("id")}


def duree_ms(texte):
    """'72h', '3j', '15min', '90s', '1500ms' ou un nombre de secondes."""
    m = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*(ms|s|min|h|j|d)?\s*", str(texte))
    if not m:
        raise ValueError(f"durée illisible : {texte}")
    n, unite = float(m.group(1)), (m.group(2) or "s")
    return int(n * {"ms": 1, "s": 1000, "min": 60000, "h": 3600000, "j": 86400000, "d": 86400000}[unite])


def est_eclaireur(hid):
    """Les éclaireurs (identifiants en 'e') font la reconnaissance : ni budget ni durée par défaut."""
    return str(hid).startswith("e")


def chemin_relatif(chemin, base):
    """Chemin relatif à `base` en séparateurs `/` (le chemin lui-même s'il est ailleurs)."""
    try:
        return Path(chemin).resolve().relative_to(Path(base).resolve()).as_posix()
    except ValueError:
        return Path(chemin).as_posix()


def sous_dossier(chemin, base, quoi):
    """Chemin absolu de `chemin` (relatif à `base`) s'il est sous `base`, sinon ValueError."""
    base = Path(base).resolve()
    complet = (base / chemin).resolve()
    try:
        complet.relative_to(base)
    except ValueError:
        raise ValueError(f"{quoi} refusé : il doit se trouver dans le dossier de la horde ({base.as_posix()})") from None
    return complet


def adresse_http(url, base):
    """Adresse absolue (relative à `base`) ; seuls http et https sont permis."""
    complete = urljoin(base, str(url))
    if urlparse(complete).scheme not in ("http", "https"):
        raise ValueError(f"adresse refusée : seuls http et https sont permis ({url})")
    return complete


def fichier_televersable(chemin, dossier):
    """Seuls les fixtures explicitement déposés dans uploads/ peuvent quitter le poste."""
    autorise = sous_dossier("uploads", dossier, "dossier de téléversement")
    fichier = sous_dossier(chemin, dossier, "fichier")
    try:
        fichier.relative_to(autorise)
    except ValueError:
        raise ValueError("téléversement refusé : placer une donnée fictive dans uploads/") from None
    if not fichier.is_file():
        raise ValueError("téléversement refusé : fichier absent")
    return fichier


def chemin_msys(texte):
    """Git Bash sous Windows transforme '/offres' en 'C:/Program Files/Git/offres' : on l'annule."""
    m = re.match(r"^[A-Za-z]:[\\/](?:[^\\/]+[\\/])*?Git[\\/](.*)$", str(texte))
    return "/" + m.group(1).replace("\\", "/") if m else texte


def est_touche_navigation(touche):
    """Flèches, Tab, Page, Home, End (seuls ou en suite) : des touches qu'on répète légitimement."""
    parties = str(touche).split()
    return bool(parties) and all(
        p.split("+")[-1] in TOUCHES_NAVIGATION or p.split("+")[-1].startswith("Arrow") for p in parties)


def traduire_erreur(erreur):
    """Message d'une exception de Playwright, dit simplement à l'humain."""
    s = str(erreur)
    if asyncio is not None and isinstance(erreur, asyncio.TimeoutError) and not s:
        return "la page ne répond pas (une boîte du navigateur est peut-être ouverte)"
    if "intercepts pointer events" in s:
        return "le clic ne passe pas, quelque chose recouvre l'élément"
    if "not enabled" in s or "disabled" in s:
        return "l'élément est désactivé"
    if "not editable" in s or "readonly" in s.lower():
        return "on ne peut pas écrire dans ce champ"
    if "not visible" in s or "outside of the viewport" in s:
        return "l'élément n'est pas visible"
    if "timeout" in s.lower():
        m = re.search(r"Timeout (\d+)ms", s)
        secondes = f" en {int(m.group(1)) // 1000} s" if m else ""
        return f"rien ne se passe (le navigateur n'a pas pu faire le geste{secondes})"
    if "net::ERR_INTERNET_DISCONNECTED" in s:
        return "pas de connexion internet"
    if "ERR_CONNECTION" in s:
        return "le site ne répond pas (connexion refusée)"
    if "Target page, context or browser has been closed" in s:
        return "l'onglet est fermé"
    return premiere_ligne(erreur, 200)


def jeton_egal(candidat, attendu):
    """Constant-time token comparison; non-string candidates never match."""
    return isinstance(candidat, str) and hmac.compare_digest(candidat.encode("utf-8"), attendu.encode("utf-8"))


def nom_de_fichier_sur(nom):
    """Base name only: the tested site chooses the suggested name, never the destination folder."""
    base = Path(str(nom or "").replace("\\", "/")).name
    base = base.strip().strip(".") or "download"
    return base[:150]


def url_repond(url, delai=3):
    """True si quelque chose répond sur l'adresse (hors proxy du système, sans suivre les redirections)."""
    class SansRedirection(urllib_request.HTTPRedirectHandler):
        def redirect_request(self, *args, **kwargs):
            return None  # A 3xx answer proves the address responds; never follow it to another host.
    ouvreur = urllib_request.build_opener(urllib_request.ProxyHandler({}), SansRedirection)
    try:
        with ouvreur.open(url, timeout=delai) as r:
            return r.status < 500
    except urllib_error.HTTPError as e:
        return e.code < 500
    except Exception:
        return False


def attendre_url(url, secondes, processus=None):
    """Attend que l'adresse réponde. Renvoie (ok, raison) ; s'arrête si le processus lancé est mort."""
    fin = time.time() + secondes
    while time.time() < fin:
        if url_repond(url):
            return True, ""
        if processus is not None and processus.poll() is not None:
            return False, f"l'application s'est arrêtée au démarrage (code {processus.returncode}), voir app.log"
        time.sleep(0.25)
    return False, f"l'application ne répond pas sur {url} après {secondes} s"


def options_detache():
    """Options de subprocess pour un processus qui survit à son parent, sans fenêtre console."""
    if os.name == "nt":
        indicateurs = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
        return {"creationflags": indicateurs}
    return {"start_new_session": True}


def etat_playwright(etat, url_app, base=None):
    """État de départ d'un navigateur. Accepte le format Playwright (cookies, origins), ou le
    format simple {"localStorage": {cle: valeur}, "cookies": [...]}. Le sessionStorage n'est pas pris
    en charge par Playwright : il est ignoré. Un chemin de fichier absent est une erreur claire."""
    if etat is None:
        return None
    if isinstance(etat, (str, Path)):
        fichier = Path(base or ".") / etat
        donnees = lire_json(fichier)
        if donnees is None:
            raise ValueError(f"fichier d'état introuvable : {fichier.as_posix()}")
        etat = donnees
    if "origins" in etat:
        return etat
    adresse = urlparse(url_app)
    stockage = [{"name": cle, "value": v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)}
                for cle, v in (etat.get("localStorage") or {}).items()]
    return {"cookies": etat.get("cookies", []),
            "origins": [{"origin": f"{adresse.scheme}://{adresse.netloc}", "localStorage": stockage}]}


async def borne(coroutine, delai=DELAI_PAGE):
    """Attend une coroutine au plus `delai` secondes (une boîte du navigateur ouverte bloque Playwright)."""
    return await asyncio.wait_for(coroutine, delai)


async def lancer_navigateur(pw, visible=False, canal=None):
    """Launch the requested engine; an explicit engine never falls back silently."""
    if canal in ("firefox", "webkit"):
        try:
            return await getattr(pw, canal).launch(headless=not visible), canal
        except Exception as error:
            raise RuntimeError(f"{canal} could not start. Install it with python -m playwright install {canal}: {error}") from error
    derniere = None
    for essai in ([canal] if canal else CANAUX):
        try:
            if essai in (None, "chromium"):
                return await pw.chromium.launch(headless=not visible), "chromium"
            return await pw.chromium.launch(headless=not visible, channel=essai), essai
        except Exception as e:
            derniere = e
    raise RuntimeError(f"aucun navigateur Chromium, Edge ou Chrome utilisable : {derniere}")


async def tester_navigateur():
    from playwright.async_api import async_playwright
    async with async_playwright() as pw:
        try:
            navigateur, canal = await lancer_navigateur(pw)
        except RuntimeError:
            return None, None
        version = navigateur.version
        await navigateur.close()
        return canal, version


async def nouveau_monde(navigateur, hid, fiche, url, base, **monde):
    """Crée le navigateur isolé d'un humain (ou d'un rejeu). `fiche` : appareil, etat, horloge.
    Lève ValueError si l'appareil est inconnu ou si le fichier d'état est absent."""
    nom_appareil = alias(fiche.get("appareil") or "desktop", ALIAS_APPAREILS)
    if nom_appareil not in APPAREILS:
        raise ValueError(f"appareil inconnu : {nom_appareil} (valeurs permises : {', '.join(APPAREILS)}). "
                         "Le contexte libre (par exemple téléphone dans le train) va dans le champ contexte.")
    etat = etat_playwright(fiche.get("etat"), url, base)
    ctx = await navigateur.new_context(
        locale=fiche.get("locale", "en-US"), timezone_id=fiche.get("timezone", "UTC"),
        ignore_https_errors=bool(fiche.get("ignore_https_errors", False)), storage_state=etat,
        accept_downloads=True, **APPAREILS[nom_appareil])
    m = None
    try:
        await ctx.add_init_script(script=INIT_JS)
        m = Monde(hid, ctx, url, **monde)
        if fiche.get("horloge"):
            await m.installer_horloge()
        return m
    except BaseException:
        with suppress(Exception):
            if m is not None:
                await m.fermer()
            else:
                await asyncio.wait_for(ctx.close(), 10)
        raise


# --------------------------------------------------------------------------
# Monde d'un humain : son navigateur, ses onglets, les pannes qu'il subit
# --------------------------------------------------------------------------

def panne_vise(panne, requete, origine):
    """True si la panne s'applique à cette requête (motif, méthode, type de ressource, origine)."""
    motif, methode = panne.get("motif"), panne.get("methode")
    type_panne = panne["type"]
    if motif:
        if not fnmatch.fnmatch(requete.url, motif):
            return False
    else:
        if type_panne in ("http-error", "lost-response") and requete.resource_type not in ("fetch", "xhr"):
            return False
        # sans motif, la lenteur ne retarde que les pages et les données : retarder chaque module JavaScript
        # d'une application en développement (des centaines) rendrait la page inutilisable, pas lente
        if type_panne == "slow" and requete.resource_type not in ("document", "fetch", "xhr"):
            return False
        if type_panne == "server-down" and urlparse(requete.url).netloc != origine:
            return False
        # sans motif ni méthode, la réponse perdue ne vise que les écritures
        if type_panne == "lost-response" and not methode and requete.method.upper() == "GET":
            return False
    return not methode or requete.method.upper() == methode.upper()


def code_http(panne):
    """Code HTTP de la panne http-error (option --status), 500 par défaut."""
    try:
        return int(panne.get("statut") or panne.get("statut_http") or 500)
    except (TypeError, ValueError):
        return 500


def methodes_visees(panne):
    """Méthodes HTTP touchées par une panne réseau, pour l'affichage."""
    if panne.get("methode"):
        return panne["methode"].upper()
    if panne["type"] == "lost-response" and not panne.get("motif"):
        return "écritures (GET exclu)"
    return "toutes"


class Monde:
    """Le navigateur isolé d'un humain : onglets, boîtes, pannes subies, compteurs des garde-fous."""

    def __init__(self, hid, ctx, url_app, journal=None, captures=None, dossier=None, evidence_dir=None):
        self.id = hid
        self.ctx = ctx
        self.closed = False
        self.releasing = False
        self.released_state = None
        self.url_app = url_app
        self.origine = urlparse(url_app).netloc
        self.journal = journal or (lambda e: None)
        self.captures = captures          # dossier des captures (None : pas de capture)
        self.dossier = dossier            # dossier de la horde (fichiers à déposer)
        # onglets
        self.pages = []
        self.onglet = 0                   # index de l'onglet courant
        # pannes subies
        self.pannes = []                  # pannes actives (dict)
        self.apres = []                   # pannes instantanées déjà appliquées (identifiants)
        self.globales = []                # pannes qui touchent tout le monde (application arrêtée)
        self.route_posee = False
        self.quota = False
        self.quota_init = None            # script d'initialisation de storage-full, à retirer à la fin
        self.horloge = False
        # boîtes du navigateur (alert, confirm, prompt, beforeunload)
        self.dialogue = None
        self.evt_dialogue = asyncio.Event()
        self.tache_suspendue = None
        # ce que le navigateur annonce à l'humain
        from .evidence import EvidenceStore
        evidence_dir = evidence_dir if evidence_dir is not None else (Path(dossier) / "evidence" if dossier else None)
        self.evidence = EvidenceStore(evidence_dir, hid, self._evidence_spilled)
        self.erreurs_page = self.evidence.errors
        self.messages = self.evidence.messages
        self.requetes = self.evidence.requests
        self.evidence_failed = False
        self.fermeture = None             # fermeture en cours (partagée entre appels concurrents)
        self.attentes_fermeture = set()   # tâches qui attendent cette fermeture
        self.taches = set()
        self.delai_geste = DELAI_GESTE_MS
        # références [rN] : mémoire par page, pour ne jamais redonner une référence à un autre élément
        self.refs = {}
        self.ecrans = {}                  # dernier écran lu, par page
        # session de l'humain (renseignée par la horde)
        self.n = 0                        # actions (voir et paroles comprises)
        self.n_gestes = 0                 # gestes sur la page (look, think, wait exclus)
        self.statut = "en cours"
        self.humeur = ""
        self.signalements = 0
        self.dernier = time.time()
        self.debut_reel = None
        self.budget = None                # gestes permis (None : pas de limite)
        self.duree = None                 # secondes permises (None : pas de limite)
        # compteurs des garde-fous
        self.repetitions = 0
        self.dernier_cle = None
        self.dernier_inutile = False
        self.sans_changement = 0
        self.ko_reseau = 0
        self.bloque_jusqua = 0.0
        self.attente = 0.0
        self.refus = 0
        # réponses aux humains
        self.derniere_sortie_complete = False
        self.vues = set()                 # lignes déjà données en entier : elles se replient ensuite
        self.derniere_capture = None
        self.dernier_titre = None         # titre de page donné dans le dernier en-tête
        self.dernier_complet = None       # (page, lignes) du dernier look --full donné en entier
        ctx.on("page", self._nouvelle_page)

    # -- tâches de fond --
    def lancer(self, coroutine):
        """Lance une tâche de fond en la gardant (Python peut sinon la ramasser avant la fin)."""
        tache = asyncio.ensure_future(coroutine)
        self.taches.add(tache)
        tache.add_done_callback(self.taches.discard)
        return tache

    async def fermer(self):
        """Close browser resources while retaining recorded counters and evidence."""
        if self.closed:
            self.evidence.close()
            return
        # Concurrent callers (evidence failure, release, horde stop) share one
        # close; a waiting caller is never cancelled by the close it waits for.
        current = asyncio.current_task()
        self.attentes_fermeture.add(current)
        try:
            if self.fermeture is None:
                self.fermeture = asyncio.ensure_future(self._fermer())
            await asyncio.shield(self.fermeture)
        finally:
            self.attentes_fermeture.discard(current)

    async def _fermer(self):
        tasks = set(self.taches) - {asyncio.current_task()} - self.attentes_fermeture
        if self.tache_suspendue is not None:
            tasks.add(self.tache_suspendue)
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        try:
            await asyncio.wait_for(self.ctx.close(), 10)
            self.closed = True
            self.ctx = None
            self.taches.clear()
            self.tache_suspendue = self.dialogue = None
            self.pages.clear()
            self.refs.clear()
            self.ecrans.clear()
            self.vues.clear()
            self.dernier_complet = None
        finally:
            self.fermeture = None
            self.evidence.close()

    def _evidence_spilled(self, details):
        details = dict(details, path=chemin_relatif(details["path"], self.dossier) if self.dossier else details["path"])
        self.journal({"type": "evidence-spilled", "h": self.id, **details})

    def _record_evidence(self, operation, *args):
        """A disk error stops collection visibly instead of dropping records unnoticed."""
        try:
            operation(*args)
        except Exception as error:
            if not self.evidence_failed:
                self.evidence_failed = True
                async def stop_collection():
                    with suppress(Exception):
                        await self.fermer()
                self.lancer(stop_collection())
                with suppress(Exception):
                    self.journal({"type": "evidence-storage-error", "h": self.id, "message": premiere_ligne(error),
                                  "collection_stopped": True})

    # -- pages et événements --
    def _nouvelle_page(self, page):
        if page in self.pages:
            return
        self.pages.append(page)
        if len(self.pages) > 1:
            self._record_evidence(self.messages.append, f"Un nouvel onglet s'est ouvert (onglet {len(self.pages)}).")
            self.onglet = len(self.pages) - 1
        page.on("console", lambda m: self._console(page, m))
        page.on("pageerror", lambda e: self._anomalie(page, "erreur-js", str(e)))
        page.on("requestfailed", lambda r: self._echec_requete(page, r))
        page.on("response", lambda r: self._reponse(page, r))
        page.on("request", self._requete)
        page.on("dialog", self._dialogue)
        page.on("download", lambda d: self.lancer(self._telechargement(d)))
        page.on("crash", lambda p: self._anomalie(page, "crash", "l'onglet a planté"))
        page.on("close", self._fermee)

    def _fermee(self, page):
        if page not in self.pages:
            return
        i = self.pages.index(page)
        self.pages.remove(page)
        self.refs.pop(page, None)
        self.ecrans.pop(page, None)
        if self.onglet >= len(self.pages):
            self.onglet = max(0, len(self.pages) - 1)
        elif i < self.onglet:
            self.onglet -= 1

    def pannes_en_cours(self):
        """Identifiants des pannes qui touchent cet humain en ce moment."""
        return [p.get("id", p["type"]) for p in self.pannes + self.globales]

    def _anomalie(self, page, genre, message, url=None):
        if genre == "erreur-js":
            self._record_evidence(self.erreurs_page.append, message[:300])
        self.journal({"type": "anomalie", "h": self.id, "genre": genre, "message": message[:500],
                      "url": url or (page.url if page else None), "induite": self.pannes_en_cours(),
                      "apres": list(self.apres)})

    def _console(self, page, message):
        if message.type == "error":
            self._anomalie(page, "console", message.text)

    def _echec_requete(self, page, requete):
        self._anomalie(page, "requete-echouee", f"{requete.method} {requete.url} : {requete.failure}", requete.url)

    def _reponse(self, page, reponse):
        if reponse.status >= 400:
            self._anomalie(page, "http", f"{reponse.status} {reponse.request.method} {reponse.url}", reponse.url)

    def _requete(self, requete):
        if requete.resource_type in ("fetch", "xhr", "websocket", "eventsource"):
            adresse = urlparse(requete.url)
            chemin = re.sub(r"/\d+(?=/|$)", "/{id}", adresse.path)
            cle = f"{requete.method} {adresse.netloc}{chemin}"
            self._record_evidence(self.requetes.increment, cle)

    def _dialogue(self, dialogue):
        self.dialogue = dialogue
        self.evt_dialogue.set()
        self.journal({"type": "boite", "h": self.id, "genre": dialogue.type, "message": dialogue.message})

    async def _telechargement(self, telechargement):
        nom = telechargement.suggested_filename
        with suppress(Exception):
            if self.dossier:
                destination = Path(self.dossier) / "telechargements" / f"{self.id}-{nom_de_fichier_sur(nom)}"
                destination.parent.mkdir(parents=True, exist_ok=True)
                await telechargement.save_as(destination)
        self._record_evidence(self.messages.append, f'Un fichier a été téléchargé : "{nom}".')
        self.journal({"type": "telechargement", "h": self.id, "fichier": nom})

    @property
    def page(self):
        return self.pages[self.onglet] if self.pages else None

    def pages_libres(self):
        """Les onglets sur lesquels on peut agir : pas celui qui porte une boîte ouverte (elle bloquerait)."""
        if self.dialogue is None:
            return list(self.pages)
        porteuse = getattr(self.dialogue, "page", None)
        return [p for p in self.pages if porteuse is not None and p != porteuse]

    def page_libre(self):
        """L'onglet courant, ou ValueError s'il n'y en a pas ou si une boîte le bloque."""
        page = self.page
        if page is None:
            raise ValueError("aucun onglet ouvert")
        if page not in self.pages_libres():
            raise ValueError("une boîte du navigateur est ouverte : panne non appliquée")
        return page

    async def nouvelle_page(self, url=None):
        """Ouvre un onglet (sur `url` s'il est donné) et attend qu'il soit interactif."""
        page = await self.ctx.new_page()
        self._nouvelle_page(page)
        self.onglet = self.pages.index(page)
        if url:
            await page.goto(url, wait_until="domcontentloaded", timeout=DELAI_NAVIGATION_MS)
            await self.hydrater(page)
        return page

    def reseau_en_panne(self):
        """True si une panne réseau (ou l'arrêt de l'application) touche cet humain en ce moment."""
        return bool(self.globales) or any(p["type"] in PANNES_RESEAU | {"offline"} for p in self.pannes)

    async def hydrater(self, page):
        """Attend que la page soit interactive : chargement terminé, puis réseau calme (borné).
        Un clic donné avant l'hydratation d'une application React serait perdu."""
        fin = time.time() + (HYDRATATION_RESEAU_MAX if self.reseau_en_panne() else HYDRATATION_MAX)
        for etat in ("load", "networkidle"):
            reste = fin - time.time()
            if reste < 0.2:
                break
            try:
                await page.wait_for_load_state(etat, timeout=reste * 1000)
            except Exception:
                break

    # -- pannes --
    async def _route(self, route):
        try:
            requete = route.request
            for panne in list(self.pannes):
                exclusions = panne.get("chaos_exclude", {})
                if exclusions:
                    from .chaos import matches
                    if matches(exclusions.get("routes", []), urlparse(requete.url).path) or matches(exclusions.get("methods", []), requete.method):
                        continue
                if not panne_vise(panne, requete, self.origine):
                    continue
                type_panne = panne["type"]
                if type_panne == "server-down":
                    await route.abort("connectionrefused")
                    return
                if type_panne == "http-error":
                    await route.fulfill(status=code_http(panne), content_type="text/plain",
                                        body=panne.get("corps") or "Internal Server Error")
                    return
                if type_panne == "lost-response" and panne.get("restant", 1) > 0:
                    panne["restant"] = panne.get("restant", 1) - 1
                    with suppress(Exception):
                        await route.fetch()
                    await route.abort("connectionreset")
                    return
                if type_panne == "slow":
                    await asyncio.sleep(int(panne.get("delai") or 3000) / 1000)
            await route.continue_()
        except Exception:
            # une erreur ici ne doit jamais laisser la requête en suspens
            with suppress(Exception):
                await route.continue_()

    async def _poser_quota(self, actif):
        """Pose (ou retire) le drapeau de stockage plein dans les onglets déjà ouverts."""
        for page in self.pages_libres():
            with suppress(Exception):
                await borne(page.evaluate("(a) => { window.__hordeQuota = a; }", actif))

    async def installer_horloge(self):
        if not self.horloge:
            self.horloge = True
            await borne(self.ctx.clock.install(time=datetime.now()), DELAI_PANNE)

    async def appliquer(self, panne):
        """Applique une panne à cet humain. Lève une exception si elle ne peut pas l'être."""
        t = panne["type"]
        if t in PANNES_RESEAU:
            if not self.route_posee:
                self.route_posee = True
                await borne(self.ctx.route("**/*", self._route))
            if t == "lost-response":
                panne["restant"] = int(panne.get("fois") or 1)
            self.pannes.append(panne)
        elif t == "offline":
            self.pannes.append(panne)
            await borne(self.ctx.set_offline(True))
        elif t == "storage-full":
            self.pannes.append(panne)
            self.quota = True
            if self.quota_init is None:
                # le drapeau est posé avant le script de chaque nouvelle page (reload, tab new)
                self.quota_init = await borne(self.ctx.add_init_script(script="window.__hordeQuota = true;"))
            await self._poser_quota(True)
        elif t == "storage-empty":
            await borne(self.page_libre().evaluate("() => { localStorage.clear(); sessionStorage.clear(); }"))
            self.apres.append(panne.get("id", t))
        elif t == "storage-corrupt":
            panne["cles"] = await borne(self.page_libre().evaluate(CORROMPRE_JS, panne.get("cle") or "*"))
            self.apres.append(panne.get("id", t))
        elif t == "clock":
            if self.dialogue is not None:
                raise ValueError("une boîte du navigateur est ouverte : panne non appliquée")
            await self.installer_horloge()
            await borne(self.ctx.clock.fast_forward(duree_ms(panne.get("avance") or "24h")), DELAI_PANNE)
            self.apres.append(panne.get("id", t))
        elif t == "window":
            largeur, hauteur = (int(x) for x in (panne.get("taille") or "390x844").lower().split("x"))
            await borne(self.page_libre().set_viewport_size({"width": largeur, "height": hauteur}))
            self.apres.append(panne.get("id", t))
        elif t == "cookies-cleared":
            await borne(self.ctx.clear_cookies())
            self.apres.append(panne.get("id", t))

    async def retirer(self, panne):
        """Met fin à une panne de durée. La route réseau et le script de quota sont retirés avec la dernière."""
        if panne in self.pannes:
            self.pannes.remove(panne)
        t = panne["type"]
        if t in PANNES_RESEAU and self.route_posee and not any(x["type"] in PANNES_RESEAU for x in self.pannes):
            # sans route, le cache du navigateur revient
            self.route_posee = False
            await borne(self.ctx.unroute("**/*", self._route))
        if t == "offline" and not any(x["type"] == "offline" for x in self.pannes):
            await borne(self.ctx.set_offline(False))
        if t == "storage-full" and not any(x["type"] == "storage-full" for x in self.pannes):
            self.quota = False
            if self.quota_init is not None:
                init, self.quota_init = self.quota_init, None
                with suppress(Exception):
                    await borne(init.dispose())
            await self._poser_quota(False)

    # -- exécution d'un geste, en tenant compte des boîtes du navigateur --
    async def executer(self, coroutine, delai=DELAI_EXECUTION):
        """Exécute un geste. Renvoie son résultat, ou "boite" si une boîte du navigateur s'est ouverte
        (le geste reste alors suspendu jusqu'à la réponse). Lève TimeoutError au bout de `delai` secondes."""
        self.evt_dialogue.clear()
        tache = asyncio.ensure_future(coroutine)
        attente = asyncio.ensure_future(self.evt_dialogue.wait())
        try:
            fini, _ = await asyncio.wait({tache, attente}, timeout=delai, return_when=asyncio.FIRST_COMPLETED)
            if tache in fini:
                return tache.result()
            if self.dialogue is not None:
                self.tache_suspendue = tache
                return "boite"
            raise TimeoutError("le navigateur ne répond plus")
        finally:
            pending = [attente]
            if tache is not self.tache_suspendue:
                pending.append(tache)
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)

    async def repondre_boite(self, accepter, texte=None):
        """Répond à la boîte du navigateur ouverte, puis laisse finir le geste qu'elle suspendait."""
        boite = self.dialogue
        if boite is None:
            raise ValueError("aucune boîte du navigateur n'attend de réponse")
        self.dialogue = None
        if accepter:
            await boite.accept(texte)
        else:
            await boite.dismiss()
        if self.tache_suspendue:
            tache, self.tache_suspendue = self.tache_suspendue, None
            with suppress(Exception):
                await asyncio.wait_for(tache, timeout=10)

    async def calme(self, page=None, calme_ms=CALME_MS, requetes=False):
        """Attend que la page cesse de bouger (DOM stable pendant `calme_ms`), sans bloquer sous une boîte
        ouverte. Avec `requetes`, attend aussi qu'aucun fetch ni xhr ne soit en vol (toujours borné)."""
        page = page or self.page
        if page is None or self.dialogue is not None:
            return
        with suppress(Exception):
            await page.wait_for_load_state("domcontentloaded", timeout=8000)
        with suppress(Exception):
            await borne(page.evaluate(CALME_JS, {"calme": calme_ms, "max": CALME_MAX_MS, "requetes": requetes}))

    async def lire(self, complet=False):
        """Lit l'écran de l'onglet courant : {lignes, titre, url}."""
        page = self.page
        if page is None:
            return {"lignes": ["(aucun onglet ouvert : utiliser tab new)"], "titre": "", "url": ""}
        if self.dialogue is not None:
            boite = self.dialogue
            return {"lignes": [f'!! Le navigateur affiche une boîte ({boite.type}) : "{boite.message}"',
                               'Réponds avec "accept" (OK) ou "dismiss" (Annuler).'],
                    "titre": "", "url": page.url}
        memoire = self.refs.setdefault(page, {"n": 0, "cles": {}})
        options = {"mode": "voir", "max": LIGNES_ECRAN_COMPLET if complet else LIGNES_ECRAN, "complet": complet,
                   "debut": memoire["n"], "cles": memoire["cles"]}
        try:
            ecran = await borne(page.evaluate(script_ecran(), options), DELAI_LECTURE)
        except Exception as e:
            return {"lignes": [f"(l'écran ne se laisse pas lire : {premiere_ligne(e, 160)})"], "titre": "",
                    "url": page.url}
        memoire["n"] = ecran.pop("n", memoire["n"])
        memoire["cles"].update(ecran.pop("cles", {}))
        if len(memoire["cles"]) > REFS_MEMOIRE_MAX:
            memoire["cles"] = dict(list(memoire["cles"].items())[-REFS_MEMOIRE_MAX:])
        return ecran

    async def capturer(self, nom):
        """Capture de l'onglet courant dans le dossier des captures. Renvoie le chemin, ou None."""
        if not self.captures or self.page is None or self.dialogue is not None:
            return None
        chemin = Path(self.captures) / f"{nom}.jpg"
        try:
            from chaosfolk.privacy import screenshot_masks
            await self.page.screenshot(path=str(chemin), type="jpeg", quality=50, scale="css", timeout=6000,
                                       mask=screenshot_masks(self.page))
            return chemin
        except Exception:
            return None

    # -- trouver une cible --
    async def resoudre_ref(self, texte):
        """Référence [rN] d'une cible donnée par son code ou par son libellé.
        Renvoie (référence, None), ou (None, message) si le libellé est absent ou ambigu."""
        brut = str(texte).strip()
        m = RE_REF.fullmatch(brut)
        if m:
            return m.group(1), None
        page = self.page
        if page is None:
            return None, "aucun onglet ouvert"
        res = await borne(page.evaluate(script_ecran(), {"mode": "chercher", "libelle": brut}))
        trouves = res["exacts"] or res["proches"]
        if len(trouves) == 1:
            return trouves[0]["ref"], None
        if not trouves:
            return None, (f'aucun élément visible ne porte le nom "{brut}". Regarde l\'écran (look) '
                          "et utilise le code entre crochets.")
        liste = ", ".join(f'[{x["ref"]}] {x["ligne"]}' for x in trouves[:6])
        return None, f'plusieurs éléments portent ce nom : {liste}. Utilise le code voulu entre crochets.'

    async def cible_ref(self, ref):
        """Localisateur et description d'une référence [rN] (None, None si elle n'existe plus)."""
        page = self.page
        if page is None:
            return None, None
        loc = page.locator(f'[data-horde-ref="{ref}"]')
        if await borne(loc.count()) == 0:
            return None, None
        description = None
        with suppress(Exception):
            description = await borne(page.evaluate(script_ecran(), {"mode": "decrire", "ref": ref}))
        return loc.first, description

    async def cible_desc(self, desc, delai=None):
        """Retrouve un élément visible à partir de sa description (rejeu). Attend qu'il apparaisse
        (jusqu'au délai du geste). Lève ValueError s'il est introuvable ou ambigu."""
        from playwright.async_api import Error as ErreurPlaywright
        delai = (delai or self.delai_geste) / 1000
        fin = time.time() + delai
        rang = int(desc.get("index") or 0)
        while True:
            ambigu = manque = None
            page = self.page
            if page is None:
                raise ValueError("aucun onglet ouvert")
            for nom, loc, avec_index in self._candidats(page, desc):
                try:
                    visibles = loc.filter(visible=True)
                    nb = await borne(visibles.count())
                except ErreurPlaywright:
                    # localisateur invalide pour cette page (chemin css périmé...) : on essaie le suivant
                    continue
                if avec_index and rang > 0 and nb:
                    # l'index n'a de sens que parmi les éléments de même rôle et même nom. S'il dépasse, le
                    # bon élément n'est pas (encore) là : un localisateur plus large en prendrait un autre
                    if rang < nb:
                        return visibles.nth(rang)
                    manque = (nom, nb)
                    break
                if nb == 1:
                    return visibles.first
                if nb > 1 and avec_index:
                    return visibles.nth(rang)
                if nb > 1:
                    ambigu = ambigu or (nom, nb)
            if time.time() >= fin or not self._candidats(page, desc):
                break
            await asyncio.sleep(0.2)
        if manque:
            raise ValueError(f"cible introuvable : rang demandé {rang + 1}, mais {manque[1]} élément(s) "
                             f"seulement ({manque[0]})")
        if ambigu:
            raise ValueError(f"cible ambiguë : {ambigu[1]} éléments correspondent ({ambigu[0]})")
        raise ValueError("cible introuvable")

    @staticmethod
    def _candidats(page, desc):
        """Façons de retrouver la cible, de la plus sûre à la moins sûre : (nom, localisateur, index permis)."""
        essais = []
        if desc.get("testid"):
            essais.append(("data-testid", page.get_by_test_id(desc["testid"]), False))
        role, nom = desc.get("role"), desc.get("nom")
        if role and role != "clickable" and nom:
            essais.append((f"{role} {nom}", page.get_by_role(role, name=nom, exact=True), True))
            essais.append((f"{role} contenant {nom}", page.get_by_role(role, name=nom), True))
        if desc.get("placeholder"):
            essais.append(("indice", page.get_by_placeholder(desc["placeholder"], exact=True), False))
        if desc.get("css"):
            essais.append(("chemin css", page.locator(desc["css"]), False))
        if desc.get("texte"):
            essais.append(("texte", page.get_by_text(desc["texte"], exact=True), False))
        return essais

    # -- les gestes --
    async def geste(self, action, args, loc=None):
        """Exécute un geste (a : ses arguments, loc : sa cible). Renvoie "ok" ou un texte à dire à l'humain
        (key --times : le focus touche après touche). Lève une exception s'il échoue."""
        retour = await getattr(self, f"geste_{action}")(args, loc)
        return retour or "ok"

    async def geste_goto(self, args, loc):
        url = adresse_http(args["url"], self.url_app)
        if self.page is None:
            await self.nouvelle_page(url)
            return
        await self.page.goto(url, wait_until="domcontentloaded", timeout=DELAI_NAVIGATION_MS)
        await self.hydrater(self.page)

    async def geste_click(self, args, loc):
        fois = int(args.get("fois") or 1)
        bouton = "right" if args.get("droit") else "left"
        if args.get("double"):
            await loc.dblclick(timeout=self.delai_geste, button=bouton)
            return
        for i in range(fois):
            try:
                await loc.click(timeout=self.delai_geste if i == 0 else 1200, button=bouton)
            except Exception:
                if i == 0:
                    raise
                break
            if fois > 1:
                await asyncio.sleep(0.08)

    async def geste_type(self, args, loc):
        texte = args.get("texte", "")
        if args.get("lent"):
            if not args.get("ajouter"):
                await loc.fill("", timeout=self.delai_geste)
            await loc.press_sequentially(texte, delay=70, timeout=60000)
        elif args.get("ajouter"):
            await loc.press_sequentially(texte, delay=10, timeout=30000)
        else:
            try:
                await loc.fill(texte, timeout=self.delai_geste)
            except Exception as e:
                if "Cannot type text" not in str(e):
                    raise
                # un champ numérique refuse fill avec un texte comme "1 200,50" : un humain le tape quand même
                await loc.click(timeout=self.delai_geste)
                await loc.press("Control+a", timeout=self.delai_geste)
                await loc.press_sequentially(texte, delay=10, timeout=30000)
        if args.get("entree"):
            await loc.press("Enter", timeout=self.delai_geste)

    async def geste_select(self, args, loc):
        option = args.get("option", "")
        if await loc.evaluate("e => e.tagName") == "SELECT":
            await loc.select_option(label=option, timeout=self.delai_geste)
            return
        await loc.click(timeout=self.delai_geste)
        await asyncio.sleep(0.25)
        page = self.page
        for choix in (page.get_by_role("option", name=option, exact=True), page.get_by_role("option", name=option),
                      page.get_by_text(option, exact=True)):
            if await choix.count():
                await choix.first.click(timeout=self.delai_geste)
                return
        raise ValueError(f'aucune option "{option}" dans la liste')

    async def geste_tick(self, args, loc):
        if args.get("decocher"):
            await loc.uncheck(timeout=self.delai_geste)
            return
        try:
            await loc.check(timeout=self.delai_geste)
        except Exception:
            await loc.click(timeout=self.delai_geste)

    async def geste_key(self, args, loc):
        fois = int(args.get("fois") or 1)
        if not 1 <= fois <= TOUCHES_FOIS_MAX:
            raise ValueError(f"--times va de 1 à {TOUCHES_FOIS_MAX}")
        focus = []
        for _ in range(fois):
            for touche in str(args["touche"]).split():
                await self.page.keyboard.press(touche)
            if fois > 1:
                focus.append(await self.focus_texte())
        if focus:
            return "focus touche après touche : " + ", ".join(focus)
        return None

    async def focus_texte(self):
        """L'élément qui a le focus clavier, en une ligne courte ([r20] lien "Offres"), ou "aucun"."""
        page = self.page
        memoire = self.refs.setdefault(page, {"n": 0, "cles": {}})
        try:
            res = await borne(page.evaluate(script_ecran(), {"mode": "focus", "debut": memoire["n"],
                                                             "cles": memoire["cles"]}))
        except Exception:
            return "?"
        memoire["n"] = max(memoire["n"], res.get("n") or 0)
        return res.get("ligne") or "aucun"

    async def geste_hover(self, args, loc):
        await loc.hover(timeout=self.delai_geste)

    async def geste_scroll(self, args, loc):
        sens = alias(args.get("sens") or "down", ALIAS_SENS)
        taille = self.page.viewport_size or {"width": 1200, "height": 800}
        await self.page.mouse.move(taille["width"] * 0.6, taille["height"] * 0.55)
        if sens in ("top", "bottom"):
            await self.page.keyboard.press("Home" if sens == "top" else "End")
        elif sens in ("right", "left"):
            await self.page.mouse.wheel(500 if sens == "right" else -500, 0)
        else:
            await self.page.mouse.wheel(0, 700 if sens == "down" else -700)

    async def geste_back(self, args, loc):
        await self.page.go_back(wait_until="domcontentloaded", timeout=DELAI_HISTORIQUE_MS)
        await self.hydrater(self.page)

    async def geste_forward(self, args, loc):
        await self.page.go_forward(wait_until="domcontentloaded", timeout=DELAI_HISTORIQUE_MS)
        await self.hydrater(self.page)

    async def geste_reload(self, args, loc):
        await self.page.reload(wait_until="domcontentloaded", timeout=DELAI_NAVIGATION_MS)
        await self.hydrater(self.page)

    async def geste_tab(self, args, loc):
        quoi = alias(str(args.get("quoi") or "new"), ALIAS_ONGLET)
        if quoi == "new":
            url = adresse_http(args.get("url") or (self.page.url if self.page else self.url_app), self.url_app)
            await self.nouvelle_page(url)
        elif quoi == "close":
            if self.page:
                await self.page.close()
        else:
            n = int(quoi)
            if not 1 <= n <= len(self.pages):
                raise ValueError(f"il n'y a que {len(self.pages)} onglet(s)")
            self.onglet = n - 1
            await self.page.bring_to_front()

    async def geste_wait(self, args, loc):
        await asyncio.sleep(min(float(args.get("secondes") or 3), ATTENTE_UNITAIRE))

    async def geste_upload(self, args, loc):
        fichier = fichier_televersable(args["chemin"], self.dossier or ".")
        await loc.set_input_files(str(fichier), timeout=self.delai_geste)


# --------------------------------------------------------------------------
# Le serveur de la horde
# --------------------------------------------------------------------------

def cle_geste(verbe, args):
    """Empreinte d'un geste, pour reconnaître un geste répété à l'identique."""
    return verbe + json.dumps(args or {}, sort_keys=True, ensure_ascii=False)


def lignes_diff(avant, apres):
    """Lignes apparues et lignes disparues entre deux écrans."""
    vues_avant, vues_apres = set(avant), set(apres)
    return [x for x in apres if x not in vues_avant], [x for x in avant if x not in vues_apres]


def sans_focus(lignes):
    """Écran sans les marques de focus clavier (pour savoir si SEUL le focus a bougé)."""
    return [x.replace(" (focus)", "").replace(", focus)", ")") for x in lignes
            if not x.startswith("(focus clavier sur")]


def replier(lignes, deja_vues):
    """Replie les suites d'au moins LIGNES_REPLI_MIN lignes déjà vues (menu, en-tête), références comprises."""
    connues = set(deja_vues)
    sortie, i = [], 0
    while i < len(lignes):
        j = i
        while j < len(lignes) and lignes[j] in connues:
            j += 1
        if j - i >= LIGNES_REPLI_MIN:
            refs = RE_REFS.findall(" ".join(lignes[i:j]))
            sortie.append(f"({j - i} lignes déjà vues, inchangées" + (f" : [{refs[0]}] à [{refs[-1]}]" if refs else "") + ")")
            i = j
        else:
            fin = max(j, i + 1)
            sortie += lignes[i:fin]
            i = fin
    return sortie


class Horde:
    """Le serveur : les navigateurs des humains, les pannes, l'application, le journal."""

    def __init__(self, opts):
        self.opts = opts
        self.dossier = Path(opts.dossier).resolve()
        from .private_state import session_directory
        session_directory(self.dossier)
        from .audit_session import existing as existing_audit
        self.audit_session = existing_audit(self.dossier)
        (self.dossier / "captures").mkdir(exist_ok=True)
        self.url = opts.url
        self.origine_journal = time.time()   # le temps du journal continue d'un lancement à l'autre
        self.lance_a = None                  # premier geste d'un humain qui n'est pas éclaireur
        self.dernier_contact = time.time()
        self.duree_max = opts.duree_max
        self.duree_humain = opts.duree_humain
        self.humains = {}
        self.fiches = {}
        self.verrous = {}
        self.pannes = []
        self.globales_actives = []
        self.taches = set()
        self.jeton = secrets.token_hex(32)
        self.jeton_chef = secrets.token_hex(32)
        self.arret = asyncio.Event()
        self.garder_app = False
        # application lancée par la horde
        self.app = None
        self.app_identity = None
        self.app_log = None
        self.app_externe = False             # elle tournait déjà avant la horde : la horde ne peut pas l'arrêter
        self.verrou_app = asyncio.Lock()
        # reprise dans un dossier existant : le temps et la numérotation continuent
        self.n_repris = {}
        self.n_panne = 0
        dernier_t = 0
        for e in iterer_journal(self.dossier, obligatoire=False):
            dernier_t = max(dernier_t, e.get("t", 0))
            if e.get("type") == "action":
                self.n_repris[e["h"]] = max(self.n_repris.get(e["h"], 0), e.get("n", 0))
            m = RE_PANNE_NUM.match(str(e.get("id") or ""))
            if m:
                self.n_panne = max(self.n_panne, int(m.group(1)))
        self.origine_journal -= dernier_t / 1000 + 1
        self.journal_f = open(self.dossier / "journal.jsonl", "a", encoding="utf-8")
        from .chaos import Controller, policy_path
        source = policy_path(getattr(opts, "chaos_policy", None), getattr(opts, "project", None))
        self.chaos = Controller(self.dossier, self.jeton, source, getattr(opts, "dry_run", False)) if source or getattr(opts, "dry_run", False) else None
        if self.chaos:
            self.chaos.snapshot(self.pannes)

    def horodatage(self):
        """Millisecondes écoulées depuis l'origine du journal."""
        return int((time.time() - self.origine_journal) * 1000)

    def journal(self, evenement):
        evenement = {"t": self.horodatage(), **evenement}
        self.journal_f.write(json.dumps(evenement, ensure_ascii=False) + "\n")
        self.journal_f.flush()
        if getattr(self, "chaos", None):
            self.chaos.event(evenement)
            if evenement["type"] in {"chaos-planned", "chaos-skipped", "chaos-simulated", "chaos-cancelled", "chaos-control", "panne-debut", "panne-fin"}:
                self.chaos.snapshot(self.pannes)

    def lancer(self, coroutine):
        """Lance une tâche de fond en la gardant."""
        tache = asyncio.ensure_future(coroutine)
        self.taches.add(tache)
        tache.add_done_callback(self.taches.discard)
        return tache

    # -- application gérée par la horde --
    def app_vivante(self):
        return self.app is not None and self.app.poll() is None

    async def app_demarrer(self):
        """Lance l'application et attend qu'elle réponde. Sans effet si elle tourne déjà."""
        if not self.opts.app_commande or self.app_externe:
            raise ValueError("la horde n'a pas lancé l'application (option --app-command)")
        async with self.verrou_app:
            if self.app_vivante():
                return True
            if await asyncio.to_thread(url_repond, self.url):
                self.journal({"type": "app", "etat": "deja-lancee"})
                return True
            self.app_log = open(self.dossier / "app.log", "a", encoding="utf-8")
            self.app = subprocess.Popen(self.opts.app_commande, shell=True, cwd=self.opts.app_dossier or None,  # nosec B602: the operator's own --app-command, never network input
                                        stdout=self.app_log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                        **options_detache())
            self.app_identity = process_identity(self.app.pid)
            self.noter_app_pid()
            ok, raison = await asyncio.to_thread(attendre_url, self.url, self.opts.app_attente, self.app)
            self.journal({"type": "app", "etat": "demarree" if ok else "injoignable", "raison": raison or None})
            if not ok:
                print(raison, flush=True)
            return ok

    async def app_arreter(self):
        """Arrête l'application (et ses enfants). Renvoie False si la horde ne l'a pas lancée."""
        async with self.verrou_app:
            if self.app is None:
                return False
            await asyncio.to_thread(self._tuer_app)
            self.noter_app_pid()
            self.journal({"type": "app", "etat": "arretee"})
            return True

    def noter_app_pid(self):
        """Écrit dans serveur.json le PID de l'application lancée par la horde (None si elle est arrêtée) :
        stop-app s'en sert pour arrêter l'application laissée par stop --keep-app."""
        fichier = self.dossier / "serveur.json"
        with suppress(Exception):
            info = lire_json(fichier)
            if info:
                info["app_pid"] = self.app.pid if self.app_vivante() else None
                info["app_identity"] = self.app_identity if self.app_vivante() else None
                ecrire_json(fichier, info)

    def _tuer_app(self):
        processus, self.app = self.app, None
        identity, self.app_identity = self.app_identity, None
        if processus.poll() is None:
            stop_owned_process(identity)
        with suppress(Exception):
            processus.wait(timeout=10)
        if self.app_log:
            self.app_log.close()
            self.app_log = None

    async def app_au_demarrage(self):
        """Lance l'application demandée. Si quelque chose répond déjà sur l'adresse, ne la relance pas."""
        if not self.opts.app_commande:
            return
        if await asyncio.to_thread(url_repond, self.url):
            self.app_externe = True
            self.journal({"type": "app", "etat": "deja-lancee"})
            print(f"attention : quelque chose répond déjà sur {self.url} (port occupé). La horde ne lance pas "
                  "l'application et ne pourra pas l'arrêter : app-stop est refusée.", flush=True)
            return
        await self.app_demarrer()

    # -- cycle de vie --
    async def lancer_horde(self):
        from playwright.async_api import async_playwright
        veille = None
        app = None
        try:
            app = asyncio.ensure_future(self.app_au_demarrage())
            self.pw = await async_playwright().start()
            self.navigateur, self.canal = await lancer_navigateur(self.pw, self.opts.visible, self.opts.canal)
            await app
            serveur = await asyncio.start_server(self.client, "127.0.0.1", self.opts.port or 0, limit=LIMITE_LIGNE)
            port = serveur.sockets[0].getsockname()[1]
            info = {"port": port, "jeton": self.jeton, "dossier": str(self.dossier), "url": self.url,
                    "pid": os.getpid(), "navigateur": self.canal, "debut": datetime.now().isoformat(timespec="seconds")}
            ecrire_json(self.dossier / "serveur.json", {**info, "jeton_chef": self.jeton_chef,
                                                        "app_pid": self.app.pid if self.app_vivante() else None,
                                                        "app_identity": self.app_identity if self.app_vivante() else None})
            ecrire_json(FICHIER_ACTIF, info)
            config = lire_json(self.dossier / "config.json", {})
            config.update({"url": self.url, "debut": info["debut"], "navigateur": self.canal,
                           "app_commande": self.opts.app_commande, "projet": getattr(self.opts, "project", None)})
            if self.chaos:
                config["chaos"] = self.chaos.status()
            ecrire_json(self.dossier / "config.json", config)
            self.journal({"type": "debut", "url": self.url, "navigateur": self.canal})
            print(f"horde prête sur le port {port} ({self.canal})", flush=True)
            veille = asyncio.ensure_future(self.veiller())
            async with serveur:
                await self.arret.wait()
        finally:
            pending = [task for task in (veille, app) if task is not None]
            for task in pending:
                task.cancel()
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)
            await self.fermer()

    async def fermer(self):
        self.journal({"type": "fin-horde", "garder_app": self.garder_app or None})
        for tache in list(self.taches):
            tache.cancel()
        if self.taches:
            await asyncio.gather(*list(self.taches), return_exceptions=True)
        for m in self.humains.values():
            with suppress(Exception):
                await m.fermer()
        with suppress(Exception):
            await asyncio.wait_for(self.navigateur.close(), 10)
        with suppress(Exception):
            await asyncio.wait_for(self.pw.stop(), 10)
        if not self.garder_app:
            with suppress(Exception):
                await self.app_arreter()
        elif self.app_log:
            self.app_log.close()
        if self.chaos:
            await self.chaos.close()
        self.journal_f.close()
        with suppress(Exception):
            if lire_json(FICHIER_ACTIF, {}).get("pid") == os.getpid():
                FICHIER_ACTIF.unlink()

    async def veiller(self):
        """Tic de la horde : active et arrête les pannes, surveille les durées. Ne bloque jamais."""
        while not self.arret.is_set():
            await asyncio.sleep(0.25)
            try:
                if self.chaos:
                    await self.chaos.refresh()
                audit_due = self.audit_session and time.monotonic() - getattr(self, "audit_last_gate", 0) >= 1
                if audit_due and self.audit_session.gate():
                    # Stop admission of new work. Keep the engine available for
                    # final results and explicit cleanup; never kill the host.
                    for fault in self.pannes:
                        if fault["phase"] in {"programmee", "admission"}:
                            fault["phase"] = "annulee"
                        elif fault["phase"] == "active" and fault["type"] not in PANNES_INSTANT:
                            fault["fin_prevue"] = self.horodatage()
                if audit_due:
                    self.audit_last_gate = time.monotonic()
                self.verifier_pannes()
            except Exception as e:
                self.journal({"type": "erreur-moteur", "message": premiere_ligne(e)})
            if not self.audit_session and self.lance_a and time.time() - self.lance_a > self.duree_max + MARGE_ARRET:
                self.journal({"type": "arret-duree-max"})
                self.arret.set()
            if time.time() - self.dernier_contact > self.opts.inactivite:
                self.journal({"type": "arret-inactivite"})
                self.arret.set()

    async def client(self, lecteur, ecrivain):
        """Une requête du client : une ligne JSON, une réponse JSON."""
        try:
            try:
                req = json.loads((await asyncio.wait_for(lecteur.readline(), 10)).decode("utf-8"))
                if not isinstance(req, dict):
                    raise ValueError("requête JSON attendue sous forme d'objet")
                if not self.autorise(req):
                    rep = {"ok": False, "texte": self.refus_jeton(req)}
                else:
                    self.dernier_contact = time.time()
                    rep = await self.traiter(req)
            except Exception as e:
                rep = {"ok": False, "texte": f"erreur : {premiere_ligne(e)}"}
            ecrivain.write((json.dumps(rep, ensure_ascii=False) + "\n").encode("utf-8"))
            await ecrivain.drain()
        finally:
            ecrivain.close()

    def autorise(self, req):
        """Le jeton des humains suffit pour agir ; les commandes du chef demandent le jeton du chef."""
        jeton = req.get("jeton")
        if req.get("cmd") in COMMANDES_RESERVEES:
            return jeton_egal(jeton, self.jeton_chef)
        return jeton_egal(jeton, self.jeton) or jeton_egal(jeton, self.jeton_chef)

    def refus_jeton(self, req):
        if req.get("cmd") in COMMANDES_RESERVEES:
            return MESSAGE_RESERVEE
        return "jeton invalide"

    async def traiter(self, req):
        cmd = req["cmd"]
        if cmd == "inspect" and getattr(self, "audit_session", None):
            refusal = self.audit_session.gate(consume=True)
            if refusal:
                return {"ok": False, "texte": refusal}
        simples = {"faults": self.texte_pannes, "status": self.texte_bilan, "network": self.texte_reseau}
        if cmd in simples:
            return {"ok": True, "texte": simples[cmd]()}
        commandes = {"humans": self.creer_humains, "action": self.action, "fault": self.programmer_panne,
                     "fault-end": self.terminer_panne, "save-state": self.sauver_etat,
                     "inspect": self.inspecter, "stop": self.demander_arret, "erreur_commande": self.noter_erreur_commande,
                     "audit": self.auditer, "chaos-control": self.controler_chaos, "release": self.liberer_humain}
        if cmd not in commandes:
            return {"ok": False, "texte": f"commande inconnue : {cmd}"}
        return await commandes[cmd](req)

    async def controler_chaos(self, req):
        action = req.get("action")
        allowed = {"status", "pause", "resume", "simulate", "live", "enable", "disable", "schedule-on", "schedule-off"}
        if action not in allowed:
            raise ValueError("Unknown chaos control")
        if self.chaos is None:
            if action == "status":
                return {"ok": True, "texte": json.dumps({"policy": None, "enabled": True, "dry_run": False})}
            from .chaos import Controller
            self.chaos = Controller(self.dossier, self.jeton)
        if action in ("pause", "resume"):
            self.chaos.paused = action == "pause"
        elif action in ("enable", "disable"):
            self.chaos.override["enabled"] = action == "enable"
        elif action in ("schedule-on", "schedule-off"):
            self.chaos.override["schedule_enabled"] = action == "schedule-on"
        elif action in ("simulate", "live"):
            self.chaos.override["dry_run"] = action == "simulate"
        if req.get("end_active"):
            for fault in self.pannes:
                if fault["phase"] == "active" and fault["type"] not in PANNES_INSTANT:
                    fault["fin_prevue"] = self.horodatage()
            self.verifier_pannes()
        if action != "status":
            self.journal({"type": "chaos-control", "action": action})
        return {"ok": True, "texte": json.dumps(self.chaos.status())}

    async def demander_arret(self, req):
        self.garder_app = bool(req.get("garder_app"))
        texte = "horde arrêtée"
        if self.garder_app and self.opts.app_commande and not self.app_externe:
            # une panne app-stop en cours (ou l'application en train de redémarrer) : l'application est
            # relancée avant de fermer, sinon "--keep-app" laisserait une application arrêtée
            relancee = False
            if not self.app_vivante() and any(p["type"] in PANNES_GLOBALES and p["phase"] in ("active", "redemarrage")
                                              for p in self.pannes):
                relancee = await self.app_demarrer()
                if not relancee:
                    texte += ". Attention : l'application, arrêtée par une panne, n'a pas pu être relancée (voir app.log)"
            if self.app_vivante():
                texte += (" (l'application" + (", arrêtée par une panne, a été relancée et" if relancee else "")
                          + " continue de tourner ; pour l'arrêter : chaosfolk stop-app --folder "
                          + f'"{self.dossier.as_posix()}")')
        elif self.garder_app:
            texte += " (l'application continue de tourner)"
        self.arret.set()
        return {"ok": True, "texte": texte}

    async def noter_erreur_commande(self, req):
        """Commande d'humain mal écrite (refusée par le client avant d'arriver ici) : notée au journal
        pour qu'analyze la compte. Un identifiant inconnu (faute de frappe du chef) n'est pas noté."""
        if req.get("h") in self.humains:
            self.journal({"type": "erreur_commande", "h": req["h"], "texte": str(req.get("texte") or "")[:300],
                          "message": str(req.get("message") or "")[:300]})
        return {"ok": True, "texte": ""}

    async def sauver_etat(self, req):
        m = self.humains[req["h"]]
        fichier = sous_dossier(req["fichier"], self.dossier, "fichier")
        fichier.parent.mkdir(parents=True, exist_ok=True)
        verrou = self.verrous[req["h"]]
        try:
            await asyncio.wait_for(verrou.acquire(), DELAI_LECTURE)
        except asyncio.TimeoutError:
            return {"ok": False, "texte": "l'humain est occupé (un geste est en cours) ; réessaie save-state ensuite"}
        try:
            if m.closed:
                if m.released_state is None:
                    return {"ok": False, "texte": "The browser is closed and has no saved release state."}
                saved = lire_json(m.released_state, None)
                if not isinstance(saved, dict):
                    return {"ok": False, "texte": f"The saved release state is missing or unreadable: {m.released_state.as_posix()}"}
                ecrire_json(fichier, saved)
            else:
                await borne(m.ctx.storage_state(path=str(fichier)), DELAI_PANNE)
        finally:
            verrou.release()
        return {"ok": True, "texte": f"état de {req['h']} enregistré dans {fichier.as_posix()}"}

    async def liberer_humain(self, req):
        """Release a finished user's browser only after preserving its storage state."""
        hid = req["h"]
        m = self.humains.get(hid)
        if m is None:
            return {"ok": False, "texte": f"Unknown user: {hid}"}
        async with self.verrous[hid]:
            if m.closed:
                return {"ok": True, "texte": f"Browser already released for {hid}."}
            if m.statut not in ("fini", "abandon"):
                return {"ok": False, "texte": "Finish the user with done or giveup before releasing its browser."}
            blocking = [p["id"] for p in self.pannes
                        if p.get("h") in (None, hid)
                        and p.get("phase") in {"programmee", "admission", "active", "redemarrage"}]
            if blocking:
                return {"ok": False, "texte": "End pending or active faults before release: " + ", ".join(blocking)}
            if any(not task.done() for task in m.taches):
                return {"ok": False, "texte": "Wait for this user's background downloads before release."}
            target = self.dossier / "etats" / "released" / f"{hid}-{secrets.token_hex(8)}.json"
            target.parent.mkdir(parents=True, exist_ok=True)
            m.releasing = True
            try:
                await borne(m.ctx.storage_state(path=str(target)), DELAI_PANNE)
                # The state file exists: record it before closing, so a failed
                # close can be retried without saving a second file.
                m.released_state = target
                self.journal({"type": "browser-released", "h": hid,
                              "state": chemin_relatif(target, self.dossier)})
                await m.fermer()
            finally:
                m.releasing = False
            return {"ok": True, "texte": f"Browser released for {hid}; storage state saved in {target.as_posix()}."}

    async def inspecter(self, req):
        m = self.humains.get(req["h"])
        if m is None:
            return {"ok": False, "texte": f"humain inconnu : {req['h']}"}
        verrou = self.verrous[req["h"]]
        try:
            await asyncio.wait_for(verrou.acquire(), DELAI_LECTURE)
        except asyncio.TimeoutError:
            return {"ok": False, "texte": "l'humain est occupé (un geste est en cours)"}
        try:
            if m.closed:
                return {"ok": False, "texte": "This user's browser was released; use trace or replay for recorded evidence."}
            if m.dialogue is not None:
                return {"ok": False, "texte": "une boîte du navigateur est ouverte"}
            if m.page is None:
                return {"ok": False, "texte": "aucun onglet ouvert"}
            resultat = await borne(m.page.evaluate(req["js"]), DELAI_LECTURE)
        finally:
            verrou.release()
        return {"ok": True, "texte": json.dumps(resultat, ensure_ascii=False, indent=1)[:20000]}

    async def auditer(self, req):
        """Contrôles UI, responsive et accessibilité de l'onglet courant d'un humain (voir qa.audit_world)."""
        if getattr(self, "audit_session", None):
            refusal = self.audit_session.gate(consume=True)
            if refusal:
                return {"ok": False, "texte": refusal}
        m = self.humains.get(req["h"])
        if m is None:
            return {"ok": False, "texte": f"humain inconnu : {req['h']}"}
        verrou = self.verrous[req["h"]]
        try:
            await asyncio.wait_for(verrou.acquire(), DELAI_LECTURE)
        except asyncio.TimeoutError:
            return {"ok": False, "texte": "l'humain est occupé (un geste est en cours)"}
        try:
            if m.closed:
                return {"ok": False, "texte": "This user's browser was released; use trace or replay for recorded evidence."}
            if m.dialogue is not None:
                return {"ok": False, "texte": "une boîte du navigateur est ouverte"}
            if m.page is None:
                return {"ok": False, "texte": "aucun onglet ouvert"}
            from chaosfolk import audit
            try:
                nom = audit.validate_name(req.get("nom"))
                viewports = audit.validate_viewports(req.get("viewports") or [])
            except ValueError as erreur:
                return {"ok": False, "texte": str(erreur)}
            resultat = await audit.audit_world(m, viewports, bool(req.get("clavier")),
                                            Path(self.dossier) / "audits", nom)
        finally:
            verrou.release()
        return {"ok": True, "texte": resultat}

    # -- humains --
    async def creer_humains(self, req):
        """Crée les navigateurs des humains d'un fichier de personas. Un humain en erreur n'empêche pas les autres."""
        if getattr(self, "audit_session", None):
            refusal = self.audit_session.gate()
            if refusal:
                return {"ok": False, "texte": refusal}
        fichier = Path(req["fichier"])
        donnees = lire_json(fichier)
        if not donnees:
            raise ValueError(f"fichier de personas illisible : {fichier}")
        if getattr(self, "audit_session", None):
            for hid, world in list(self.humains.items()):
                if (not world.closed and world.statut in {"fini", "abandon"}
                        and not self.fiches.get(hid, {}).get("retain_browser")):
                    released = await self.liberer_humain({"h": hid})
                    if not released["ok"]:
                        return released
            new_count = sum(1 for item in donnees.get("humains", []) if isinstance(item, dict) and item.get("id") not in self.humains)
            opened = sum(not world.closed for world in self.humains.values())
            limit = self.audit_session.snapshot()["config"]["limits"].get("max_browsers", 6)
            if opened + new_count > limit:
                return {"ok": False, "texte": f"Browser limit ({limit}) reached. Release finished coordinated users before the next batch."}
        base = fichier.resolve().parent
        crees, erreurs, arrivees = [], [], []
        for k, fiche in enumerate(donnees.get("humains", []), 1):
            hid = fiche.get("id") if isinstance(fiche, dict) else None
            if isinstance(hid, str) and hid in self.humains:
                continue
            m = None
            try:
                # tout ce qui peut être mal écrit dans une fiche est lu ici : un humain fautif n'empêche pas les autres
                if not hid or not isinstance(hid, str):
                    raise ValueError(f"fiche n°{k} sans identifiant (champ id)")
                validate_id(hid)
                budget = fiche.get("budget") or (None if est_eclaireur(hid) else self.opts.budget)
                duree = fiche.get("duree") or (None if est_eclaireur(hid) else self.duree_humain)
                try:
                    budget, duree = (int(budget) if budget else None), (int(duree) if duree else None)
                except (TypeError, ValueError):
                    raise ValueError(f"budget ou durée illisible ({fiche.get('budget')!r}, {fiche.get('duree')!r})") from None
                depart = adresse_http(fiche.get("depart") or self.url, self.url)
                m = await nouveau_monde(self.navigateur, hid, fiche, self.url, base, journal=self.journal,
                                        captures=self.dossier / "captures", dossier=self.dossier)
            except Exception as e:
                erreurs.append(f"{hid or 'fiche ' + str(k)} : {premiere_ligne(e)}")
                self.journal({"type": "anomalie", "h": hid, "genre": "creation", "message": premiere_ligne(e),
                              "induite": []})
                if m is not None:
                    with suppress(Exception):
                        await m.fermer()
                continue
            m.globales = self.globales_actives
            m.n = self.n_repris.get(hid, 0)
            m.humeur = fiche.get("humeur") or ""
            m.budget, m.duree = budget, duree
            self.humains[hid], self.fiches[hid], self.verrous[hid] = m, fiche, asyncio.Lock()
            crees.append(hid)
            arrivees.append((m, depart, fiche))
        self.fusionner_personas(fichier, donnees, base, crees)

        async def arriver(m, depart, fiche):
            try:
                await m.nouvelle_page(depart)
            except Exception as e:
                self.journal({"type": "anomalie", "h": m.id, "genre": "chargement", "message": premiere_ligne(e),
                              "induite": []})
            self.journal({"type": "arrivee", "h": m.id, "nom": fiche.get("nom"), "url": depart})

        # les humains arrivent tous en même temps, sur une page interactive
        await asyncio.gather(*(arriver(*x) for x in arrivees))
        texte = f"{len(crees)} humain(s) prêt(s) : {', '.join(crees) or 'aucun nouveau'}"
        if erreurs:
            texte += "\nNon créé(s) :\n  " + "\n  ".join(erreurs)
        return {"ok": not erreurs, "texte": texte}

    def fusionner_personas(self, fichier, donnees, base, crees):
        """Ajoute les humains créés à personas.json : un deuxième lot ne fait pas disparaître le premier."""
        cible = self.dossier / "personas.json"
        if fichier.resolve() == cible.resolve() or not crees:
            return
        deja = lire_json(cible, {})
        nouvelles = [dict(h) for h in donnees.get("humains", []) if isinstance(h, dict) and h.get("id") in crees]
        for fiche in nouvelles:
            etat = fiche.get("etat")
            if isinstance(etat, str) and not Path(etat).is_absolute():
                fiche["etat"] = (base / etat).resolve().as_posix()
        fusion = dict(deja, **{k: v for k, v in donnees.items() if k != "humains"})
        fusion["humains"] = [h for h in deja.get("humains", []) if h.get("id") not in crees] + nouvelles
        ecrire_json(cible, fusion)

    async def action(self, req):
        hid = req["h"]
        if hid not in self.humains:
            return {"ok": False, "texte": f"humain inconnu : {hid} (le chef d'orchestre doit lancer 'humans')"}
        if req["action"] == "help":
            return {"ok": True, "texte": AIDE_HUMAIN + f"Captures : {(self.dossier / 'captures').as_posix()}/<nom>.jpg\n"}
        async with self.verrous[hid]:
            return await self.jouer_action(hid, req["action"], req.get("args") or {}, req)

    def garde_fou(self, m, verbe, args):
        """Message de refus si le geste ne doit pas se faire, None sinon."""
        if m.statut in ("fini", "abandon"):
            if verbe in PAROLES - {"think"}:
                return "ta session est déjà terminée."
            return "ta session est terminée, plus aucun geste n'est possible."
        if verbe in PAROLES - {"think"}:
            return None
        if getattr(self, "audit_session", None):
            refusal = self.audit_session.gate(consume=verbe in GESTES or verbe == "look")
            if refusal:
                return "Audit stopped: " + refusal + '. Finish with done; do not retry or create another run.'
            tasks = self.fiches.get(m.id, {}).get("audit_tasks", [])
            active = getattr(m, "audit_task", None)
            if tasks and (not active or not self.audit_session.task_allowed(active)):
                return 'Choose an enabled assigned task with check-start before acting. If none remain, finish with done.'
        maintenant = time.time()
        if not getattr(self, "audit_session", None) and self.lance_a and maintenant - self.lance_a > self.duree_max:
            return 'la horde est terminée (durée maximale atteinte). Termine maintenant : done "<ton bilan>".'
        if m.duree and m.debut_reel and maintenant - m.debut_reel > m.duree:
            return 'ton temps est écoulé. Termine maintenant : done "<ton bilan>".'
        if verbe in GESTES and m.budget and m.n_gestes >= m.budget + MARGE_BUDGET:
            return 'ton budget de gestes est épuisé. Termine maintenant : done "<ton bilan>".'
        if verbe in NAVIGATION and m.bloque_jusqua > maintenant:
            return (f"le site ne répondait plus il y a un instant. Attends encore {int(m.bloque_jusqua - maintenant) + 1} s, "
                    "continue sans naviguer, ou termine.")
        navigation_clavier = verbe == "key" and est_touche_navigation(args.get("touche", ""))
        if (verbe in GESTES_COMPTES and not navigation_clavier and m.dernier_inutile
                and m.repetitions >= REPETITIONS_MAX and cle_geste(verbe, args) == m.dernier_cle):
            return (f"tu as déjà fait exactement ce geste {m.repetitions} fois sans résultat. Un défaut se signale une fois, "
                    "il ne se retente pas : signale-le si ce n'est pas fait, puis passe à autre chose ou termine.")
        if verbe == "wait" and m.attente >= ATTENTE_MAX:
            return f"tu as déjà attendu {int(m.attente)} s en tout. Continue autrement ou termine."
        return None

    def _refuser(self, m, hid, verbe, a, req, refus):
        m.refus += 1
        self.journal({"type": "garde-fou", "h": hid, "action": verbe, "args": a, "message": refus, "refus": True,
                      "pense": req.get("pense"), "dit": req.get("dit")})
        return {"ok": False, "texte": ">> Garde-fou : " + refus}

    @staticmethod
    def _borner_attente(m, args):
        """Arguments d'une attente, bornés à ATTENTE_UNITAIRE et au reste du cumul permis."""
        try:
            demandee = float(args.get("secondes") or 3)
        except ValueError:
            raise ValueError(f"durée illisible : {args.get('secondes')}") from None
        secondes = max(0.5, min(demandee, ATTENTE_UNITAIRE, ATTENTE_MAX - m.attente))
        m.attente += secondes
        return dict(args, secondes=secondes)

    async def _jouer(self, m, verbe, args):
        """Joue un geste. Renvoie (résultat, message, description de la cible, arguments)."""
        if m.dialogue is not None and verbe not in BOITE:
            return "echec", "une boîte du navigateur attend ta réponse (accept ou dismiss)", None, args
        description = None
        # un humain n'attend pas 5 s qu'un élément devienne cliquable, sauf quand le réseau est en panne
        m.delai_geste = DELAI_GESTE_MS if m.reseau_en_panne() else DELAI_GESTE_HUMAIN_MS
        try:
            if verbe == "wait":
                args = self._borner_attente(m, args)
            if verbe in BOITE:
                await m.repondre_boite(verbe == "accept", args.get("texte"))
                return "ok", "", None, args
            loc = None
            if "ref" in args:
                ref, erreur = await m.resoudre_ref(args["ref"])
                if ref is None:
                    return "echec", erreur, None, args
                args = dict(args, ref=ref)
                loc, description = await m.cible_ref(ref)
                if loc is None:
                    return "echec", f"je ne trouve plus [{ref}] à l'écran (la page a changé)", None, args
                if verbe in ("click", "hover", "tick") and (description or {}).get("hors_ecran"):
                    # tiroir fermé, panneau poussé hors de la fenêtre : Playwright attendrait tout le délai pour rien
                    return "echec", "l'élément n'est pas visible (hors de l'écran)", description, args
            delai = DELAI_EXECUTION_LENT if args.get("lent") else DELAI_EXECUTION
            retour = await m.executer(m.geste(verbe, args, loc), delai=delai)
            if retour == "boite":
                return "ok", "une boîte du navigateur s'est ouverte", description, args
            return "ok", "" if retour == "ok" else str(retour), description, args
        except Exception as e:
            return "echec", traduire_erreur(e), description, args

    def _compter(self, m, verbe, args, resultat, message, change_utile):
        """Met à jour les compteurs des garde-fous après un geste. Renvoie les alertes à donner à l'humain."""
        alertes = []
        if verbe not in GESTES:
            return alertes
        cle = cle_geste(verbe, args)
        m.repetitions = m.repetitions + 1 if cle == m.dernier_cle else 1
        m.dernier_cle = cle
        m.dernier_inutile = resultat == "echec" or not change_utile
        m.sans_changement = m.sans_changement + 1 if not change_utile else 0
        if resultat == "echec" and any(x in message for x in ERREURS_RESEAU):
            m.ko_reseau += 1
        elif resultat == "ok":
            m.ko_reseau = 0
        if m.ko_reseau >= RESEAU_KO_MAX:
            m.ko_reseau = 0
            m.bloque_jusqua = time.time() + PAUSE_RESEAU
            alertes.append(f"le site ne répond plus. C'est noté par la horde, inutile d'insister : pendant {PAUSE_RESEAU} s, "
                           f"les gestes de navigation sont refusés. Attends une fois (wait {ATTENTE_UNITAIRE}), "
                           "puis continue ou termine.")
        navigation_clavier = verbe == "key" and est_touche_navigation(args.get("touche", ""))
        if (verbe != "wait" and not navigation_clavier and m.dernier_inutile
                and m.repetitions == REPETITIONS_MAX):
            alertes.append("deuxième essai identique sans effet. La horde refusera le suivant : "
                           "signale ce que tu vois et change d'approche.")
        if m.sans_changement == ECRAN_FIGE:
            alertes.append(f"l'écran n'a pas bougé depuis {ECRAN_FIGE} gestes. Si tu es bloqué, signale-le, "
                           "puis change d'approche ou termine.")
        if m.budget:
            restant = m.budget - m.n_gestes
            if restant == ALERTE_BUDGET:
                alertes.append(f"il te reste environ {ALERTE_BUDGET} gestes.")
            elif restant == 0:
                alertes.append('c\'était ton dernier geste prévu : termine avec done "<ton bilan>".')
        return alertes

    def _rediger(self, m, hid, verbe, args, obs):
        """Texte de la réponse à l'humain : écran entier, ce qui a changé, ou rien."""
        ecran, lignes, avant = obs["ecran"], obs["ecran"]["lignes"], obs["avant"]
        parole = verbe in PAROLES
        entete = f"Écran de {hid}"
        if len(m.pages) > 1:
            entete += f", onglet {m.onglet + 1}/{len(m.pages)}"
        adresse = urlparse(ecran.get("url") or "")
        chemin = (adresse.path + (("?" + adresse.query) if adresse.query else "")
                  if adresse.netloc == m.origine else (ecran.get("url") or ""))
        # le titre de la page n'est redit que quand il change
        titre = ecran.get("titre") or ""
        if titre != m.dernier_titre:
            m.dernier_titre = titre
            sortie = [entete + f' : "{titre}" {chemin}']
        else:
            sortie = [entete + f" : {chemin}"]
        if verbe in GESTES:
            message = obs["message"]
            if message and message[-1] not in ".!?)":
                message += "."
            if obs["resultat"] == "ok":
                sortie.append(f"Geste fait ({message.rstrip('.')})." if message else "Geste fait.")
            else:
                sortie.append(f"Geste raté : {message}")
        if m.messages:
            sortie.extend(">> " + message for message in m.messages)
            m._record_evidence(m.messages.clear)
        complet = False
        nouvelle_url = ecran.get("url") != obs["url_avant"]
        full = bool(args.get("complet"))
        if parole:
            sortie.append("Noté.")
        elif verbe == "look" and not full and not obs["change"] and m.derniere_sortie_complete:
            sortie.append("Rien n'a changé depuis le dernier écran que tu as vu. Chaque geste te renvoie déjà l'écran : "
                          "inutile de lancer look juste après.")
        elif verbe == "look" and full and m.dernier_complet == (m.page, lignes):
            sortie.append("Rien n'a changé.")
            complet = m.derniere_sortie_complete
        elif verbe == "look" or not avant or nouvelle_url or full:
            sortie += lignes if full else replier(lignes, m.vues)
            complet = True
            if full:
                m.dernier_complet = (m.page, lignes)
        else:
            plus, moins = lignes_diff(avant, lignes)
            if not plus and not moins and avant != lignes:
                sortie.append("Les mêmes éléments, dans un autre ordre :")
                sortie += replier(lignes, m.vues)
                complet = True
            elif not plus and not moins:
                sortie.append("Rien n'a changé à l'écran.")
                complet = m.derniere_sortie_complete
            elif not obs["change_utile"] and verbe != "key":
                focus = RE_REFS.findall(" ".join(x for x in lignes if "focus" in x))
                sortie.append("Rien n'a changé à l'écran" + (f" (le focus clavier est sur [{focus[0]}])." if focus else "."))
                complet = m.derniere_sortie_complete
            elif len(plus) + len(moins) > max(12, len(lignes) * 0.5):
                sortie += replier(lignes, m.vues)
                complet = True
            else:
                sortie.append("Ce qui a changé (le reste de l'écran est identique) :")
                sortie += ["+ " + x for x in plus[:40]]
                if len(plus) > 40:
                    sortie.append(f"+ ... {len(plus) - 40} autres")
                sortie += ["- " + x for x in moins[:12]]
                if len(moins) > 12:
                    sortie.append(f"- ... {len(moins) - 12} autres disparus")
        if complet:
            if verbe == "look" and any(x.startswith("(") and "lignes déjà vues" in x for x in sortie):
                sortie.append('(lignes repliées ci-dessus : "look --full" les redonne toutes)')
            m.vues = (m.vues | set(lignes)) if len(m.vues) < REFS_MEMOIRE_MAX else set(lignes)
        if not parole:
            m.derniere_sortie_complete = complet
        if obs["capture"] and not parole:
            sortie.append(f"(capture : {Path(obs['capture']).as_posix()})")
        for alerte in obs["alertes"]:
            sortie.append(">> Attention : " + alerte)
        if verbe in FINS:
            sortie.append("Merci, ta session est terminée.")
        return "\n".join(sortie)

    async def jouer_action(self, hid, verbe, args, req):
        """Un geste, une parole ou un regard d'un humain : garde-fous, geste, lecture, capture, journal, réponse."""
        m = self.humains[hid]
        m.evidence.check()
        m.dernier = time.time()
        if not m.debut_reel:
            m.debut_reel = m.dernier
        if self.lance_a is None and not est_eclaireur(hid):
            self.lance_a = m.dernier
        if req.get("humeur"):
            m.humeur = req["humeur"]
        refus = self.garde_fou(m, verbe, args)
        if refus:
            return self._refuser(m, hid, verbe, args, req, refus)
        page_avant = m.page
        url_avant = page_avant.url if page_avant else ""
        evt = {"type": "action", "h": hid, "action": verbe, "pense": req.get("pense"), "dit": req.get("dit"),
               "humeur": req.get("humeur")}
        ms = {}
        resultat, message, description = "ok", "", None
        t0 = time.perf_counter()
        if verbe in PAROLES:
            if verbe == "check-start":
                if not self.audit_session:
                    raise ValueError("No audit session is attached")
                assigned = next((t for t in self.fiches[hid].get("audit_tasks", []) if t["task_id"] == args["task"]), None)
                if assigned is None or not self.audit_session.task_allowed(args["task"]):
                    raise ValueError("This audit task is not assigned, active and enabled")
                refusal = self.audit_session.gate()
                if refusal:
                    raise ValueError(refusal)
                m.audit_task, m.audit_start_action = args["task"], m.n + 1
            if verbe == "check-result":
                if not self.audit_session:
                    raise ValueError("No audit session is attached")
                assigned = next((t for t in self.fiches[hid].get("audit_tasks", []) if t["task_id"] == args["task"]), None)
                if assigned is None:
                    raise ValueError("This audit task is not assigned to this user")
                if getattr(m, "audit_task", None) != args["task"] or m.n <= getattr(m, "audit_start_action", 0):
                    raise ValueError("Read and exercise the page before reporting a result")
                relative = f"audit-evidence/{hid}-{m.n}-{hashlib.sha256(args['task'].encode()).hexdigest()[:12]}.json"
                ecrire_json(self.dossier / relative, {"user": hid, "action": m.n, "url": url_avant,
                    "screen": m.ecrans.get(m.page, []), "capture": chemin_relatif(m.derniere_capture, self.dossier) if m.derniere_capture else None,
                    "expected": assigned["expect"], "reported": args["texte"]})
                self.audit_session.record(args["task"], args["status"], args["texte"], [relative], hid, assigned["claim"])
                m.audit_task = None
            if verbe == "flag":
                m.signalements += 1
                evt["gravite"] = args.get("gravite") or "annoying"
            if verbe in FINS:
                m.statut = "abandon" if verbe == "giveup" else "fini"
                if getattr(self, "audit_session", None):
                    self.audit_session.release(hid)
        elif verbe in GESTES:
            resultat, message, description, args = await self._jouer(m, verbe, args)
            if verbe != "wait":
                m.n_gestes += 1
        ms["geste"] = round((time.perf_counter() - t0) * 1000)
        t0 = time.perf_counter()
        if verbe in GESTES:
            # pas de calme après look ; court après une navigation (la page a déjà attendu le réseau calme),
            # plus long après une saisie (filtres, validations). Sans panne, on attend aussi les fetch et xhr
            fenetre = CALME_NAVIGATION_MS if verbe in NAVIGATION else CALME_MS if verbe == "type" else CALME_GESTE_MS
            await m.calme(calme_ms=fenetre, requetes=not (m.pannes or m.globales))
        ms["calme"] = round((time.perf_counter() - t0) * 1000)
        t0 = time.perf_counter()
        ecran = await m.lire(complet=bool(args.get("complet")))
        ms["lecture"] = round((time.perf_counter() - t0) * 1000)
        lignes = ecran["lignes"]
        avant = m.ecrans.get(m.page, []) if m.page is page_avant else []
        change = lignes != avant or ecran.get("url") != url_avant
        # un simple déplacement du focus ne compte pas comme un effet, sauf au clavier (Tab, flèches)
        change_utile = change and (sans_focus(lignes) != sans_focus(avant) or ecran.get("url") != url_avant
                                   or verbe == "key")
        m.n += 1
        # une capture seulement si l'écran a changé (ou s'il n'y en a pas encore) : sinon la précédente vaut
        t0 = time.perf_counter()
        capture = None
        if change or not m.derniere_capture:
            capture = await m.capturer(f"{hid}-{m.n:04d}")
            if capture:
                m.derniere_capture = capture
        ms["capture"] = round((time.perf_counter() - t0) * 1000)
        alertes = self._compter(m, verbe, args, resultat, message, change_utile)
        obs = {"ecran": ecran, "avant": avant, "url_avant": url_avant, "change": change,
               "change_utile": change_utile, "capture": capture, "alertes": alertes,
               "resultat": resultat, "message": message}
        texte = self._rediger(m, hid, verbe, args, obs)
        evt.update({"args": args, "n": m.n, "cible": description, "resultat": resultat, "message": message,
                    "onglet": m.onglet + 1, "onglets": len(m.pages), "url": ecran.get("url"),
                    "titre": ecran.get("titre"), "change": change, "duree_ms": ms, "taille_reponse": len(texte),
                    "capture": chemin_relatif(m.derniere_capture, self.dossier) if m.derniere_capture else None,
                    "ecran": lignes[:LIGNES_JOURNAL], "pannes": m.pannes_en_cours()})
        self.journal(evt)
        m._record_evidence(m.evidence.flush)
        m.evidence.check()
        if verbe not in PAROLES:
            # après une parole ("Noté."), l'humain n'a pas vu l'écran : le diff suivant part de ce qu'il a vu
            m.ecrans[m.page] = lignes
        if alertes:
            self.journal({"type": "garde-fou", "h": hid, "action": verbe, "message": " ".join(alertes), "refus": False})
        self.verifier_pannes()
        return {"ok": resultat == "ok", "texte": texte}

    # -- pannes --
    async def programmer_panne(self, req):
        if getattr(self, "audit_session", None):
            refusal = self.audit_session.gate()
            if refusal:
                raise ValueError(refusal)
            if not self.audit_session.fault_allowed(req["type"]):
                raise ValueError("This fault is excluded or missing a prerequisite in the audit selection")
        t = req["type"]
        if t not in PANNES:
            raise ValueError(f"panne inconnue : {t} (connues : {', '.join(sorted(PANNES))})")
        if t in PANNES_GLOBALES and (not self.opts.app_commande or self.app_externe):
            raise ValueError(f"{t} refusée : la horde n'a pas lancé l'application (option --app-command de launch)"
                             + (", elle tournait déjà" if self.app_externe else ""))
        quand_a, apres, duree = (req.get(c) for c in ("a", "apres_actions", "duree"))
        if t in PANNES_GLOBALES and apres not in (None, ""):
            raise ValueError(f"{t} n'a pas d'humain : utiliser --at (secondes) et non --after-actions")
        if duree not in (None, "") and float(duree) <= 0:
            raise ValueError("--duration doit être supérieure à 0 (sinon, ne pas la donner)")
        params = {k: v for k, v in (req.get("params") or {}).items() if k in PARAMS_PANNE and v not in (None, "")}
        # une panne mal paramétrée est refusée tout de suite, pas au moment où elle devrait s'appliquer
        if t == "clock":
            try:
                duree_ms(params.get("avance") or "24h")
            except ValueError:
                raise ValueError(f"--advance illisible : {params.get('avance')} (exemples : 72h, 3j, 15min, 90s)") from None
        if t == "window" and not re.fullmatch(r"\s*\d+\s*[xX]\s*\d+\s*", str(params.get("taille") or "390x844")):
            raise ValueError(f"--size illisible : {params.get('taille')} (exemple : 390x844)")
        if t in PANNES_GLOBALES:
            ids = [None]
        else:
            cible = req.get("humains") or "tous"
            ids = list(self.humains) if cible in ("tous", "all") else [x.strip() for x in cible.split(",") if x.strip()]
            if not ids:
                raise ValueError("aucun humain : lancer d'abord la commande humans")
            inconnus = [x for x in ids if x not in self.humains]
            if inconnus:
                raise ValueError(f"humains inconnus : {', '.join(inconnus)}")
            released = [hid for hid in ids if self.humains[hid].closed or self.humains[hid].releasing]
            if released:
                raise ValueError("Browser already released for: " + ", ".join(released))
        self.n_panne += 1
        lot = f"p{self.n_panne}"
        commun = {"type": t, "lot": lot, "a": self.horodatage() + int(float(quand_a) * 1000) if quand_a not in (None, "") else None,
                  "apres": int(apres) if apres not in (None, "") else None,
                  "duree": int(float(duree) * 1000) if duree not in (None, "") else None,
                  "note": req.get("note"), "phase": "programmee", **params}
        if commun["a"] is None and commun["apres"] is None:
            commun["a"] = self.horodatage()
        for hid in ids:
            fault = {"id": f"{lot}-{hid}" if hid else lot, "h": hid, **commun}
            fault["scheduled"] = bool(req.get("scheduled") or quand_a is not None or apres is not None)
            self.pannes.append(fault)
            if self.chaos:
                self.journal({"type": "chaos-planned", "id": fault["id"], "h": hid, "panne": t})
        self.verifier_pannes()
        return {"ok": True, "texte": f"panne {lot} ({t}) programmée"}

    async def terminer_panne(self, req):
        """fault-end : arrête une panne active, annule une panne programmée (par identifiant ou par lot)."""
        trouvees = [p for p in self.pannes if req["id"] in (p["id"], p["lot"])]
        if not trouvees:
            return {"ok": False, "texte": f"aucune panne ne correspond à {req['id']} (voir : horde.py faults)"}
        for p in trouvees:
            if p["phase"] == "programmee":
                p["phase"] = "annulee"
                if self.chaos:
                    self.journal({"type": "chaos-cancelled", "id": p["id"], "h": p["h"], "panne": p["type"]})
            elif p["phase"] == "admission":
                p["phase"] = "annulee"
                self.journal({"type": "chaos-cancelled", "id": p["id"], "h": p["h"], "panne": p["type"]})
            elif p["phase"] == "active" and p["type"] not in PANNES_INSTANT:
                p["fin_prevue"] = self.horodatage()
        self.verifier_pannes()
        return {"ok": True, "texte": f"panne {req['id']} terminée ({len(trouvees)} panne(s))"}

    def verifier_pannes(self):
        """Programme l'activation et l'arrêt des pannes dues. Ne fait aucun appel à un navigateur :
        chaque panne s'applique dans sa propre tâche, avec un délai maximal."""
        maintenant = self.horodatage()
        audit_run = getattr(self, "audit_session", None)
        allowed_faults = audit_run.fault_selection() if audit_run and any(
            p["phase"] in {"programmee", "admission", "active"} for p in self.pannes) else None
        for p in self.pannes:
            if (allowed_faults is not None and p["phase"] in {"programmee", "admission", "active"}
                    and p["type"] not in allowed_faults):
                if p["phase"] in {"programmee", "admission"}:
                    p["phase"] = "annulee"
                elif p["type"] not in PANNES_INSTANT:
                    p["fin_prevue"] = maintenant
            if p["phase"] == "programmee":
                m = self.humains.get(p["h"]) if p["h"] else None
                prete = (p["a"] is not None and maintenant >= p["a"]) or \
                        (p["apres"] is not None and m is not None and m.n_gestes >= p["apres"])
                if prete:
                    p["phase"] = "admission" if self.chaos else "active"
                    self.lancer(self._tache_panne(self.activer, p, maintenant))
            elif p["phase"] == "active" and p.get("fin_prevue") is not None and maintenant >= p["fin_prevue"]:
                p["phase"] = "redemarrage" if self.chaos or p["type"] in PANNES_GLOBALES else "terminee"
                self.lancer(self._tache_panne(self.desactiver, p, maintenant))

    async def _tache_panne(self, fonction, p, maintenant):
        """Exécute activer ou desactiver sous le verrou de l'humain (s'il est libre à temps), jamais indéfiniment."""
        verrou = self.verrous.get(p["h"])
        pris = False
        if verrou is not None:
            with suppress(asyncio.TimeoutError):
                await asyncio.wait_for(verrou.acquire(), DELAI_VERROU)
                pris = True
        try:
            await fonction(p, maintenant)
        except Exception as e:
            p["erreur"] = premiere_ligne(e, 200)
            if self.chaos and p["phase"] == "admission":
                p["phase"], p["reason"] = "ignoree", "engine-admission-error"
                await self.chaos.release(p)
                self.journal({"type": "chaos-skipped", "id": p["id"], "h": p["h"], "panne": p["type"], "reason": p["reason"]})
            self.journal({"type": "erreur-moteur", "message": f"{p['id']} : {p['erreur']}"})
        finally:
            if pris:
                verrou.release()

    async def activer(self, p, maintenant):
        if getattr(self, "audit_session", None):
            if self.audit_session.gate() or not self.audit_session.fault_allowed(p["type"]):
                p["phase"] = "annulee"
                return
        if self.chaos:
            if p["phase"] == "annulee":
                return
            reason = await self.chaos.admit(p, self)
            if (p["phase"] == "annulee" or (getattr(self, "audit_session", None) and
                    (self.audit_session.gate() or not self.audit_session.fault_allowed(p["type"])))):
                p["phase"] = "annulee"
                await self.chaos.release(p)
                return
            if reason or self.chaos.dry_run():
                p["phase"] = "ignoree" if reason else "simulee"
                p["reason"] = reason or "dry-run"
                self.journal({"type": "chaos-skipped" if reason else "chaos-simulated", "id": p["id"],
                              "h": p["h"], "panne": p["type"], "reason": p["reason"], "group": p.get("chaos_group")})
                return
            p["phase"] = "active"
            maintenant = self.horodatage()
        p["debut"] = maintenant
        if p.get("duree") and "fin_prevue" not in p:
            p["fin_prevue"] = maintenant + p["duree"]
        try:
            if p["type"] == "app-stop":
                self.globales_actives.append(p)
                await asyncio.wait_for(self.app_arreter(), DELAI_PANNE)
            else:
                await asyncio.wait_for(self.humains[p["h"]].appliquer(p), DELAI_PANNE)
        except Exception as e:
            p["erreur"] = premiere_ligne(e, 200)
        params = {k: p[k] for k in PARAMS_PANNE + ("note",) if p.get(k) not in (None, "")}
        exclusions = p.get("chaos_exclude", {})
        if exclusions.get("routes") or exclusions.get("methods"):
            params["chaos_exclude"] = {key: exclusions.get(key, []) for key in ("routes", "methods")}
        self.journal({"type": "panne-debut", "id": p["id"], "lot": p["lot"], "h": p["h"], "panne": p["type"],
                      "params": params, "erreur": p.get("erreur")})
        if p["type"] in PANNES_INSTANT:
            p["phase"] = "terminee"
            p["fin"] = maintenant
            self.journal({"type": "panne-fin", "id": p["id"], "lot": p["lot"], "h": p["h"], "panne": p["type"]})
            if self.chaos:
                await self.chaos.release(p)
        elif p.get("erreur") and self.chaos:
            # Partially installed reversible faults are removed immediately.
            await self.desactiver(p, self.horodatage())

    async def desactiver(self, p, maintenant):
        p["fin"] = maintenant
        extra = {}
        try:
            if p["type"] == "app-stop":
                # la fin n'est notée qu'une fois l'application vraiment revenue
                extra["app_revenue"] = await self.app_demarrer()
            else:
                await asyncio.wait_for(self.humains[p["h"]].retirer(p), DELAI_PANNE)
        except Exception as e:
            p["erreur"] = premiere_ligne(e, 200)
        finally:
            if p in self.globales_actives:
                self.globales_actives.remove(p)
            p["phase"] = "terminee"
            if self.chaos:
                await self.chaos.release(p)
        self.journal({"type": "panne-fin", "id": p["id"], "lot": p["lot"], "h": p["h"], "panne": p["type"],
                      "erreur": p.get("erreur"), **extra})

    # -- textes pour le chef d'orchestre --
    def texte_pannes(self):
        if not self.pannes:
            return "aucune panne programmée"
        lignes = []
        for p in self.pannes:
            quand = f"à {p['a'] / 1000:.0f} s" if p["a"] is not None else f"après {p['apres']} gestes"
            ligne = f"{p['id']:<10} {p['type']:<18} {p['phase']:<11} {quand}"
            if p.get("duree"):
                ligne += f", {p['duree'] / 1000:.0f} s"
            if p["type"] in PANNES_RESEAU:
                ligne += f", méthodes : {methodes_visees(p)}"
            if p.get("erreur"):
                ligne += f" ERREUR {p['erreur']}"
            if p.get("reason"):
                ligne += f" ({p['reason']})"
            lignes.append(ligne)
        return "\n".join(lignes)

    def texte_bilan(self):
        duree = int(time.time() - self.origine_journal)
        n = sum(m.n for m in self.humains.values())
        actives = sum(1 for p in self.pannes if p["phase"] == "active")
        lignes = [f"Horde lancée depuis {duree // 60} min {duree % 60} s : {len(self.humains)} humains, {n} actions, "
                  f"{actives} panne(s) active(s)."]
        for hid, m in self.humains.items():
            nom = str(self.fiches[hid].get("nom", ""))[:22]
            lignes.append(f"{hid} {nom:<22} {m.statut:<9} {m.n:>3} actions  "
                          f"dernière il y a {int(time.time() - m.dernier):>3} s  humeur {m.humeur or '-'}  "
                          f"{m.signalements} signalement(s)  {m.refus} refus  {len(m.erreurs_page)} erreur(s) js")
            if m.evidence.failure is not None:
                lignes.append("  browser stopped after evidence storage failure; evidence may be incomplete")
            elif m.closed:
                lignes.append("  browser released; recorded evidence retained")
        return "\n".join(lignes)

    def texte_reseau(self):
        lignes = []
        for hid, m in self.humains.items():
            try:
                m.evidence.check()
                lignes.extend(f"{hid} {v:>4}  {k}" for k, v in m.requetes.sorted_items())
            except Exception as error:
                lignes.append(f"{hid}  évidence réseau indisponible : {premiere_ligne(error)}")
            finally:
                if m.closed:
                    m.evidence.close()
        return "\n".join(lignes) or "aucun appel réseau de données (fetch, xhr) observé : l'application semble sans serveur"


# --------------------------------------------------------------------------
# Client : ce que lance un humain (léger : ni asyncio, ni Playwright, ni urllib)
# --------------------------------------------------------------------------

def info_serveur():
    """Port, jetons et dossier de la horde active (variable CHAOSFOLK_PORT : port imposé)."""
    info = lire_json(FICHIER_ACTIF, {})
    if os.environ.get("CHAOSFOLK_PORT"):
        info["port"] = int(os.environ["CHAOSFOLK_PORT"])
    if not info.get("port"):
        raise SystemExit("aucune horde lancée (chaosfolk launch ...)")
    return info


def envoyer(req, delai=180):
    """Envoie une requête au serveur de la horde et renvoie sa réponse (dict). Une commande réservée porte
    le jeton du chef (écrit dans <dossier>/serveur.json) seulement si la variable CHAOSFOLK_LEADER_TOKEN vaut ce jeton ;
    sinon elle part avec le jeton des humains et la horde la refuse."""
    info = info_serveur()
    req["jeton"] = info.get("jeton")
    chef = os.environ.get("CHAOSFOLK_LEADER_TOKEN", "").strip()
    if req["cmd"] in COMMANDES_RESERVEES and chef and info.get("dossier"):
        with suppress(ValueError):
            if lire_json(Path(info["dossier"]) / "serveur.json", {}).get("jeton_chef") == chef:
                req["jeton"] = chef
    try:
        with socket.create_connection(("127.0.0.1", int(info["port"])), timeout=delai) as s:
            s.sendall((json.dumps(req, ensure_ascii=False) + "\n").encode("utf-8"))
            tampon = bytearray()
            while not tampon.endswith(b"\n"):
                bloc = s.recv(65536)
                if not bloc:
                    break
                tampon.extend(bloc)
    except OSError as e:
        raise SystemExit(f"la horde ne répond pas sur le port {info['port']} ({e}). Est-elle lancée ?") from e
    try:
        return json.loads(tampon.decode("utf-8"))
    except ValueError:
        raise SystemExit("la horde a répondu de travers (réponse vide ou coupée)") from None


def relayer(req, delai=180):
    """Envoie une commande du chef, affiche la réponse, renvoie le code de sortie (0 si ok)."""
    rep = envoyer(req, delai)
    print(rep.get("texte", ""))
    return 0 if rep.get("ok") else 1


GESTES_ARGUMENTS = {
    "goto": ["url"], "click": ["ref"], "type": ["ref", "texte"], "select": ["ref", "option"],
    "tick": ["ref"], "key": ["touche"], "hover": ["ref"], "upload": ["ref", "chemin"],
    "wait": ["secondes"], "flag": ["texte"], "giveup": ["texte"], "done": ["texte"],
    "check-result": ["task", "status", "texte"],
    "check-start": ["task"],
}
SENS_PERMIS = ["down", "up", "right", "left", "top", "bottom"]
GRAVITES_PERMISES = ["blocking", "annoying", "minor"]


def aide_verbe(verbe):
    """Aide d'une seule commande d'humain (les lignes de AIDE_HUMAIN qui la citent), ou l'aide entière."""
    lignes = AIDE_HUMAIN.splitlines()
    motif = re.compile(rf"(?<![\w-]){re.escape(verbe)}(?![\w-])")
    choisies = [x for x in lignes[1:-1] if motif.search(x[:36])]
    return "\n".join(lignes[:1] + choisies + lignes[-1:]) if choisies else AIDE_HUMAIN


class ErreurCommande(Exception):
    """Commande d'humain mal écrite (levée à la place de la sortie d'argparse, pour la noter au journal)."""


class ParseurHumain(argparse.ArgumentParser):
    def error(self, message):
        raise ErreurCommande(message)


OPTIONS_HUMAIN_VALEUR = {"--thought": "pense", "--say": "dit", "--mood": "humeur", "--times": "fois",
                         "--severity": "gravite"}
OPTIONS_HUMAIN_DRAPEAU = {"--double": "double", "--right": "droit", "--slow": "lent", "--append": "ajouter",
                          "--enter": "entree", "--uncheck": "decocher", "--full": "complet"}


def places_positionnelles(verbe):
    """Nombre de valeurs sans option qu'accepte une commande d'humain (None : sans limite)."""
    if verbe == "key":
        return None
    return len(GESTES_ARGUMENTS.get(verbe, [])) + {"scroll": 1, "tab": 2, "accept": 1}.get(verbe, 0)


def separer_options(verbe, reste):
    """Sépare les options connues des valeurs. Une valeur peut commencer par un tiret (type r3 "-5 %",
    --thought "-- bof") : argparse la prendrait pour une option. Renvoie la liste à donner à argparse :
    les options, puis "--", puis les valeurs. Une ancienne option française qui ne peut pas être une valeur
    (valeur en trop) est refusée avec le nom qui la remplace."""
    options, valeurs, i = [], [], 0
    while i < len(reste):
        jeton = reste[i]
        nom = jeton.split("=", 1)[0]
        if nom in OPTIONS_HUMAIN_VALEUR and "=" in jeton:
            options.append(jeton)
        elif jeton in OPTIONS_HUMAIN_VALEUR and i + 1 < len(reste):
            options.append(f"{jeton}={reste[i + 1]}")
            i += 1
        elif jeton in OPTIONS_HUMAIN_VALEUR or jeton in OPTIONS_HUMAIN_DRAPEAU:
            options.append(jeton)
        else:
            valeurs.append(jeton)
        i += 1
    places = places_positionnelles(verbe)
    anciennes = [v for v in valeurs if v.split("=", 1)[0] in ANCIENNES_OPTIONS]
    if anciennes and (places is None or len(valeurs) > places):
        nom = anciennes[0].split("=", 1)[0]
        refus_ancien_mot(nom, ANCIENNES_OPTIONS[nom], "option")
    return options + (["--"] + valeurs if valeurs else [])


def noter_erreur_commande(hid, argv, message):
    """Envoie à la horde une commande d'humain mal écrite, pour le journal. Jamais bloquant."""
    with suppress(BaseException):
        envoyer({"cmd": "erreur_commande", "h": hid, "texte": " ".join(argv), "message": message}, delai=5)


def commande_humain(argv):
    """`horde.py <humain> <commande> ...` : envoie le geste au serveur et affiche l'écran.
    Code de sortie 1 pour un geste raté (une suite de commandes enchaînées s'arrête là), 0 sinon.
    Une commande mal écrite (code 2) est notée au journal (événement erreur_commande)."""
    hid, verbe, reste = argv[0], (argv[1] if len(argv) > 1 else "look"), argv[2:]
    if verbe not in ACTIONS:
        noter_erreur_commande(hid, argv, f"commande inconnue : {verbe}")
        raise SystemExit(f"commande inconnue : {verbe}\n\n{AIDE_HUMAIN}")
    if "--help" in reste or "-h" in reste:
        print(aide_verbe(verbe))
        return 0
    p = ParseurHumain(prog=f"horde.py {hid} {verbe}", add_help=False)
    for nom, dest in (("--thought", "pense"), ("--say", "dit"), ("--mood", "humeur")):
        p.add_argument(nom, dest=dest)
    for nom in GESTES_ARGUMENTS.get(verbe, []):
        p.add_argument(nom)
    if verbe == "scroll":
        p.add_argument("sens", nargs="?", default="down", choices=SENS_PERMIS)
    if verbe == "tab":
        p.add_argument("quoi", nargs="?", default="new")
        p.add_argument("url", nargs="?")
    if verbe == "accept":
        p.add_argument("texte", nargs="?")
    if verbe == "key":
        p.add_argument("suite", nargs="*")
    for drapeau, dest in OPTIONS_HUMAIN_DRAPEAU.items():
        p.add_argument(drapeau, dest=dest, action="store_true")
    p.add_argument("--times", dest="fois", type=positive_int)
    p.add_argument("--severity", dest="gravite", choices=GRAVITES_PERMISES)
    try:
        args = vars(p.parse_args(separer_options(verbe, reste)))
        if verbe == "key" and args.get("fois") is not None and not 1 <= args["fois"] <= TOUCHES_FOIS_MAX:
            raise ErreurCommande(f"--times va de 1 à {TOUCHES_FOIS_MAX}")
    except ErreurCommande as e:
        noter_erreur_commande(hid, argv, str(e))
        print(f"commande mal écrite : {e}\n\n{aide_verbe(verbe)}", file=sys.stderr)
        return 2
    if verbe == "key":
        args["touche"] = " ".join([args["touche"]] + args.pop("suite"))
    meta = {k: args.pop(k) for k in ("pense", "dit", "humeur")}
    args = {k: v for k, v in args.items() if v not in (None, False)}
    # Git Bash réécrit les arguments qui commencent par /
    for cle, valeur in {**args, **meta}.items():
        if isinstance(valeur, str) and cle != "chemin":
            (meta if cle in meta else args)[cle] = chemin_msys(valeur)
    response = envoyer({"cmd": "action", "h": hid, "action": verbe, "args": args, **meta})
    print(response.get("texte", ""))
    return 0 if response.get("ok") else 1


# --------------------------------------------------------------------------
# Lecture du journal : analyse, extraction d'un scénario
# --------------------------------------------------------------------------

def dossier_courant(dossier=None):
    """Dossier de la horde demandée (--folder), ou de la horde active."""
    if dossier:
        return Path(dossier).resolve()
    info = lire_json(FICHIER_ACTIF, {})
    if info.get("dossier"):
        return Path(info["dossier"])
    raise SystemExit("préciser --folder (aucune horde active)")


def grouper_anomalies(evts):
    """Anomalies techniques regroupées : liste de (catégorie, genre, message, nombre, humains)."""
    groupes = {}
    for e in (x for x in evts if x["type"] == "anomalie"):
        brut = ((e.get("message") or "").splitlines() or [""])[0]
        message = re.sub(r"\d{3,}", "N", re.sub(r"(https?|wss?)://[^ ]+", "URL", brut))[:160]
        if any(re.search(b, e.get("message") or "") for b in BRUIT_DEV):
            categorie = "bruit"
        elif e.get("induite"):
            categorie = "pendant"
        else:
            categorie = "apres" if e.get("apres") else "sans"
        g = groupes.setdefault((categorie, e["genre"], message), {"n": 0, "h": set()})
        g["n"] += 1
        g["h"].add(e.get("h"))
    ordre = {"sans": 0, "apres": 1, "pendant": 2, "bruit": 3}
    return [(c, genre, msg, g["n"], sorted(x for x in g["h"] if x))
            for (c, genre, msg), g in sorted(groupes.items(), key=lambda x: (ordre[x[0][0]], -x[1]["n"]))]


def analyser(dossier):
    """Imprime le tri d'une horde : humains, signalements, anomalies regroupées, pannes, garde-fous, boîtes."""
    from chaosfolk.reporting import JournalSpool
    source = iterer_journal(dossier)
    try:
        with JournalSpool(source, collapse_anomalies=False) as journal:
            return _analyser(dossier, journal)
    finally:
        source.close()


def _analyser(dossier, evts):
    personas = lire_personas(dossier)
    actions, maximum, par_humain, summaries = 0, 0, {}, {}
    for e in evts:
        maximum = max(maximum, e["t"])
        if e["type"] == "erreur_commande":
            par_humain[e.get("h")] = par_humain.get(e.get("h"), 0) + 1
        if e["type"] == "action":
            actions += 1
            summary = summaries.setdefault(e["h"], {"count": 0, "failed": 0, "failures": [], "end": None, "mood": "-", "said": None})
            summary["count"] += 1
            if e["resultat"] == "echec":
                summary["failed"] += 1
                if len(summary["failures"]) < 6:
                    summary["failures"].append({key: e[key] for key in ("n", "action", "message")})
            if e["action"] in FINS:
                summary["end"] = {"action": e["action"], "n": e["n"], "args": {"texte": e["args"].get("texte", "")}}
            if e.get("humeur"):
                summary["mood"] = e["humeur"]
            if e.get("dit"):
                summary["said"] = e["dit"]
    print(f"Horde : {len(personas)} humains, {actions} actions, {maximum / 60000:.1f} min")
    if par_humain:
        print(f"Commandes mal écrites par les humains : {sum(par_humain.values())} ("
              + ", ".join(f"{h} x{n}" for h, n in sorted(par_humain.items(), key=lambda x: str(x[0]))) + ")")
    print("\nHUMAINS")
    for hid, fiche in personas.items():
        summary = summaries.get(hid, {"count": 0, "failed": 0, "failures": [], "end": None, "mood": "-", "said": None})
        fin = summary["end"]
        statut = "abandon" if fin and fin["action"] == "giveup" else ("fini" if fin else "pas terminé")
        print(f"\n{hid} {fiche.get('nom', '')} ({fiche.get('profil', '')}) : {statut}, {summary['count']} actions, "
              f"{summary['failed']} gestes ratés, humeur finale {summary['mood']}")
        if fin:
            print(f'   {"abandon" if statut == "abandon" else "bilan"} (n{fin["n"]}) : "{fin["args"].get("texte", "")}"')
        for e in (x for x in evts.events(kind="action", human=hid) if x["action"] == "flag"):
            print(f'   signalement {e.get("gravite", "")} n{e["n"]} {urlparse(e.get("url") or "").path} : "{e["args"].get("texte", "")}"')
        for e in summary["failures"]:
            print(f'   raté n{e["n"]} {e["action"]} : {e["message"]}')
        if summary["said"]:
            print(f'   a dit : "{summary["said"]}"')
    print("\nANOMALIES TECHNIQUES (regroupées)")
    etiquettes = {"sans": "SANS PANNE", "apres": "après une panne instantanée", "pendant": "induite par une panne",
                  "bruit": "bruit du serveur de dev"}
    for categorie, genre, message, n, humains in grouper_anomalies(evts.events(kind="anomalie")):
        print(f'  [{etiquettes[categorie]}] {genre} x{n} ({", ".join(humains)}) : {message}')
    print("\nPANNES")
    for e in evts.events(kind=("panne-debut", "panne-fin")):
        print(f'  {e["t"] / 1000:>6.0f} s {e["type"]:<11} {e["id"]:<10} {e["panne"]}'
              + (f' ERREUR {e["erreur"]}' if e.get("erreur") else ""))
    first = True
    for e in evts.events(kind="garde-fou"):
        if e.get("refus"):
            if first:
                print("\nGARDE-FOUS (gestes refusés : souvent là où l'application bloque l'humain)")
                first = False
            print(f'  {e["h"]} {e["action"]} {json.dumps(e.get("args") or {}, ensure_ascii=False)[:60]} : {e["message"][:90]}')
    first = True
    for e in evts.events(kind="boite"):
        if first:
            print("\nBOÎTES DU NAVIGATEUR")
            first = False
        print(f'  {e["h"]} {e["genre"]} : "{e["message"]}"')


def extraire(dossier, hid, jusqua=None):
    """Scénario rejouable d'un humain : ses gestes (avec la description de leurs cibles) et les pannes qu'il a
    subies, ancrées sur le numéro d'action d'origine (debut_n, fin_n). L'arrêt de l'application (app-stop)
    devient, pour le rejeu, une coupure du serveur de l'application dans ce navigateur."""
    state = _ExtractionState(dossier, hid, lire_personas(dossier).get(hid, {}),
                             lire_json(Path(dossier) / "config.json", {}), jusqua)
    for e in iterer_journal(dossier):
        state.accept(e)
    return state.result()


class _ExtractionState:
    """One user's replay state; retain output evidence and the latest tab screens."""
    def __init__(self, dossier, hid, fiche, config, jusqua=None):
        self.dossier, self.hid, self.fiche, self.config, self.jusqua = dossier, hid, fiche, config, jusqua
        self.etapes, self.pannes, self.ouvertes, self.ecrans = [], [], {}, {}
        self.depart, self.dernier_n, self.finished = None, 0, False
        self.fault_events = []

    def accept(self, e):
        genre = e["type"]
        if genre in ("panne-debut", "panne-fin") and e.get("h") in (None, self.hid):
            self.fault_events.append(e)
        if self.finished:
            return
        if genre in ("panne-debut", "panne-fin") and e.get("h") in (None, self.hid) and e.get("panne") == "app-stop":
            type_panne, params = "server-down", {"note": "traduit de app-stop : coupure du serveur de l'application"}
        elif e.get("h") == self.hid:
            type_panne, params = e.get("panne"), e.get("params") or {}
        else:
            return
        if genre == "arrivee":
            # une nouvelle arrivée repart de zéro : le navigateur a été recréé avec son état de départ
            self.depart = e.get("url")
            self.etapes, self.pannes, self.ouvertes, self.ecrans, self.dernier_n = [], [], {}, {}, 0
        elif genre == "panne-debut" and not e.get("erreur"):
            self.ouvertes[e["id"]] = {"type": type_panne, "debut_n": self.dernier_n, **params}
            self.pannes.append(self.ouvertes[e["id"]])
        elif genre == "panne-fin" and e["id"] in self.ouvertes:
            self.ouvertes[e["id"]]["fin_n"] = self.dernier_n
        elif genre == "action":
            if self.jusqua is not None and e["n"] > self.jusqua:
                self.finished = True
                return
            self.dernier_n = e["n"]
            cle = e.get("onglet")
            change = e.get("change")
            if change is None:
                # journal d'avant le champ `change` : on compare à l'écran précédent du même onglet
                change = (e.get("ecran"), e.get("url")) != self.ecrans.get(cle)
            self.ecrans[cle] = (e.get("ecran"), e.get("url"))
            if e["action"] in GESTES:
                self.etapes.append({"n": e["n"], "t": e.get("t"), "action": e["action"], "args": e.get("args") or {},
                               "cible": e.get("cible"), "echec_original": e["resultat"] == "echec",
                               "effet": bool(change), "pense": e.get("pense"), "dit": e.get("dit")})
    def result(self):
        etat = self.fiche.get("etat")
        if isinstance(etat, str):
            etat = chemin_relatif(Path(self.dossier) / etat, self.dossier)
        return {"nom": f"{self.hid}-jusqu-a-{self.jusqua or 'fin'}", "humain": self.hid, "url": self.config.get("url"),
                "dossier_horde": Path(self.dossier).resolve().as_posix(), "depart": self.depart,
                "appareil": alias(self.fiche.get("appareil") or "desktop", ALIAS_APPAREILS), "etat": etat,
                "horloge": bool(self.fiche.get("horloge")), "etapes": self.etapes, "pannes": self.pannes,
                "fault_events": self.fault_events, "attendu": [{"type": "no-page-error"}],
                "a_completer": "Écrire dans 'attendu' la propriété qui doit tenir (voir references/reproduction.md)."}


# --------------------------------------------------------------------------
# Rejeu déterministe d'un scénario (sans IA)
# --------------------------------------------------------------------------

def planifier_pannes(sc):
    """Pannes d'un scénario avec l'étape avant laquelle chacune s'applique et celle après laquelle elle s'arrête.
    Les pannes sont ancrées sur le numéro d'action d'origine (debut_n, fin_n), donc un scénario raccourci
    reste juste ; les anciens scénarios (debut_etape, fin_etape) sont lus tels quels.
    Renvoie (pannes, avertissements)."""
    etapes = sc["etapes"]
    numeros = [e.get("n") or k for k, e in enumerate(etapes, 1)]
    plan, avertissements = [], []
    for i, p in enumerate(sc.get("pannes", []), 1):
        p = dict(p)
        p.setdefault("id", f"s{i}")
        if "debut_n" in p:
            avant = next((k for k, n in enumerate(numeros, 1) if n > p["debut_n"]), None)
            apres = None
            if p.get("fin_n") is not None and avant is not None:
                avant_fin = [k for k, n in enumerate(numeros, 1) if n <= p["fin_n"]]
                apres = max(avant, avant_fin[-1] if avant_fin else avant)
                if p["type"] not in PANNES_INSTANT and not any(p["debut_n"] < n <= p["fin_n"] for n in numeros):
                    # panne de durée qui n'a couvert aucun geste à l'origine (seulement des look ou des paroles) :
                    # l'étendre au geste suivant changerait le parcours. Elle s'applique puis se retire avant lui
                    p["sans_geste"] = True
                    apres = None
                    avertissements.append(f"la panne {p['type']} ({p['id']}) n'a couvert aucun geste à l'origine : "
                                          f"appliquée puis retirée juste avant l'étape {avant}")
        else:
            avant, apres = p.get("debut_etape"), p.get("fin_etape")
            if avant is not None and avant > len(etapes):
                avant = None
        if avant is None:
            avertissements.append(f"la panne {p['type']} ({p['id']}) ne s'applique jamais : aucun geste après son début")
        p["avant_etape"], p["apres_etape"] = avant, apres
        plan.append(p)
    return plan, avertissements


async def jouer_etape(m, etape):
    """Rejoue un geste d'un scénario. Lève une exception s'il échoue."""
    action, args = etape["action"], etape.get("args") or {}
    if action in BOITE:
        if m.dialogue is not None:
            await m.repondre_boite(action == "accept", args.get("texte"))
        return
    if m.dialogue is not None:
        await m.repondre_boite(False)
    loc = None
    if etape.get("cible") or "ref" in args:
        loc = await m.cible_desc(etape.get("cible") or {})
    await m.executer(m.geste(action, args, loc), delai=DELAI_EXECUTION_LENT if args.get("lent") else DELAI_EXECUTION)


async def appliquer_recette(m, sc):
    """Après le parcours, avant les attendus : recharger, revenir par l'adresse de départ, ouvrir un nouvel onglet,
    vider le stockage du navigateur puis recharger, revenir en arrière, ou refaire le dernier geste réussi."""
    recette = sc["recette"]
    if recette == "reload":
        await m.executer(m.geste("reload", {}, None))
    elif recette == "revisit":
        await m.executer(m.geste("goto", {"url": sc.get("depart") or sc["url"]}, None))
    elif recette == "new-tab":
        await m.executer(m.geste("tab", {"quoi": "new"}, None))
    elif recette == "local-only":
        await borne(m.page.evaluate("() => { localStorage.clear(); sessionStorage.clear(); }"))
        await m.executer(m.geste("reload", {}, None))
    elif recette == "back":
        await m.executer(m.geste("back", {}, None))
    elif recette == "retry":
        derniere = next((e for e in reversed(sc["etapes"]) if not e.get("echec_original")), None)
        if derniere is None:
            raise ValueError("aucun geste à refaire")
        await jouer_etape(m, derniere)
    else:
        raise ValueError(f"recette inconnue : {recette} (connues : {', '.join(RECETTES)})")


async def rejouer_un(navigateur, sc, avec_pannes, dossier_sortie, nom, dossier_horde, observer=None):
    """Un essai de rejeu dans un navigateur neuf. Renvoie le résultat de l'essai (dict).
    `observer` : fonction JavaScript évaluée sur la page finale, son résultat va dans "observation"."""
    url = sc["url"]
    # plusieurs sessions (utilisateurs, rôles) : un contexte isolé chacune, ouvert à son premier geste
    sessions = sc.get("sessions") or {}
    principale = (sc["etapes"][0].get("session") if sc["etapes"] else None) or next(iter(sessions), None)
    mondes = {}

    async def ouvrir(session):
        fiche = dict(sc, **(sessions.get(session) or {}))
        if isinstance(fiche.get("etat"), str) and not (Path(dossier_horde) / fiche["etat"]).exists():
            # le dossier de la horde a pu être déplacé : l'état se retrouve dans son dossier etats/
            autre = Path(dossier_horde) / "etats" / Path(fiche["etat"]).name
            if autre.exists():
                fiche["etat"] = autre.as_posix()
        monde = await nouveau_monde(navigateur, f"rejeu-{session}" if session else "rejeu", fiche, url, dossier_horde,
                                    captures=dossier_sortie, dossier=dossier_horde,
                                    evidence_dir=Path(dossier_sortie) / "evidence")
        mondes[session] = monde
        await monde.nouvelle_page(fiche.get("depart") or url)
        await monde.calme()
        return monde

    def live_evidence():
        return [{"session": session, "path": chemin_relatif(world.evidence.path, dossier_sortie),
                 "collections": [name for name in ("errors", "messages", "requests")
                                 if getattr(world.evidence, name).disk]}
                for session, world in mondes.items() if world.evidence.path is not None]

    journal_etapes = []
    fault_events = []
    from .audit_session import existing as existing_audit
    audit_run = existing_audit(dossier_horde)

    def audit_interruption(consume=False):
        reason = audit_run.gate(consume=consume) if audit_run else None
        return ({"ok": None, "raisons": [], "rejeu_impossible": "Audit stopped: " + reason,
                 "etapes": journal_etapes, "fault_events": fault_events, "live_evidence": live_evidence()}
                if reason else None)

    started = time.monotonic()
    def record_fault(event, fault, step):
        fault_events.append({"event": event, "type": fault["type"], "step": step,
                             "id": fault.get("id"),
                             "elapsed_ms": round((time.monotonic() - started) * 1000)})
    try:
        interrupted = audit_interruption()
        if interrupted:
            return interrupted
        m = await ouvrir(principale)
        plan, avertissements = planifier_pannes(sc) if avec_pannes else ([], [])
        principal = m
        calme_fait = True                 # la page vient d'être attendue : pas de second calme en fin d'essai
        for i, etape in enumerate(sc["etapes"], start=1):
            interrupted = audit_interruption(consume=True)
            if interrupted:
                return interrupted
            # les pannes ne touchent que la session principale ; chaque geste se joue dans sa session
            for p in plan:
                if p["avant_etape"] == i:
                    await principal.appliquer(p)
                    record_fault("start", p, i)
                    if p.get("sans_geste"):
                        # la panne n'a couvert que des regards : l'application la vit un instant, puis elle cesse
                        await principal.calme()
                        await principal.retirer(p)
                        record_fault("end", p, i)
            session = etape.get("session") or principale
            m = mondes.get(session) or await ouvrir(session)
            tolerant = etape.get("echec_original")
            calme_fait = False
            if tolerant and not etape.get("effet") and not sc.get("garder_echecs"):
                journal_etapes.append({"etape": i, "action": etape["action"], "ok": True,
                                       "message": "sauté (raté à l'origine, sans effet)"})
            else:
                ok, message = True, ""
                try:
                    await jouer_etape(m, etape)
                    await m.calme()
                    calme_fait = True
                except Exception as e:
                    # raté à l'origine avec un effet (page d'erreur, navigation coupée) : on le rejoue sans exiger le succès
                    ok, message = bool(tolerant), traduire_erreur(e) if not tolerant else "raté comme à l'origine"
                    if not tolerant:
                        await m.calme()
                        calme_fait = True
                journal_etapes.append({"etape": i, "action": etape["action"], "ok": ok, "message": message})
            for p in plan:
                if p["apres_etape"] == i and p in principal.pannes:
                    await principal.retirer(p)
                    record_fault("end", p, i)
        if m.dialogue is not None:
            await m.repondre_boite(False)
            calme_fait = False
        if not calme_fait:
            await m.calme()
        if sc.get("recette"):
            interrupted = audit_interruption(consume=True)
            if interrupted:
                return interrupted
            try:
                await appliquer_recette(m, sc)
            except Exception as e:
                capture = await m.capturer(nom)
                return {"ok": None, "raisons": [], "rejeu_impossible": f"recette {sc['recette']} impossible : {traduire_erreur(e)}",
                        "fault_events": fault_events, "live_evidence": live_evidence(),
                        "capture": capture.as_posix() if capture else None, "etapes": journal_etapes}
            if m.dialogue is not None:
                await m.repondre_boite(False)
            await m.calme()
        raisons, inverifiable = [], ""
        for session in dict.fromkeys(r.get("session") for r in sc.get("attendu") or []):
            interrupted = audit_interruption()
            if interrupted:
                return interrupted
            # un attendu sans session se lit dans la dernière session qui a agi
            monde = m if session in (None, "") else mondes.get(session) or await ouvrir(session)
            trouve, inverifiable = await verifier_attendu(monde, [r for r in sc["attendu"] if r.get("session") == session])
            raisons += [f"{session} : {x}" for x in trouve] if session else trouve
            if inverifiable:
                break
        if inverifiable:
            # l'attendu n'a pas pu être contrôlé : l'essai ne dit rien, ce n'est pas une casse
            capture = await m.capturer(nom)
            return {"ok": None, "raisons": [], "rejeu_impossible": "attendu invérifiable : " + inverifiable,
                    "fault_events": fault_events, "live_evidence": live_evidence(),
                    "capture": capture.as_posix() if capture else None, "etapes": journal_etapes,
                    "avertissements": avertissements}
        capture = await m.capturer(nom)
        ecran = await m.lire()
        # un geste qui ne s'exécute pas alors qu'il avait marché à l'origine : le rejeu a quitté le parcours
        divergence = next((x for x in journal_etapes if not x["ok"]), None)
        resultat = {"ok": not raisons, "raisons": raisons, "capture": capture.as_posix() if capture else None,
                    "fault_events": fault_events, "live_evidence": live_evidence(),
                    "erreurs_page": m.erreurs_page[:10], "etapes": journal_etapes, "ecran": ecran["lignes"][:40],
                    "divergence": divergence, "avertissements": avertissements}
        if divergence:
            resultat.update(ok=None, raisons=[], rejeu_impossible=
                            f"le rejeu a quitté le parcours à l'étape {divergence['etape']} "
                            f"({divergence['action']} : {divergence['message']})")
        if observer and m.page is not None:
            try:
                resultat["observation"] = await borne(m.page.evaluate(observer), DELAI_LECTURE)
            except Exception as e:
                return {"ok": None, "raisons": [], "rejeu_impossible": f"observation impossible ({traduire_erreur(e)})",
                        "fault_events": fault_events, "live_evidence": live_evidence(),
                        "capture": resultat["capture"], "etapes": journal_etapes}
        for world in mondes.values():
            world._record_evidence(world.evidence.flush)
            if world.evidence.failure is not None:
                resultat.update(ok=None, raisons=[], rejeu_impossible="Live evidence storage failed; trial is incomplete")
        return resultat
    finally:
        for monde in mondes.values():
            for fault in monde.pannes:
                record_fault("context-closed", fault, len(journal_etapes))
            with suppress(Exception):
                await monde.fermer()


CHAMPS_ATTENDU = {
    "no-page-error": (), "page-not-blank": (), "text-visible": ("texte",), "text-absent": ("texte",),
    "count": ("texte",), "storage": ("cle",), "js": ("expression",), "url-contains": ("texte",),
    "field-value": ("champ",),
}
# Vérifications après le parcours : ce qu'un message de succès ne prouve pas (persistance, doublons, désynchronisation)
RECETTES = ("reload", "revisit", "new-tab", "local-only", "back", "retry")


def valider_attendu(attendu, origine="le scénario"):
    """Vérifie les attendus d'un scénario avant tout rejeu : type connu, champs requis, bornes numériques.
    Renvoie la liste (types en anglais) ; lève ValueError avec un message clair sinon."""
    if attendu is None:
        return []
    if isinstance(attendu, dict):
        attendu = [attendu]
    if not isinstance(attendu, list):
        raise ValueError(f"attendu illisible dans {origine} : une liste de règles est attendue")
    from chaosfolk.schema import normalize_assertion
    attendu = [normalize_assertion(rule) for rule in attendu]
    for k, regle in enumerate(attendu, 1):
        if not isinstance(regle, dict):
            raise ValueError(f"attendu n°{k} illisible dans {origine} : une règle est un objet JSON")
        regle["type"] = t = alias(regle.get("type"), ALIAS_ATTENDU)
        if t not in CHAMPS_ATTENDU:
            raise ValueError(f"attendu n°{k} dans {origine} : type inconnu {t!r} "
                             f"(types connus : {', '.join(CHAMPS_ATTENDU)})")
        manquants = [c for c in CHAMPS_ATTENDU[t] if not isinstance(regle.get(c), str) or not regle[c]]
        if manquants:
            raise ValueError(f"attendu n°{k} ({t}) dans {origine} : champ {', '.join(manquants)} manquant")
        for key in ("egal", "min", "max"):
            if key in regle and (type(regle[key]) is not int or regle[key] < 0):
                raise ValueError(f"Assertion {k}: {key} must be a non-negative integer")
        if t == "field-value" and not any(isinstance(regle.get(key), str) for key in ("valeur", "contient")):
            raise ValueError(f"Assertion {k}: field-value needs a value or contains string")
        if t == "count" and not any(key in regle for key in ("egal", "min", "max")):
            raise ValueError("A count assertion needs equals, min or max")
        if regle.get("min", 0) > regle.get("max", float("inf")):
            raise ValueError("Assertion min exceeds max")
    return attendu


async def verifier_attendu(m, attendu):
    """Contrôle les propriétés attendues à la fin d'un rejeu. Renvoie (raisons des échecs, invérifiable) :
    invérifiable est le message d'une règle qui n'a pas pu être contrôlée (erreur JavaScript, page fermée,
    contexte détruit), auquel cas l'essai ne compte pas, ou une chaîne vide."""
    if getattr(m, "evidence", None) is not None and m.evidence.failure is not None:
        return [], "Live evidence storage failed; trial is incomplete"
    page = m.page
    raisons = []
    for regle in attendu:
        t = alias(regle.get("type"), ALIAS_ATTENDU)
        try:
            if t not in CHAMPS_ATTENDU or any(not regle.get(c) for c in CHAMPS_ATTENDU[t]):
                return raisons, f"règle {t!r} incomplète ou inconnue"
            if page is None and t != "no-page-error":
                return raisons, "aucun onglet ouvert à la fin du rejeu"
            if t == "no-page-error":
                ok = not m.erreurs_page
                desc = "aucune erreur JavaScript" + ("" if ok else f" (vu : {m.erreurs_page[0][:120]})")
            elif t in ("text-visible", "text-absent", "count"):
                loc = page.get_by_text(regle["texte"], exact=bool(regle.get("exact")))
                n = sum([1 for i in range(await loc.count()) if await loc.nth(i).is_visible()])
                if t == "text-visible":
                    ok, desc = n > 0, f'texte "{regle["texte"]}" visible'
                elif t == "text-absent":
                    ok, desc = n == 0, f'texte "{regle["texte"]}" absent'
                else:
                    bornes = {"egal": n == int(regle.get("egal", n)), "min": n >= int(regle.get("min", n)),
                              "max": n <= int(regle.get("max", n))}
                    ok = all(bornes.values())
                    voulu = ", ".join(f"{k} {regle[k]}" for k in ("egal", "min", "max") if k in regle)
                    desc = f'"{regle["texte"]}" apparaît ({voulu}) : vu {n} fois'
            elif t == "storage":
                v = await page.evaluate("k => localStorage.getItem(k)", regle["cle"])
                ok = v is not None
                if "contient" in regle:
                    ok = ok and regle["contient"] in v
                if regle.get("json"):
                    try:
                        json.loads(v or "")
                    except ValueError:
                        ok = False
                desc = f'stockage {regle["cle"]} ' + (f'contient "{regle.get("contient")}"' if "contient" in regle else "lisible")
            elif t == "js":
                ok = bool(await page.evaluate(regle["expression"]))
                desc = regle.get("description") or f'expression vraie : {regle["expression"][:80]}'
            elif t == "field-value":
                loc = page.get_by_label(regle["champ"], exact=bool(regle.get("exact")))
                if not await loc.count():
                    loc = page.get_by_placeholder(regle["champ"], exact=bool(regle.get("exact")))
                if not await loc.count():
                    return raisons, f'champ "{regle["champ"]}" absent de la page finale'
                valeur = await loc.first.input_value()
                if "valeur" in regle:
                    ok, desc = valeur == regle["valeur"], f'champ "{regle["champ"]}" vaut "{regle["valeur"]}" (vu "{valeur[:80]}")'
                else:
                    ok, desc = regle["contient"] in valeur, f'champ "{regle["champ"]}" contient "{regle["contient"]}" (vu "{valeur[:80]}")'
            elif t == "url-contains":
                ok, desc = regle["texte"] in page.url, f'adresse contient "{regle["texte"]}"'
            elif t == "page-not-blank":
                n = await page.evaluate("() => (document.body && document.body.innerText || '').trim().length")
                ok, desc = n > 0, "la page affiche quelque chose"
        except Exception as e:
            return raisons, f"{t} : impossible à vérifier ({traduire_erreur(e)})"
        if not ok:
            raisons.append(desc)
    return raisons, ""


def recettes_demandees(texte):
    """Valeur de --persist : des recettes séparées par des virgules, ou all."""
    if not texte:
        return []
    noms = list(RECETTES) if texte.strip() == "all" else [x.strip() for x in texte.split(",") if x.strip()]
    inconnues = [x for x in noms if x not in RECETTES]
    if inconnues:
        raise ValueError(f"Unknown --persist recipe: {', '.join(inconnues)}. Known: {', '.join(RECETTES)}, all")
    return list(dict.fromkeys(noms))


def verdict_rejeu(casses, n, fois, est_temoin):
    """Verdict d'une série d'essais : n essais valides sur `fois` demandés, dont `casses` cassés."""
    if n == 0:
        return "rejeu impossible"
    if n < fois:
        return f"à relancer : {n} essai{'s' if n > 1 else ''} valide{'s' if n > 1 else ''} sur {fois}"
    if est_temoin:
        return "témoin propre" if casses == 0 else ("témoin cassé" if casses == n else "témoin instable")
    return "reproduit" if casses == n else ("intermittent" if casses else "non reproduit")


def charger_scenario(chemin):
    """Lit, traduit et valide un scénario de rejeu. Quitte avec un message clair s'il est inutilisable."""
    fichier = Path(chemin)
    try:
        sc = lire_json(fichier)
    except ValueError as e:
        raise SystemExit(f"scénario illisible : {e}") from None
    if isinstance(sc, dict):
        from chaosfolk.schema import normalize_scenario
        sc = normalize_scenario(sc)
    if not sc or not isinstance(sc, dict) or not isinstance(sc.get("etapes"), list) or not sc.get("url"):
        raise SystemExit(f"scénario illisible : {fichier.as_posix()} (champs url et etapes attendus)")
    normaliser_scenario(sc)
    try:
        sc["attendu"] = valider_attendu(sc.get("attendu"), fichier.name)
    except ValueError as e:
        raise SystemExit(f"scénario inutilisable : {e}") from None
    # le dossier de la horde est écrit par extract ; à défaut (ancien scénario), le parent de scenarios/
    dossier_horde = fichier.resolve().parent.parent
    if sc.get("dossier_horde") and Path(sc["dossier_horde"]).is_dir():
        dossier_horde = Path(sc["dossier_horde"])
    return fichier, sc, dossier_horde


async def rejouer(opts):
    """Rejoue un ou plusieurs scénarios `a.fois` fois chacun, dans un seul navigateur. Les essais tournent en
    parallèle (un contexte isolé chacun, REJEUX_SIMULTANES au plus), sauf avec `a.sequentiel` (application dont le
    serveur partage un état entre essais). Un fichier de résultat et un verdict par série (scénario, témoin)."""
    from playwright.async_api import async_playwright
    from chaosfolk import reproducibility as evidence
    from uuid import uuid4
    environment = evidence.load_environment(getattr(opts, "environment", None))
    baseline = getattr(opts, "baseline", None)
    chemins = opts.scenario if isinstance(opts.scenario, list) else [opts.scenario]
    if baseline:
        if len(chemins) != 1 or opts.temoin:
            raise ValueError("--baseline requires one observed scenario and cannot use --control")
        chemins = [*chemins, baseline]
    run_id = uuid4().hex
    if environment and environment.get("prepare"):
        opts.sequentiel = True
        print("Fixture preparation enabled: all trials and retries run sequentially")
    if opts.nom and len(chemins) > 1 and not baseline:
        raise SystemExit("--name ne va qu'avec un seul scénario (sinon chaque série prend le nom de son fichier)")
    # tout est lu et validé avant de lancer le navigateur : un attendu mal écrit arrête tout de suite
    recettes = recettes_demandees(getattr(opts, "persist", None))
    scenarios = []
    for journey_index, chemin in enumerate(chemins):
        fichier, sc, dossier_horde = charger_scenario(chemin)
        if baseline and (not sc.get("attendu") or not sc.get("pannes")):
            raise ValueError("Both matrix journeys require explicit assertions and their own fault schedule")
        if baseline and not any(p.get("avant_etape") in range(1, len(sc["etapes"]) + 1)
                                for p in planifier_pannes(sc)[0]):
            raise ValueError("Each matrix journey needs a fault anchored to an executed step")
        if getattr(opts, "fail_on_bug", False) and not sc.get("attendu"):
            print("--fail-on-bug requires at least one explicit assertion", file=sys.stderr)
            return 2
        sortie = Path(opts.sortie or dossier_horde / "reproductions")
        if baseline and scenarios:
            sortie = scenarios[0]["sortie"]
        sortie.mkdir(parents=True, exist_ok=True)
        # chaque recette est une série à part : le rapport montre laquelle perd les données
        for recette in recettes or [sc.get("recette")]:
            base = opts.nom or fichier.stem
            journey = "reference" if journey_index else "observed"
            if baseline:
                base = (opts.nom or "matrix") + "-" + journey
            if recette and recettes:
                base += f"-persist-{recette}"
            nom = base + ("-temoin" if opts.temoin else ("-traitement" if not opts.nom else ""))
            series = [(nom, not opts.temoin)]
            if (opts.avec_temoin or baseline) and not opts.temoin:
                series.append((nom + "-temoin", False))
            scenarios.append({"fichier": fichier, "sc": dict(sc, recette=recette), "dossier": dossier_horde,
                              "sortie": sortie, "series": series,
                              "journey": journey, "recipe": recette,
                              "essai_max": max(ESSAI_MAX, 12 * len(sc["etapes"]) + 60)})
    places = asyncio.Semaphore(1 if opts.sequentiel else REJEUX_SIMULTANES)
    if baseline:
        if not recettes and scenarios[0]["recipe"] != scenarios[-1]["recipe"]:
            raise ValueError("Matrix journeys must use the same persistence recipe, or override both with --persist")
        def conditions(sc):
            anchors = {"debut_n", "fin_n", "debut_etape", "fin_etape", "id", "note"}
            return sorted(evidence.fingerprint({k: v for k, v in fault.items() if k not in anchors})
                          for fault in sc.get("pannes", []))
        if conditions(scenarios[0]["sc"]) != conditions(scenarios[-1]["sc"]):
            raise ValueError("Matrix journeys must use the same fault conditions; action anchors may differ")

    async def essai(navigateur, k, nom_serie, avec_pannes, i):
        s = scenarios[k]
        async with places:
            preparation = await evidence.prepare(environment)
            if preparation["status"] == "invalid":
                return {"ok": None, "raisons": [], "capture": None, "preparation": preparation,
                        "rejeu_impossible": preparation["reason"]}
            try:
                result = await asyncio.wait_for(
                    rejouer_un(navigateur, s["sc"], avec_pannes, s["sortie"], f"{nom_serie}-{i}", s["dossier"]),
                    timeout=s["essai_max"])
                return dict(result, preparation=preparation)
            except asyncio.TimeoutError:
                return {"ok": None, "raisons": [], "rejeu_impossible": f"essai arrêté après {s['essai_max']} s",
                        "capture": None, "preparation": preparation}
            except Exception as e:
                # l'application ne répond pas : ce n'est ni une casse ni une tenue
                return {"ok": None, "raisons": [], "rejeu_impossible": traduire_erreur(e), "capture": None,
                        "preparation": preparation}

    travaux = [(k, nom_serie, avec_pannes, i) for k, s in enumerate(scenarios) for nom_serie, avec_pannes in s["series"]
               for i in range(1, opts.fois + 1)]
    async with async_playwright() as pw:
        navigateur, _ = await lancer_navigateur(pw, opts.visible, opts.canal)
        for index, s in enumerate(scenarios):
            s["manifest"] = f"manifests/{run_id}-{index}.json"
            ecrire_json(s["sortie"] / s["manifest"], evidence.manifest(
                s["sc"], s["dossier"], navigateur, environment, s["fichier"]))
        if opts.sequentiel:
            resultats = [await essai(navigateur, *t) for t in travaux]
        else:
            resultats = list(await asyncio.gather(*(essai(navigateur, *t) for t in travaux)))
        # un essai qui a quitté le parcours est rejoué une seule fois, seul ; s'il diverge encore, il est écarté
        for k, (t, r) in enumerate(zip(travaux, resultats)):
            if not r.get("divergence"):
                continue
            r2 = await essai(navigateur, *t)
            d1, d2 = r["divergence"], r2.get("divergence")
            if d2:
                # Repeating a locator/action failure does not prove the product assertion.
                r2 = dict(r2, ok=None, raisons=[],
                          rejeu_impossible=f"le rejeu a quitté le parcours deux fois (étapes {d1['etape']}, {d2['etape']})")
            resultats[k] = r2
        await navigateur.close()

    for k, s in enumerate(scenarios):
        s["results"] = {}
        for nom_serie, avec_pannes in s["series"]:
            essais = [r for t, r in zip(travaux, resultats) if t[0] == k and t[1] == nom_serie]
            for i, r in enumerate(essais, 1):
                etat = ("REJEU IMPOSSIBLE : " + r["rejeu_impossible"]) if r["ok"] is None else \
                    ("tient" if r["ok"] else "CASSE : " + "; ".join(r["raisons"]))
                print(f"{nom_serie} essai {i}/{opts.fois} : {etat}")
                for avertissement in r.get("avertissements") or []:
                    print(f"  attention : {avertissement}")
            valides = [r for r in essais if r["ok"] is not None]
            n = len(valides)
            casses = sum(1 for r in valides if not r["ok"])
            if n < opts.fois:
                print(f"{opts.fois - n} essai(s) impossible(s) : relancer replay quand l'application répond")
            est_temoin = not avec_pannes
            verdict = verdict_rejeu(casses, n, opts.fois, est_temoin)
            resultat = {"scenario": s["fichier"].resolve().as_posix(), "nom": nom_serie,
                        "manifest": s["manifest"], "run_id": run_id,
                        "mode": "temoin" if est_temoin else "traitement", "fois": n, "demandes": opts.fois,
                        "casses": casses, "verdict": verdict, "essais": essais,
                        "date": datetime.now().isoformat(timespec="seconds")}
            resultat["reproducibility"] = evidence.trial_counts(resultat)
            s["results"]["with_faults" if avec_pannes else "without_faults"] = resultat
            cible = s["sortie"] / f"{nom_serie}.json"
            ecrire_json(cible, resultat)
            print(f"{nom_serie} : {verdict} ({casses}/{n} cassés) : fichier {cible.as_posix()}")
            rate = f"{100 * casses / n:.1f}%" if n else "n/a"
            print(f"  {casses}/{n} failures / valid trials ({rate}); {opts.fois - n} invalid; {opts.fois} requested")
    if baseline:
        for recipe in dict.fromkeys(s["recipe"] for s in scenarios):
            members = [s for s in scenarios if s["recipe"] == recipe]
            cells = {s["journey"] + "/" + mode: value for s in members for mode, value in s["results"].items()}
            summary = dict(evidence.matrix_summary(cells), run_id=run_id, cells=cells)
            target = members[0]["sortie"] / ("matrix" + (f"-persist-{recipe}" if recipe else "") + ".json")
            ecrire_json(target, summary)
            print(f"Matrix: {summary['status']} : {target.as_posix()}")
    if getattr(opts, "fail_on_bug", False):
        if any(r["ok"] is None for r in resultats):
            return 2
        if any(not r["ok"] for r in resultats):
            return 1
    return 0


# --------------------------------------------------------------------------
# Rapport
# --------------------------------------------------------------------------

def preuve_resolue(dossier, chemin):
    """Résumé d'un fichier de rejeu pour le rapport, ou None s'il n'existe pas."""
    resultat = lire_json(sous_dossier(chemin, dossier, "preuve"))
    if resultat is None:
        return None
    essais = resultat.get("essais", [])
    for e in essais:
        if e.get("capture"):
            e["capture"] = chemin_relatif(e["capture"], dossier)
    from chaosfolk.scoring import complete
    integrity = complete(resultat, resultat.get("mode"))
    return {**{k: resultat.get(k) for k in ("nom", "mode", "fois", "demandes", "casses", "verdict", "manifest", "reproducibility")},
            "trial_integrity": integrity, "source": chemin,
            "captures": [e.get("capture") for e in essais], "raisons": [e.get("raisons") for e in essais]}


def infos_constats(dossier, constats, evts, personas):
    """Pour chaque constat (par identifiant) : l'URL et l'appareil de son premier événement, et le chemin du
    scénario de sa première preuve. Un champ inconnu vaut None. Les preuves doivent déjà être résumées."""
    if hasattr(evts, "action_urls"):
        references = set()
        for constat in constats.get("constats", []):
            if isinstance(constat, dict) and constat.get("id"):
                first = next((x for x in constat.get("evenements") or [] if isinstance(x, dict)), {})
                references.add((first.get("h"), first.get("n")))
        actions = evts.action_urls(references)
    else:
        actions = {(e.get("h"), e.get("n")): e for e in evts if e.get("type") == "action"}
    fiches = {h.get("id"): h for h in personas.get("humains", []) if isinstance(h, dict)}
    infos = {}
    for constat in constats.get("constats", []):
        if not isinstance(constat, dict) or not constat.get("id"):
            continue
        premier = next((x for x in constat.get("evenements") or [] if isinstance(x, dict)), {})
        action = actions.get((premier.get("h"), premier.get("n"))) or {}
        appareil = (fiches.get(premier.get("h")) or {}).get("appareil")
        scenario = None
        for preuve in (constat.get("preuves") or {}).values():
            chemin = preuve.get("source") if isinstance(preuve, dict) else None
            resultat = lire_json(Path(dossier) / chemin, {}) if chemin else {}
            if resultat.get("scenario"):
                scenario = Path(resultat["scenario"])
                if not scenario.is_absolute():
                    # ancien résultat : chemin relatif au dossier d'où replay a été lancé (souvent le projet)
                    dossier_abs = Path(dossier).resolve()
                    candidats = [dossier_abs / scenario, dossier_abs.parent.parent / scenario,
                                 dossier_abs / "scenarios" / scenario.name]
                    scenario = next((c for c in candidats if c.exists()), scenario)
                scenario = scenario.as_posix()
                break
        infos[constat["id"]] = {"url": action.get("url"), "appareil": alias(appareil, ALIAS_APPAREILS) if appareil else None,
                                "scenario": scenario}
    return infos


def rapport(dossier, langue="en"):
    """Write both report languages with identical evidence and a selected default."""
    if langue not in ("en", "fr"):
        raise ValueError("Report language must be en or fr")
    dossier = Path(dossier)
    from chaosfolk.reporting import JournalSpool
    source = iterer_journal(dossier)
    try:
        with JournalSpool(source) as journal:
            return _rapport(dossier, langue, journal)
    finally:
        source.close()


def _rapport(dossier, langue, journal):
    constats = lire_json(dossier / "constats.json", {})
    introuvables = []
    proof_summaries = {}
    for constat in constats.get("constats", []):
        for cle, valeur in list((constat.get("preuves") or {}).items()):
            if isinstance(valeur, str) and valeur.endswith(".json"):
                if valeur not in proof_summaries:
                    proof_summaries[valeur] = preuve_resolue(dossier, valeur)
                resume = proof_summaries[valeur]
                if resume is None:
                    introuvables.append(f"{constat.get('id', '?')} / {cle} : {valeur}")
                    resume = {"introuvable": valeur, "nom": Path(valeur).stem, "mode": None, "fois": 0, "casses": 0,
                              "verdict": "introuvable", "captures": [], "raisons": []}
                constat["preuves"][cle] = resume
    config = lire_json(dossier / "config.json", {})
    tirage = lire_json(dossier / "tirage.json", {})
    if tirage:
        config.update({"graine": tirage.get("graine"), "escouade": tirage.get("escouade")})
    personas = lire_json(dossier / "personas.json", {})
    coverage = lire_json(dossier / "coverage.json", {})
    if not isinstance(coverage, dict):
        raise ValueError("coverage.json must be a JSON object")
    coverage = {"requested": tirage.get("themes", []), "results": coverage.get("results", [])}
    application = personas.get("application") if isinstance(personas.get("application"), dict) else {}
    matrices = []
    for path in sorted((dossier / "reproductions").glob("matrix*.json")):
        matrix = lire_json(path)
        if isinstance(matrix, dict) and matrix.get("cells"):
            matrices.append(matrix)
    donnees = {"config": config, "personas": personas, "coverage": coverage,
               "replay_matrices": matrices,
               "journal": None, "constats": constats, "genere": datetime.now().isoformat(timespec="seconds"),
               # ce dont le prompt de correction a besoin, à un seul endroit
               "application": {"nom": application.get("nom") or constats.get("application") or None,
                               "version": constats.get("version") or None, "url": config.get("url"),
                               "commande": None},
               "horde": "chaosfolk",
               "constats_infos": infos_constats(dossier, constats, journal, personas)}
    from .audit_session import existing as existing_audit
    audit_run = existing_audit(dossier)
    if audit_run:
        donnees["audit_session"] = audit_run.snapshot()
        ecrire_json(dossier / "audit-coverage.json", audit_run.snapshot(details=True))
    elif (dossier / "audit-coverage.json").is_file():
        exported = lire_json(dossier / "audit-coverage.json", {})
        if isinstance(exported, dict) and exported.get("export_schema") == 1:
            donnees["audit_session"] = exported
    from chaosfolk.branding import report_branding
    donnees["branding"] = report_branding(dossier)
    from chaosfolk.scoring import score_report
    donnees["score"] = score_report(donnees, journal_metrics=journal.scoring_metrics())
    # tout "<" est échappé : aucune saisie (</script>, <!--<script>) ne peut casser la page
    template = MODELE_RAPPORT.read_text(encoding="utf-8")
    from chaosfolk.reporting import write_reports
    write_reports(dossier, template, donnees, journal, langue)
    cible = dossier / "rapport.html"
    print(f"Report ({langue}): {cible.as_posix()}")
    for x in introuvables:
        print(f"attention : preuve introuvable, {x}")
    return 0


# --------------------------------------------------------------------------
# Commandes du chef
# --------------------------------------------------------------------------

def commande_demarrer(opts):
    """Lance le serveur de la horde en arrière-plan et attend qu'il soit prêt."""
    dossier = Path(opts.dossier or (Path(".horde") / datetime.now().strftime("%Y%m%d-%H%M"))).resolve()
    dossier.mkdir(parents=True, exist_ok=True)
    port = lire_json(FICHIER_ACTIF, {}).get("port")
    if port:
        try:
            with socket.create_connection(("127.0.0.1", int(port)), timeout=1):
                raise SystemExit(f"une horde tourne déjà (port {port}). L'arrêter d'abord : chaosfolk stop")
        except OSError:
            pass
    (dossier / "serveur.json").unlink(missing_ok=True)
    commande = [sys.executable, "-m", "chaosfolk", "serve", *opts.brut, "--folder", str(dossier)]
    with open(dossier / "serveur.log", "a", encoding="utf-8") as journal_serveur:
        processus = subprocess.Popen(commande, stdout=journal_serveur, stderr=subprocess.STDOUT,
                                     stdin=subprocess.DEVNULL, close_fds=True, **options_detache())
    fin = time.time() + opts.app_attente + 60
    while time.time() < fin:
        info = lire_json(dossier / "serveur.json")
        if info:
            print(f"Horde prête : port {info['port']}, navigateur {info['navigateur']}, dossier {dossier.as_posix()}")
            print(f"Jeton du chef : {info['jeton_chef']} (préfixe CHAOSFOLK_LEADER_TOKEN={info['jeton_chef']} pour les commandes réservées)")
            return 0
        if processus.poll() is not None:
            break
        time.sleep(0.5)
    print("la horde n'a pas démarré, voir " + (dossier / "serveur.log").as_posix())
    with suppress(Exception):
        print((dossier / "serveur.log").read_text(encoding="utf-8", errors="replace")[-2000:])
    return 1


def commande_serveur(opts):
    if not opts.dossier:
        raise SystemExit("--folder obligatoire")
    asyncio.run(Horde(opts).lancer_horde())
    return 0


def version_tuple(texte):
    """'1.63.0' en (1, 63, 0) ; les parties non numériques sont ignorées."""
    return tuple(int(x) for x in re.findall(r"\d+", str(texte))[:3])


def agent_installe():
    """(source, cible, état) de l'agent horde-humain : état "ok", "absent", "different" ou "source absente"."""
    source = ICI / "templates" / "agent.md"
    cible = Path.home() / ".claude" / "agents" / f"{AGENT_HUMAIN}.md"
    if not source.exists():
        return source, cible, "source absente"
    if not cible.exists():
        return source, cible, "absent"
    return source, cible, "ok" if cible.read_bytes() == source.read_bytes() else "different"


def commande_verifier(opts):
    """Une ligne OK ou MANQUE par point, puis la commande qui installe ce qui manque. Code 1 s'il manque
    quelque chose d'utile au moteur (l'agent horde-humain n'est pas bloquant)."""
    manques, installer = 0, []

    def point(nom, ok, detail=""):
        nonlocal manques
        print(f"{nom} : {'OK' if ok else 'MANQUE'}" + (f" ({detail})" if detail else ""))
        manques += 0 if ok else 1

    version_python = sys.version.split()[0]
    python_ok = sys.version_info[:2] >= PYTHON_MIN
    point("Python", python_ok, version_python if python_ok
          else f"{version_python} installé, {'.'.join(map(str, PYTHON_MIN))} ou plus demandé")
    minimum = ".".join(map(str, PLAYWRIGHT_MIN))
    try:
        from importlib.metadata import version
        version_pw = version("playwright")
    except Exception:
        version_pw = None
    if version_pw is None or version_tuple(version_pw) < PLAYWRIGHT_MIN:
        point("Playwright", False, (f"{version_pw} installé" if version_pw else "absent") + f", {minimum} ou plus demandé")
        installer.append(f'python -m pip install --upgrade "playwright>={minimum}"')
    else:
        point("Playwright", True, version_pw)
    canal = v = None
    if version_pw is not None:
        with suppress(Exception):
            canal, v = asyncio.run(tester_navigateur())
    if canal:
        point("Navigateur", True, f"{canal} {v}")
    else:
        point("Navigateur", False, "ni Chromium, ni Edge, ni Chrome utilisable")
        installer.append("chaosfolk install-browser")
    point("Modèle du rapport", MODELE_RAPPORT.exists(), "" if MODELE_RAPPORT.exists()
          else f"{MODELE_RAPPORT.as_posix()} absent : réinstaller la Skill")
    point("Lecture d'écran", ECRAN_JS.exists(), "ecran.js" if ECRAN_JS.exists()
          else f"{ECRAN_JS.as_posix()} absent : réinstaller la Skill")
    _, _, etat = agent_installe()
    # l'agent dédié aide les humains à jouer, mais la horde marche sans lui : ce manque n'est pas bloquant
    print(f"Agent {AGENT_HUMAIN} : " + ("OK" if etat == "ok" else
          "MANQUE (chaosfolk setup --agent claude-code)" if etat == "absent" else
          "DIFFÉRENT (copie modifiée ; chaosfolk install-agent --force la remplace)" if etat == "different" else
          f"MANQUE (fichier de la Skill absent : agents/{AGENT_HUMAIN}.md)"))
    if installer:
        print("Pour installer ce qui manque : " + " ; ".join(installer))
    return 1 if manques else 0


def commande_installer_agent(opts):
    """install-agent : copie l'agent horde-humain de la Skill dans ~/.claude/agents/."""
    source, cible, etat = agent_installe()
    if etat == "source absente":
        print(f"erreur : {source.as_posix()} introuvable (la Skill est incomplète)")
        return 1
    if etat == "ok":
        print(f"Agent {AGENT_HUMAIN} : déjà installé.")
        return 0
    if etat == "different":
        if not getattr(opts, "force", False):
            print(f"An agent already exists at {cible.as_posix()}. Use install-agent --force to back it up and replace it.")
            return 1
        backup = cible.with_name(cible.name + "." + datetime.now().strftime("%Y%m%d-%H%M%S-%f") + ".bak")
        with backup.open("xb") as handle:
            handle.write(cible.read_bytes())
        print(f"Previous agent saved to {backup.as_posix()}")
    cible.parent.mkdir(parents=True, exist_ok=True)
    cible.write_bytes(source.read_bytes())
    print(f"Agent {AGENT_HUMAIN} : " + ("remplacé par la version de la Skill" if etat == "different" else "installé")
          + f", fichier {cible.as_posix()}")
    return 0


def process_identity(pid):
    """Capture the identity of a child immediately after Popen creates it."""
    import psutil
    process = psutil.Process(pid)
    return {"pid": pid, "created": process.create_time(),
            "group": pid if os.name == "nt" else os.getpgid(pid),
            "session": None if os.name == "nt" else os.getsid(pid)}


def stop_owned_process(identity):
    """Stop a recorded process tree without trusting URL health or a bare PID.

psutil checks process identity again on terminate/kill. POSIX managed roots must
still own the dedicated process group and session created at launch.
"""
    import psutil
    if (not isinstance(identity, dict) or type(identity.get("pid")) is not int
            or identity["pid"] <= 0 or type(identity.get("created")) not in (float, int)
            or identity.get("group") != identity["pid"]):
        raise ValueError("Missing managed-process identity; refusing to stop a legacy or unverified PID")
    pid = identity["pid"]
    try:
        process = psutil.Process(pid)
        if process.create_time() != identity["created"] or not process.is_running():
            raise ValueError("Managed PID was reused; refusing to stop this process")
        if os.name != "nt" and (identity.get("session") != pid or os.getpgid(pid) != pid or os.getsid(pid) != pid):
            raise ValueError("Managed process group or session no longer matches; refusing to stop it")
        children = process.children(recursive=True)
        targets = [process, *reversed(children)]
        for target in targets:
            with suppress(psutil.NoSuchProcess):
                target.terminate()
        _, alive = psutil.wait_procs(targets, timeout=5)
        for target in alive:
            with suppress(psutil.NoSuchProcess):
                target.kill()
        _, alive = psutil.wait_procs(alive, timeout=5)
        if alive:
            raise ValueError("Managed processes did not stop; ownership record was preserved")
        return True
    except psutil.NoSuchProcess:
        return False


def commande_arreter_app(opts):
    """stop-app : arrête l'application laissée par stop --keep-app (PID app_pid de serveur.json)."""
    dossier = dossier_courant(opts.dossier)
    fichier = dossier / "serveur.json"
    info = lire_json(fichier, {})
    pid = info.get("app_pid")
    actif = lire_json(FICHIER_ACTIF, {})
    if actif.get("port") and actif.get("dossier") and Path(actif["dossier"]).resolve() == dossier.resolve():
        with suppress(OSError):
            with socket.create_connection(("127.0.0.1", int(actif["port"])), timeout=1):
                print("la horde tourne encore dans ce dossier : chaosfolk stop (sans --keep-app) "
                      "arrête aussi l'application")
                return 1
    if not pid:
        print(f"aucune application lancée par la horde n'est notée dans {fichier.as_posix()}")
        return 1
    identity = info.get("app_identity")
    if not isinstance(identity, dict) or identity.get("pid") != pid:
        raise ValueError("Missing managed-process identity; refusing to stop a legacy or unverified PID")
    ok = stop_owned_process(identity)
    ecrire_json(fichier, dict(info, app_pid=None, app_identity=None))
    print(f"application arrêtée (PID {pid})" if ok else f"l'application ne tournait plus (PID {pid})")
    return 0


APPAREILS_FICHE = {"desktop": "desktop computer", "laptop": "laptop", "tablet": "tablet", "mobile": "phone"}


def sheet_command(shell):
    """Quote the exact interpreter and state path for the selected agent shell."""
    executable, state = Path(sys.executable).as_posix(), FICHIER_ACTIF.parent
    # The default state directory needs no option: the user writes this prefix on every action.
    implicit = "CHAOSFOLK_HOME" not in os.environ and state == Path.home() / ".chaosfolk"
    if shell == "powershell":
        quote = lambda value: "'" + value.replace("'", "''") + "'"
    elif shell == "posix":
        from shlex import quote
    else:
        raise ValueError("Shell must be powershell or posix")
    command = f"{quote(executable)} -m chaosfolk" + ("" if implicit else f" --state-dir {quote(state.as_posix())}")
    return "& " + command if shell == "powershell" else command


def commande_fiches(opts):
    """sheets : écrit <dossier>/fiches/<id>.md pour chaque humain de personas.json, depuis le modèle
    "Fiche à envoyer" de references/humain.md. Affiche une ligne par humain."""
    dossier = Path(opts.dossier).resolve()
    personas = lire_json(dossier / "personas.json", {})
    if not personas.get("humains"):
        raise SystemExit(f"aucun humain dans {(dossier / 'personas.json').as_posix()} (lancer draw d'abord)")
    from chaosfolk.checks import sheet_text
    texte_md = (ICI / "templates" / "persona.md").read_text(encoding="utf-8")
    trouve = re.search(r"## Agent sheet\s+```text\n(.*?)\n```", texte_md, re.S)
    if not trouve:
        raise SystemExit('modèle introuvable : section "## Agent sheet" de references/humain.md')
    modele = trouve.group(1)
    application = personas.get("application") if isinstance(personas.get("application"), dict) else {}
    shell = getattr(opts, "shell", "powershell" if os.name == "nt" else "posix")
    # Windows PowerShell 5.1 n'a pas && : if ($?) arrête aussi la suite après un code de sortie non nul
    commun = {"application": application.get("nom") or "the application", "horde": sheet_command(shell),
              "enchainer": "A; if ($?) { B }" if shell == "powershell" else "A && B",
              "donnees": opts.donnees, "interdits": opts.interdits}
    (dossier / "fiches").mkdir(exist_ok=True)

    def liste(v):
        return " ; ".join(str(x) for x in v) if isinstance(v, list) else str(v or "")

    for h in personas["humains"]:
        if not isinstance(h, dict) or not h.get("id"):
            print("attention : une fiche sans id est ignorée")
            continue
        validate_id(h["id"])
        appareil = alias(h.get("appareil") or "desktop", ALIAS_APPAREILS)
        valeurs = dict(commun, id=h["id"], nom=h.get("nom"), age=h.get("age"), metier=h.get("metier"),
                       intention=h.get("intention"), histoire=h.get("histoire"), aisance=h.get("aisance"),
                       patience=h.get("patience"), habitudes=liste(h.get("habitudes")), manies=liste(h.get("manies")),
                       appareil=APPAREILS_FICHE.get(appareil, appareil), contexte=h.get("contexte") or "",
                       budget=h.get("budget") or opts.budget, verifications=sheet_text(h.get("checks") or []))
        champs = set(re.findall(r"\{([a-z_]+)\}", modele))
        vides = sorted(k for k in champs & set(valeurs) if valeurs[k] in (None, "") and k != "contexte")
        inconnus = sorted(champs - set(valeurs))

        def remplir(x):
            cle = x.group(1)
            if cle not in valeurs:
                return x.group(0)
            return "" if valeurs[cle] is None else str(valeurs[cle])

        fichier = dossier / "fiches" / f"{h['id']}.md"
        texte = re.sub(r"\{([a-z_]+)\}", remplir, modele)
        if h.get("audit_tasks"):
            work = ["AUDIT TASKS", "Run only these assigned checks, at the stated pages. Record each outcome before done.",
                    "Before each task, use check-start TASK_ID. It checks that the test is still enabled.",
                    "Use check-result TASK_ID passed|failed|blocked|inconclusive \"observed outcome and expected rule\".",
                    "A result records an observation; the coordinator must prove any defect with replay.",
                    "If the audit is stopped or your checks are disabled, finish immediately; never restart it."]
            for task in h["audit_tasks"]:
                work += [f"- Task {task['task_id']} at {task['route'] or 'the relevant product journey'}: {task['title']}",
                         task["try"], "Expected: " + task["expect"]]
            texte += "\n\n" + "\n".join(work)
        fichier.write_text("\n".join(x.rstrip() for x in texte.splitlines()) + "\n", encoding="utf-8")
        print(f"{h['id']} : {fichier.as_posix()}"
              + (f" (champs vides : {', '.join(vides)})" if vides else "")
              + (f" (champs inconnus laissés tels quels : {', '.join(inconnus)})" if inconnus else ""))
    return 0


def commande_trace(opts):
    """trace : les gestes d'un humain, une ligne chacun, lus dans le journal (le chef ne lit pas journal.jsonl).
    Avec --around N : les gestes N-3 à N+3 et l'écran du geste N."""
    dossier = dossier_courant(opts.dossier)
    evts = [e for e in iterer_journal(dossier) if e.get("h") == opts.humain]
    actions = [e for e in evts if e["type"] == "action"]
    if not actions:
        raise SystemExit(f"aucun geste de {opts.humain} dans le journal de {dossier.as_posix()}")
    choisis = evts
    if opts.autour is not None:
        bas, haut = opts.autour - 3, opts.autour + 3
        dans = [i for i, e in enumerate(evts) if e["type"] == "action" and bas <= e.get("n", 0) <= haut]
        choisis = evts[dans[0]:dans[-1] + 1] if dans else []
    derniere = None
    for e in choisis:
        # la capture n'est redite que quand elle change (un regard garde la capture du geste précédent)
        capture = e.get("capture") if e["type"] == "action" else None
        ligne = ligne_trace(dict(e, capture=None) if capture and capture == derniere else e, dossier)
        if capture:
            derniere = capture
        if ligne:
            print(ligne)
    if opts.autour is not None:
        geste = next((e for e in actions if e.get("n") == opts.autour), None)
        if geste is None:
            print(f"(pas de geste n{opts.autour} pour {opts.humain})")
        else:
            ecran = geste.get("ecran") or []
            print(f"--- écran après le geste {opts.autour} ({len(ecran)} lignes gardées au journal) ---")
            for x in ecran[:LIGNES_TRACE_ECRAN]:
                print(x)
            if len(ecran) > LIGNES_TRACE_ECRAN:
                print(f"... {len(ecran) - LIGNES_TRACE_ECRAN} lignes de plus")
    return 0


def ligne_trace(e, dossier):
    """Une ligne de trace pour un geste (ou un refus du garde-fou), None pour les autres événements."""
    def court(texte, n=90):
        texte = re.sub(r"\s+", " ", str(texte or "")).strip()
        return texte if len(texte) <= n else texte[:n - 3] + "..."

    if e["type"] == "garde-fou" and e.get("refus"):
        return f"- {e.get('action')} refusé par le garde-fou : {court(e.get('message'), 120)}"
    if e["type"] == "erreur_commande":
        return f"- commande mal écrite : {court(e.get('texte'))} ({court(e.get('message'), 80)})"
    if e["type"] != "action":
        return None
    args = e.get("args") or {}
    cible = (e.get("cible") or {}).get("nom")
    quoi = (f'"{court(cible, 50)}"' if cible else "") or next(
        (f'"{court(args[k], 50)}"' for k in ("texte", "url", "touche", "option", "ref", "sens", "quoi", "secondes")
         if args.get(k) not in (None, "")), "")
    if cible and args.get("texte") and e["action"] == "type":
        quoi += f' = "{court(args["texte"], 40)}"'
    adresse = urlparse(e.get("url") or "")
    parties = [f"{e.get('n')} {e['action']}" + (f" {quoi}" if quoi else ""), adresse.path or "/"]
    resultat = "ok" if e.get("resultat") == "ok" else "raté"
    if e.get("message"):
        resultat += f" ({court(e['message'], 100)})"
    parties.append(resultat)
    if e.get("pannes"):
        parties.append("pannes " + ",".join(e["pannes"]))
    if e.get("pense"):
        parties.append(f'pense "{court(e["pense"], 110)}"')
    if e.get("dit"):
        parties.append(f'dit "{court(e["dit"], 90)}"')
    if e.get("capture"):
        parties.append("capture " + (Path(dossier) / e["capture"]).as_posix())
    return " ; ".join(parties)


def commande_humains(opts):
    return relayer({"cmd": "humans", "fichier": str(Path(opts.fichier).resolve())}, delai=600)


def commande_panne(opts):
    params = {cle: getattr(opts, cle) for cle in PARAMS_PANNE}
    return relayer({"cmd": "fault", "type": opts.type, "humains": opts.humains, "a": opts.a,
                    "apres_actions": opts.apres_actions, "duree": opts.duree, "params": params, "note": opts.note})


def commande_tirer(opts):
    """Tire au sort une horde (escouade, graine) et écrit personas.json et tirage.json."""
    from chaosfolk import draw as tirage
    from chaosfolk.checks import known_pages
    from chaosfolk import campaigns
    explore = None
    if opts.project:
        explore = campaigns.unexplored(campaigns.read(campaigns.project_dir(opts.project) / "map.json", {}), limit=24)
    shared = [x.strip() for x in (opts.shared or "").split(";") if x.strip()]
    if opts.sessions == "coordinated" and not shared:
        raise ValueError("--sessions coordinated needs --shared with at least one test object")
    roles = []
    for item in (opts.roles or "").split(";"):
        if item.strip():
            role, _, state = item.partition("=")
            roles.append((role.strip(), state.strip() or None))
    graine = opts.graine if opts.graine is not None else tirage.graine_aleatoire()
    objectifs = [o.strip() for o in opts.objectifs.split(";") if o.strip()]
    if len(objectifs) == 1 and Path(objectifs[0]).is_file():
        objectifs = lire_json(objectifs[0])
    metiers = [m.strip() for m in opts.metiers.split(";") if m.strip()] if opts.metiers else None
    selected_faults = [name.strip() for name in opts.faults.split(",")] if opts.faults is not None else None
    personas, plan = tirage.tirer_horde(opts.escouade, opts.nombre, objectifs, graine,
                                        {"nom": opts.application or "Test app", "url": opts.url or ""}, metiers,
                                        budget=opts.budget, fault_types=selected_faults, themes=opts.themes,
                                        checks=opts.checks, detected=known_pages(opts.dossier), countries=opts.countries,
                                        explore=explore, sessions=opts.sessions, shared=shared, roles=roles)
    from .audit_session import existing as existing_audit, catalog as audit_catalog
    session = existing_audit(opts.dossier)
    if session:
        if opts.checks != "auto":
            raise ValueError("This audit uses its saved selection. Change it in the dashboard or audit-run configure.")
        refusal = session.gate()
        if refusal:
            raise ValueError(refusal)
        from . import checks as qa_checks
        wave = session.next_wave()
        renamed, kept = {}, []
        config = session.snapshot()["config"]
        for index, human in enumerate(personas["humains"], 1):
            new_id = f"h{wave:03d}{index:02d}"
            tasks = session.claim(new_id, "agent", qa_checks.per_user(opts.budget))["tasks"]
            if not tasks:
                continue
            renamed[human["id"]] = new_id
            human["intention"] = human["intention"].replace(human["id"].upper(), new_id.upper())
            human["id"], human["audit_tasks"] = new_id, tasks
            human["retain_browser"] = opts.sessions == "coordinated"
            if tasks[0]["route"]:
                human["depart"] = tasks[0]["route"]
            selected = [audit_catalog()[t["check_id"]] for t in tasks if audit_catalog()[t["check_id"]]["kind"] == "qa-check"]
            human["checks"] = qa_checks.assign(graine, selected, 1, max(7, len(selected) * 7), qa_checks.countries(opts.countries))[0]
            human["intention"] += " Complete the audit tasks first and report every outcome with check-result."
            kept.append(human)
        personas["humains"] = kept
        if not kept:
            raise ValueError("No pending agent tasks. Complete reconnaissance or handle the coordinator/audit queue; do not spawn idle users.")
        fault_selection = session.fault_selection()
        plan["pannes"] = [dict(fault, humains=renamed[fault["humains"]]) for fault in plan["pannes"]
                          if fault["humains"] in renamed and fault["type"] in fault_selection]
        plan["checks"] = {"selection": "audit-plan", "pool": [item["id"] for item in audit_catalog().values()
                          if item["kind"] == "qa-check" and session.selected(item, config)],
                          "assigned": {h["id"]: [task["check_id"] for task in h["audit_tasks"]] for h in kept}}
        plan["nombre"] = len(kept)
        # Keep prior users available to extraction and reporting across waves.
        previous = lire_json(Path(opts.dossier) / "personas.json", {}).get("humains", [])
        personas["humains"] = previous + kept
    dossier = Path(opts.dossier)
    ecrire_json(dossier / "personas.json", personas)
    ecrire_json(dossier / "tirage.json", plan)
    current_users = kept if session else personas["humains"]
    print(f"Seed {graine}, squad {opts.escouade}, {len(current_users)} users, budget {opts.budget}: {(dossier / 'personas.json').as_posix()}")
    for h in current_users:
        print(f"  {h['id']} {h['nom']:<22} {h['profil']:<20} {h['appareil']:<10} {h['condition']}")
    if plan["checks"]["pool"]:
        print(f"{len(plan['checks']['pool'])} QA checks in the pool ({opts.checks}); each user's share is on its sheet.")
    print(f"{len(plan['pannes'])} faults: run `chaosfolk drawn-faults {(dossier / 'tirage.json').as_posix()}` "
          "after creating the users. The seed, goals, catalog, selected faults, count and budget determine this draw.")
    return 0


def commande_pannes_tirees(opts):
    """Programme les pannes d'un tirage (créer les humains d'abord)."""
    plan = lire_json(opts.tirage)
    code = 0
    for p in plan.get("pannes", []):
        params = {cle: p[cle] for cle in PARAMS_PANNE if cle in p}
        p = dict(p, type=alias(p["type"], ALIAS_PANNES))
        print(f"{p['type']} pour {p['humains']} : ", end="")
        code |= relayer({"cmd": "fault", "type": alias(p["type"], ALIAS_PANNES), "humains": p["humains"], "a": None,
                         "apres_actions": p.get("apres_actions"), "duree": p.get("duree"), "params": params,
                         "note": f"tirage {plan.get('graine')}", "scheduled": True})
    return code


def commande_analyser(opts):
    analyser(dossier_courant(opts.dossier))
    return 0


def lire_attendu(texte):
    """Valeur de --expect : du JSON (une règle ou une liste), ou le chemin d'un fichier JSON."""
    texte = str(texte).strip()
    if texte and texte[0] not in "[{" and Path(texte).is_file():
        texte = Path(texte).read_text(encoding="utf-8-sig")
    try:
        attendu = json.loads(texte)
    except ValueError as e:
        raise ValueError(f"--expect : JSON illisible ({e}). Exemple : "
                         '\'[{"type": "text-visible", "texte": "Offre enregistrée"}]\'') from None
    return valider_attendu(attendu, "--expect")


def extraire_plusieurs(dossier, hids):
    """Scénario coordonné : les gestes de plusieurs humains dans l'ordre du journal, chacun dans sa session
    (son état et son appareil). Les pannes ne sont pas reprises, leur ancrage par numéro d'action serait ambigu."""
    personas = lire_personas(dossier)
    config = lire_json(Path(dossier) / "config.json", {})
    states = {hid: _ExtractionState(dossier, hid, personas.get(hid, {}), config) for hid in hids}
    for event in iterer_journal(dossier):
        human = event.get("h")
        if human is None:
            for state in states.values():
                state.accept(event)
        elif human in states:
            states[human].accept(event)
    parts = {hid: state.result() for hid, state in states.items()}
    etapes = sorted(((dict(e, session=hid)) for hid, sc in parts.items() for e in sc["etapes"]),
                    key=lambda e: e.get("t") or 0)
    premier = parts[hids[0]]
    sessions = {hid: {k: sc[k] for k in ("etat", "appareil", "depart", "horloge") if sc.get(k)} for hid, sc in parts.items()}
    perdues = sum(len(sc["pannes"]) for sc in parts.values())
    return dict(premier, nom="-".join(hids), humain=",".join(hids), sessions=sessions, etapes=etapes, pannes=[],
                avertissement=f"{perdues} panne(s) non reprises dans un scénario à plusieurs sessions" if perdues else None)


def commande_extraire(opts):
    attendu = lire_attendu(opts.attendu) if opts.attendu else None
    hids = [h.strip() for h in opts.humain.split(",") if h.strip()]
    if len(hids) > 1 and opts.jusqua is not None:
        raise ValueError("--up-to works with one user; cut a coordinated scenario by editing its steps")
    scenario = extraire_plusieurs(dossier_courant(opts.dossier), hids) if len(hids) > 1 else \
        extraire(dossier_courant(opts.dossier), opts.humain, opts.jusqua)
    if attendu is not None:
        scenario["attendu"] = attendu
        scenario.pop("a_completer", None)
    ecrire_json(opts.sortie, scenario)
    print(f"{len(scenario['etapes'])} étapes, {len(scenario['pannes'])} panne(s) : fichier {Path(opts.sortie).as_posix()}")
    for k, etape in enumerate(scenario["etapes"], 1):
        args = etape.get("args") or {}
        cible = (etape.get("cible") or {}).get("nom")
        quoi = f'"{cible[:50]}"' if cible else next((f'"{str(args[c])[:50]}"' for c in ("texte", "url", "touche", "option", "sens")
                                                     if args.get(c) not in (None, "")), "")
        if cible and args.get("texte"):
            quoi += f' = "{str(args["texte"])[:40]}"'
        print(f"  {k}. {etape['session'] + ' ' if etape.get('session') else ''}n{etape.get('n')} {etape['action']} {quoi}".rstrip()
              + (" (raté à l'origine)" if etape.get("echec_original") else ""))
    for p in scenario["pannes"]:
        print(f"  panne {p['type']} : après le geste n{p.get('debut_n')}"
              + (f", jusqu'au geste n{p['fin_n']}" if p.get("fin_n") is not None else ", jusqu'à la fin"))
    print("  attendu : " + json.dumps(scenario["attendu"], ensure_ascii=False))
    return 0



def validate_id(value):
    """IDs appear in filenames and commands, so accept only a portable subset."""
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,63}", value):
        raise ValueError("Persona id must start with a letter and contain at most 64 letters, digits, _ or -")
    if re.fullmatch(r"(?i:con|prn|aux|nul|com[1-9]|lpt[1-9])", value):
        raise ValueError("Persona id is a reserved Windows filename")
    return value


def positive_int(value):
    number = int(value)
    if not 1 <= number <= 10000:
        raise argparse.ArgumentTypeError("expected an integer between 1 and 10000")
    return number


def construire_parseur():
    """Analyse des commandes du chef d'orchestre : une sous-commande par commande."""
    parseur = argparse.ArgumentParser(prog="chaosfolk", epilog=
        "Additional commands (COMMAND --help): chaos, regression, planning, visual, privacy, usage, benchmark, integrations, mcp.")
    sous = parseur.add_subparsers(dest="commande", required=True)

    def commande(nom, fonction, parents=()):
        sp = sous.add_parser(nom, parents=list(parents), prog=f"chaosfolk {nom}")
        sp.set_defaults(fn=fonction)
        return sp

    lancement = argparse.ArgumentParser(add_help=False)
    lancement.add_argument("--url", required=True)
    lancement.add_argument("--folder", dest="dossier")
    lancement.add_argument("--app-command", dest="app_commande")
    lancement.add_argument("--app-folder", dest="app_dossier")
    lancement.add_argument("--app-wait", dest="app_attente", type=positive_int, default=120, help="secondes d'attente de l'application")
    lancement.add_argument("--channel", dest="canal")
    lancement.add_argument("--port", type=int)
    lancement.add_argument("--project", help="explicit project name kept with the session and its history, such as shop-front")
    lancement.add_argument("--chaos-policy", help="optional JSON/TOML injection policy; no additional model calls")
    lancement.add_argument("--dry-run", action="store_true", help="simulate injections; browser exploration still runs")
    lancement.add_argument("--visible", action="store_true")
    lancement.add_argument("--idle", dest="inactivite", type=positive_int, default=3600, help="arrêt automatique après N s sans commande")
    lancement.add_argument("--budget", type=positive_int, default=20, help="gestes par humain (sa fiche peut en donner un autre)")
    lancement.add_argument("--level", choices=("low", "medium", "high"), help="exploration preset; explicit --budget takes precedence")
    lancement.add_argument("--human-duration", dest="duree_humain", type=positive_int, default=600,
                           help="durée maximale d'un humain, en secondes")
    lancement.add_argument("--max-duration", dest="duree_max", type=positive_int, default=1800,
                           help="durée maximale de la horde, en secondes, comptée depuis le premier geste d'un humain")
    commande("launch", commande_demarrer, [lancement])
    commande("start", commande_demarrer, [lancement])  # ancien nom, refusé par Codex sous Windows avec une adresse http
    commande("serve", commande_serveur, [lancement])
    commande("check", commande_verifier)
    commande("install-agent", commande_installer_agent).add_argument("--force", action="store_true", help="back up and replace an existing custom agent")
    commande("humans", commande_humains).add_argument("fichier")
    p = commande("chaos-control", lambda a: relayer({"cmd": "chaos-control", "action": a.action}))
    p.add_argument("action", choices=("status", "pause", "resume", "simulate", "live", "enable", "disable", "schedule-on", "schedule-off"))
    p = commande("sheets", commande_fiches)
    p.add_argument("--folder", dest="dossier", required=True)
    p.add_argument("--data", dest="donnees", required=True, help="données fictives permises (rangées dans la règle des données)")
    p.add_argument("--forbidden", dest="interdits", required=True, help="ce que les humains ne doivent jamais faire")
    p.add_argument("--budget", type=positive_int, default=20, help="gestes par humain (sa fiche peut en donner un autre)")
    p.add_argument("--level", choices=("low", "medium", "high"), help="exploration preset; explicit --budget takes precedence")
    p.add_argument("--shell", choices=("powershell", "posix"), default="powershell" if os.name == "nt" else "posix",
                   help="shell used by persona agents (Windows default: powershell)")

    p = commande("fault", commande_panne)
    p.add_argument("type", choices=sorted(PANNES))
    p.add_argument("--humans", dest="humains", default="tous", help="identifiants séparés par des virgules, ou all (tous)")
    p.add_argument("--at", dest="a", type=float, help="dans N secondes")
    p.add_argument("--after-actions", dest="apres_actions", type=int, help="quand l'humain a fait N gestes")
    p.add_argument("--duration", dest="duree", type=float, help="durée en secondes (sinon jusqu'à fault-end)")
    p.add_argument("--pattern", dest="motif", help="adresses touchées, motif glob (ex. */api/*)")
    p.add_argument("--method", dest="methode")
    p.add_argument("--status", dest="statut", type=int, help="code HTTP pour http-error (500 par défaut)")
    p.add_argument("--delay", dest="delai", type=int, help="ms de retard pour slow (3000 par défaut)")
    p.add_argument("--times", dest="fois", type=positive_int, help="nombre de réponses perdues (1 par défaut)")
    p.add_argument("--key", dest="cle", help="clé de stockage à corrompre (motif glob)")
    p.add_argument("--advance", dest="avance", help="saut d'horloge : 72h, 3j, 15min")
    p.add_argument("--size", dest="taille", help="nouvelle taille de fenêtre : 390x844")
    p.add_argument("--note")

    commande("fault-end", lambda a: relayer({"cmd": "fault-end", "id": a.id})).add_argument("id")
    for nom in ("faults", "status", "network"):
        commande(nom, lambda a: relayer({"cmd": a.commande}))
    p = commande("stop", lambda a: relayer({"cmd": "stop", "garder_app": a.garder_app}))
    p.add_argument("--keep-app", dest="garder_app", action="store_true", help="arrêter la horde mais laisser l'application tourner")
    commande("stop-app", commande_arreter_app).add_argument("--folder", dest="dossier")
    commande("release", lambda a: relayer({"cmd": "release", "h": a.humain})).add_argument("humain")
    p = commande("save-state", lambda a: relayer({"cmd": "save-state", "h": a.humain,
                                                   "fichier": str(Path(a.fichier).resolve())}))
    p.add_argument("humain")
    p.add_argument("fichier")
    p = commande("inspect", lambda a: relayer({"cmd": "inspect", "h": a.humain, "js": chemin_msys(a.js)}))
    p.add_argument("humain")
    p.add_argument("js", help="expression JavaScript évaluée dans l'onglet courant de l'humain")

    p = commande("draw", commande_tirer)
    p.add_argument("--squad", dest="escouade", default="ux", help="ux (UX et ergonomie)")
    p.add_argument("--count", dest="nombre", type=int, default=4)
    p.add_argument("--budget", type=positive_int, default=20, help="action allowance used to schedule reachable faults")
    p.add_argument("--level", choices=("low", "medium", "high"), help="exploration preset; explicit --count or --budget take precedence")
    p.add_argument("--seed", dest="graine", type=int, help="pour refaire la même horde ; tirée au hasard sinon, et affichée")
    p.add_argument("--faults", help="comma-separated fault types, none, or all; omit for the default catalog")
    p.add_argument("--themes", help="comma-separated themes, or all; see chaosfolk themes")
    p.add_argument("--checks", default="auto",
                   help="QA checks handed to users: auto (selected themes, safe scope), all, none, or check ids")
    p.add_argument("--countries", help="country codes for test values, such as FR,GB,US (default: every country)")
    p.add_argument("--project", help="use this project's journey map to send users towards less explored routes")
    p.add_argument("--sessions", choices=("independent", "coordinated"), default="independent",
                   help="independent: each user tags and keeps its own data; coordinated: users share --shared objects")
    p.add_argument("--shared", help="coordinated mode: test objects every user works on, separated by semicolons")
    p.add_argument("--roles", help='roles with saved states, such as "editor=etats/editor.json;reader=etats/reader.json"')
    p.add_argument("--objectives", dest="objectifs", required=True,
                   help="ce que les gens viennent faire, séparés par des points-virgules, ou un fichier JSON (liste)")
    p.add_argument("--jobs", dest="metiers", help="métiers des humains, séparés par des points-virgules (sinon un catalogue)")
    p.add_argument("--app-name", dest="application", help="nom de l'application testée")
    p.add_argument("--url")
    p.add_argument("--folder", dest="dossier", required=True)
    commande("drawn-faults", commande_pannes_tirees).add_argument("tirage")
    commande("analyze", commande_analyser).add_argument("--folder", dest="dossier")
    p = commande("trace", commande_trace)
    p.add_argument("humain")
    p.add_argument("--around", dest="autour", type=int, help="gestes N-3 à N+3 et l'écran du geste N")
    p.add_argument("--folder", dest="dossier")
    p = commande("extract", commande_extraire)
    p.add_argument("humain")
    p.add_argument("--up-to", dest="jusqua", type=int)
    p.add_argument("--folder", dest="dossier")
    p.add_argument("--output", dest="sortie", required=True)
    p.add_argument("--expect", dest="attendu", help="attendu en JSON (une règle ou une liste), ou un fichier JSON")
    p = commande("replay", lambda a: asyncio.run(rejouer(a)))
    p.add_argument("scenario", nargs="+", help="un ou plusieurs scénarios, rejoués dans un seul navigateur")
    p.add_argument("--times", dest="fois", type=positive_int, default=3)
    p.add_argument("--fail-on-bug", action="store_true", help="exit 1 for failed assertions, 2 for invalid trials")
    p.add_argument("--control", dest="temoin", action="store_true", help="rejouer sans les pannes")
    p.add_argument("--environment", help="JSON file with bounded fixture prepare/verify commands and build metadata")
    p.add_argument("--baseline", help="team-supplied reference scenario; runs both journeys with and without faults")
    p.add_argument("--with-control", dest="avec_temoin", action="store_true",
                   help="rejouer aussi le témoin sans les pannes, en même temps")
    p.add_argument("--sequential", dest="sequentiel", action="store_true", help="essais l'un après l'autre (serveur à état partagé)")
    p.add_argument("--persist", help="after the steps, verify with recipes: reload, revisit, new-tab, local-only, back, "
                                     "retry (comma-separated, or all); one series per recipe")
    p.add_argument("--name", dest="nom")
    p.add_argument("--output", dest="sortie", help="dossier des résultats (par défaut : reproductions/ à côté du scénario)")
    p.add_argument("--visible", action="store_true")
    p.add_argument("--channel", dest="canal")
    from chaosfolk import qa
    p = commande("fields", qa.command_fields)
    p.add_argument("humain", help="user whose current tab is analysed, usually the scout e0")
    p.add_argument("--save", help="add this page to a fields.json file (draw reads <folder>/fields.json)")
    p.add_argument("--json", action="store_true")
    from chaosfolk import audit
    p = commande("audit", audit.command_audit)
    p.add_argument("humain", help="user whose current tab is audited, usually the scout e0")
    p.add_argument("--viewports", default=audit.DEFAULT_VIEWPORTS,
                   help="comma-separated WIDTHxHEIGHT sizes checked one after the other; the tab is restored afterwards")
    p.add_argument("--keyboard", action="store_true", help="also tab through the page to check reachability and focus")
    p.add_argument("--name", dest="nom", help="file name for the audit evidence (default: from the page address)")
    p = commande("vary", lambda a: asyncio.run(qa.vary(a)))
    p.add_argument("scenario")
    cible = p.add_mutually_exclusive_group(required=True)
    cible.add_argument("--step", type=int, help="source action number (n) of the type step to vary")
    cible.add_argument("--field", help="label of the typed field to vary (its last type step)")
    valeurs = p.add_mutually_exclusive_group(required=True)
    valeurs.add_argument("--check", help="use the test values of this catalog check")
    valeurs.add_argument("--values", help='JSON list, {"valid": [...], "invalid": [...]}, or a JSON file')
    p.add_argument("--countries", help="with --check: only universal values and these countries, such as FR,GB,US")
    p.add_argument("--accept", help="assertions that must hold for a valid value (JSON or file)")
    p.add_argument("--reject", help="assertions that must hold for an invalid value (JSON or file)")
    p.add_argument("--times", dest="fois", type=positive_int, default=1)
    p.add_argument("--parallel", action="store_true", help="run values in parallel (the backend must isolate them)")
    p.add_argument("--persist", choices=("reload", "revisit", "new-tab", "local-only", "back", "retry"),
                   help="verify each value after this recipe, for example reload")
    p.add_argument("--fail-on-bug", action="store_true", help="exit 1 when a value breaks its assertions, 2 when a trial is invalid")
    p.add_argument("--name", dest="nom")
    p.add_argument("--output", dest="sortie")
    p.add_argument("--visible", action="store_true")
    p.add_argument("--channel", dest="canal")
    p = commande("compare", lambda a: asyncio.run(qa.compare(a)))
    p.add_argument("scenario_a")
    p.add_argument("scenario_b")
    p.add_argument("--expect", dest="attente", choices=("same", "different"), default="same",
                   help="same: any difference is a failure (enumeration); different: identical outcomes fail")
    p.add_argument("--ignore", action="append", default=[], help="regular expression masked before comparing (repeatable)")
    p.add_argument("--times", dest="fois", type=positive_int, default=3)
    p.add_argument("--fail-on-bug", action="store_true", help="exit 1 when the outcome breaks the expectation, 2 when a trial is invalid")
    p.add_argument("--name", dest="nom")
    p.add_argument("--output", dest="sortie")
    p.add_argument("--visible", action="store_true")
    p.add_argument("--channel", dest="canal")
    def generate_report(a):
        from chaosfolk.language import choose_language
        return rapport(dossier_courant(a.dossier), choose_language(a.lang))
    p = commande("report", generate_report)
    p.add_argument("--folder", dest="dossier")
    p.add_argument("--lang", choices=("en", "fr"), help="language of rapport.html; prompted when omitted in an interactive shell")
    return parseur


def apply_level(opts, argv):
    """Fill a selected preset while preserving explicitly provided count and budget."""
    if not getattr(opts, "level", None):
        return opts
    from chaosfolk.budgets import PRESETS
    preset = PRESETS[opts.level]
    provided = lambda name: any(arg == name or arg.startswith(name + "=") for arg in argv)
    if not provided("--budget"):
        opts.budget = preset["actions_per_user"]
    if opts.commande == "draw" and not provided("--count"):
        opts.nombre = preset["users"]
    return opts


def principal(argv=None):
    """Point d'entrée : un geste d'humain (`h01 click r12`) ou une commande du chef (`fault ...`)."""
    utf8()
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(__doc__)
        print(AIDE_HUMAIN)
        return 0
    refuser_anciens_mots(argv)
    if argv[0] not in COMMANDES_CHEF:
        return commande_humain(argv)
    if argv[0] in COMMANDES_LOURDES:
        charger_moteur()
    opts = construire_parseur().parse_args(argv)
    apply_level(opts, argv)
    opts.brut = argv[1:]
    try:
        return opts.fn(opts)
    except ValueError as e:
        print(f"erreur : {e}")
        return 1


if __name__ == "__main__":
    sys.exit(principal())
