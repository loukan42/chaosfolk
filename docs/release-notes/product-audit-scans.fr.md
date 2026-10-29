# Choisir jusqu'où Chaosfolk vérifie ton application

À paraître dans la prochaine version. [Read in English](product-audit-scans.md).

Tu peux choisir la profondeur du scan, retirer les tests inutiles et suivre
l'audit dans un tableau de bord local pendant que ton assistant de code l'exécute.

## Choisir la profondeur du scan

Le mode Rapide commence par les vérifications les plus prioritaires. Standard
ajoute davantage de cas autour des parcours de tes utilisateurs. Approfondi
sélectionne tous les tests du catalogue. Les trois modes portent sur l'ensemble
du produit, avec des tests adaptés aux fonctions découvertes dans ton application.

Par exemple, les tests d'ajout de fichiers s'appliquent lorsqu'un champ le permet.
Si une vérification exige un compte de test que tu n'as pas fourni, elle reste
visible avec le statut « bloqué ».

Tu peux décocher un test avant ou pendant le scan. Chaosfolk conserve tes choix
quand tu changes de niveau ou que tu reviens au tableau de bord. Un test retiré
ne reçoit plus de nouvelles actions ; une action déjà en cours peut se terminer.

![Choix du niveau de scan, retrait d'un test et enregistrement des limites de durée et d'actions.](../../assets/audit-scan.gif)

[Voir une image fixe](../../assets/audit-scan.png). L'enregistrement montre les
réglages avant le démarrage d'un scan.

## Fixer des limites et suivre l'avancement

Le tableau de bord affiche le temps écoulé et l'état des tests. Tu peux limiter
la durée du scan ou le nombre d'actions dans le navigateur, comme les clics et
les saisies dans un formulaire. Le bouton Arrêter bloque les nouvelles actions
et interrompt les outils de test surveillés par Chaosfolk.

La consommation d'IA s'affiche quand ton assistant de code fournit cette mesure.
Les tokens sont les morceaux de texte traités par l'IA ; leur nombre aide à
suivre cette consommation. Si l'information manque, le tableau de bord indique
« indisponible ». Une limite de tokens exige des mesures récentes et complètes
pour poursuivre les tests.

Une demande déjà envoyée à l'IA peut encore consommer des tokens après l'arrêt.
Son annulation dépend de l'outil qui exécute les agents.

## Savoir ce qui a été vérifié

Le rapport distingue les tests terminés, les observations à confirmer et le
travail inachevé. Tu retrouves aussi les tests que tu as retirés. Si un agent
termine son lot sans donner de résultat pour un test, ce test reste à faire.

Un scan Approfondi peut rester partiel si le temps manque, si une fonction est
inaccessible ou si un outil nécessaire n'est pas disponible. Pour annoncer le
scan terminé, chaque test sélectionné et applicable doit avoir un résultat
enregistré sur les parties du produit qui ont été découvertes.

L'actualisation du tableau de bord ne fait aucun appel à l'IA. Les agents
reçoivent de petits lots de tests et des bilans courts pour limiter les
informations répétées dans leurs conversations.

Les commandes et l'installation sont décrites dans le
[guide des audits complets](../audit-runs.md).
