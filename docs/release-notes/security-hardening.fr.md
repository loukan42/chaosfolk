# Durcissement sécurité pour un usage en entreprise

Une revue de sécurité menée en octobre 2026 sur le moteur, le tableau de bord,
les rapports, l'export confidentiel et les installateurs n'a trouvé aucun
problème critique, et une série de faiblesses moyennes et faibles que cette
version corrige. Le dépôt suit désormais un processus de développement sécurisé
documenté, aligné sur l'ISO/IEC 27001:2022, pour qu'une entreprise puisse
adopter Chaosfolk sur des preuves plutôt que sur la confiance.

## Ce qui change pour vous

- **Les preuves restent dans le dossier de session.** Les noms d'audit, les
  tailles d'écran, les noms de téléchargement et les chemins de preuve des
  campagnes sont validés avant toute lecture ou écriture ; un `--name ../x`
  maladroit ou injecté est refusé avec un message clair.
- **Les secrets ne sortent pas dans les rapports.** Le texte saisi dans les
  champs mot de passe, code à usage unique et « afficher le mot de passe » est
  masqué dans les captures, dans le texte d'écran lu par les agents et dans tous
  les rapports ; il reste dans le journal privé pour que le rejeu fonctionne.
  L'export confidentiel (`chaosfolk privacy`) caviarde aussi les JWT, les
  identifiants HTTP Basic, les en-têtes cookie et authorization et les
  identifiants encodés en formulaire.
- **Moins d'exposition des identifiants du moteur.** Les hooks chaos et les
  exécuteurs k6 ou Appium ne reçoivent plus le jeton du chef ; les jetons sont
  comparés en temps constant ; le tableau de bord répond aux erreurs sans
  chemin local ni bannière de version Python ; le répertoire d'état est
  réservé à son propriétaire dès sa création.
- **Des intégrations locales plus sûres.** Git tourne dans vos dépôts avec
  `core.fsmonitor`, les hooks et les diff externes désactivés ; la vérification
  de disponibilité ne suit plus les redirections ; les hooks de reproductibilité
  s'exécutent dans leur propre session de processus ; les captures d'audit
  appliquent les mêmes masques que les autres.
- **Les rapports portent une Content-Security-Policy** qui interdit tout accès
  réseau, en seconde barrière derrière le rendu en texte seul.
- **Des installateurs épinglés et vérifiables.** `install.sh` et `install.ps1`
  installent une version publiée par défaut, vérifient l'empreinte de l'archive
  quand `CHAOSFOLK_SHA256` est défini, peuvent refuser de télécharger uv
  (`CHAOSFOLK_REQUIRE_UV=1`) et acceptent un miroir interne (`CHAOSFOLK_SOURCE`).
  L'empreinte de l'archive 0.8.0 figure dans le README.
- **Un processus documenté.** [SECURITY.md](../../SECURITY.md) donne le canal de
  signalement, les délais de réponse et les versions maintenues.
  [docs/security.md](../security.md) contient le modèle de menace, les
  contrôles du moteur, le cycle de développement sécurisé, la correspondance
  avec l'annexe A de l'ISO/IEC 27001:2022, une liste de durcissement pour les
  environnements gérés et le registre des risques acceptés.

## Pour les contributeurs

La CI installe des dépendances verrouillées par empreinte, épingle chaque action
GitHub sur un commit et ajoute CodeQL, bandit, pip-audit avec un SBOM CycloneDX,
gitleaks, zizmor, la revue des dépendances et OpenSSF Scorecard. Dependabot,
CODEOWNERS et les hooks pre-commit sont configurés. `chaosfolk install-browser`
n'accepte plus que `--with-deps`, `--force` et `--dry-run`.

## Limites

Chaosfolk reste un outil de test, pas un bac à sable : le mode exploration
autorise la navigation HTTP(S) sans liste d'origines, le jeton du chef peut
exécuter du JavaScript arbitraire dans le navigateur de test, et la commande de
l'application s'exécute avec vos droits. Le registre des risques acceptés du
guide de sécurité liste ces points avec les mesures compensatoires.

Les notes de version sont fournies en anglais et en français pour chaque
version, les deux étant liées depuis le README et le changelog.

[English version](security-hardening.en.md)
