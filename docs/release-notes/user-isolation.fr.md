# Humains simulés isolés et exploration par le parcours

Un dérivé de Chaosfolk a passé ses propres revues de sécurité et des essais sur le terrain.
Cette version reprend dans le moteur ce qui s'applique ici. Deux sujets : un humain simulé ne peut
plus agir au-delà de son navigateur, et une exploration commence par le parcours métier au lieu
de s'en remettre au hasard.

## Ce qui change pour vous

- **Les humains lancent une commande à part.** Les fiches appellent
  `python -P -m chaosfolk.user --key CLÉ h01 look` au lieu de `chaosfolk h01 look`. Cette commande
  n'accepte que les gestes d'un humain et refuse toute commande du chef : vous pouvez l'autoriser
  une fois pour la séance sans autoriser `serve --app-command` ni `replay`. Relancez
  `chaosfolk sheets` après la mise à jour ; `chaosfolk humans` affiche la commande de chaque humain,
  ce qui permet au chef de jouer l'éclaireur. Avec le jeton du chef, `chaosfolk e0 look` marche
  toujours pour le chef.
- **Une clé par humain.** Le moteur refuse un geste dont la clé n'est pas celle de l'humain visé :
  une page piégée ne peut pas faire agir un humain dans le navigateur d'un autre, ni terminer sa séance.
- **Des limites plus serrées.** `goto` et `tab new` restent sur l'origine de `launch --url` (les
  redirections de l'application elle-même passent), un humain garde au plus 20 téléchargements,
  `save-state` refuse un chemin sous `uploads/`, et le plan des pannes (`faults`) est une commande
  du chef.
- **Des guillemets qui n'exécutent rien.** Les fiches demandent des textes entre apostrophes
  droites. Un code promo saisi `"$(...)"` entre guillemets doubles était exécuté par le terminal.
- **Rapports et scénarios plus sûrs.** Un rapport ne reprend plus le texte de `--app-command`,
  le départ d'un rejeu doit être une adresse HTTP(S), et un fichier de preuve ne se lit que dans
  le dossier de la séance.
- **Git et installations plus sûrs.** git ne va plus chercher ni lancer un transport déclaré par un
  `.git` reçu, `chaos schedule add` enregistre la tâche désactivée et affiche la commande à relire,
  et `install-browser` lance `python -P -m playwright` pour que le projet testé ne puisse pas
  l'usurper.

## Ce que vous pouvez faire de plus

- **Couvrir d'abord le parcours.** [docs/journey.md](../journey.md) (en anglais) décrit comment
  dessiner les étapes et les modes d'un parcours, puis jouer une matrice avec des testeurs dirigés :
  parcours droits, changement de mode après et au milieu d'une étape, fin dans un mode et validation
  dans l'autre. Un testeur humain a trouvé cinq défauts sur une application de devis à deux modes
  qu'un audit Approfondi avait manqués ; le banc d'essai contient désormais une version semée du
  principal, `mode-switch-step-skip`.
- **Attendre un assistant lent.** La fiche d'un humain peut fixer `attente_max` (secondes d'attente
  cumulées pour `wait`, 60 par défaut, 1800 au plus). `draw` garde les humains écrits à la main
  quand il remplace les humains tirés.
- **Étiqueter les constats.** Un constat peut porter un `type` (`ui`, `ux`, `technique`,
  `accessibilite`, `contenu`, `performance`), affiché à côté de la gravité dans le rapport.

## Limites

- Les clés séparent les humains au niveau du protocole du moteur. Des agents qui partagent un compte
  du système peuvent toujours lire les mêmes fichiers.
- La règle de l'origine unique vaut aussi pour l'éclaireur. Une application qui exige une seconde
  origine se teste par ses propres liens, ou dans une autre séance pour cette origine.
- Le guide du parcours est une méthode pour le chef d'orchestre, pas une garantie : il vient d'un
  seul cas, et la matrice ne vaut que ce que vaut la carte dessinée pendant la reconnaissance.
