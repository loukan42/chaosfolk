# Garder le contrôle pendant un audit

À paraître dans la prochaine version de Chaosfolk.

Cette mise à jour corrige l'arrêt et la reprise des scans, conserve tes réglages
quand une sauvegarde échoue et retire des rapports à partager certains détails
qui pouvaient contenir des valeurs saisies pendant les tests.

## Arrêter et reprendre un scan

Le bouton Arrêter reste accessible quand tu descends dans la liste des tests,
y compris pendant l'enregistrement des réglages. Une ancienne demande de
démarrage, retardée par le réseau, ne peut plus relancer le scan après ton arrêt.
Quand tu reprends l'audit, les outils de test interrompus reviennent dans la liste
du travail à faire. Tu conserves les observations déjà recueillies.

L'arrêt bloque les nouvelles actions et interrompt les outils surveillés par
Chaosfolk. Une demande déjà envoyée à l'IA peut encore consommer des tokens :
son annulation dépend de l'assistant de code qui exécute les agents.

## Retrouver tes réglages

Si une sauvegarde échoue, tes limites restent dans le formulaire, même après
rechargement de la page. Quand tu travailles dans deux onglets, modifier la durée
dans l'un ne remplace plus une limite d'actions changée dans l'autre. Si les deux
onglets modifient la même limite, la dernière sauvegarde l'emporte.

Les tests que tu décoches restent exclus quand tu changes de profondeur ou
reviens au tableau de bord.

![Réglage de la profondeur, des tests et des limites du scan.](../../assets/audit-scan.gif)

## Limiter les navigateurs ouverts

Tu peux fixer le nombre de navigateurs d'utilisateurs ouverts en même temps,
avec une limite de six par défaut. Chaosfolk ferme ceux des utilisateurs qui ont
terminé avant d'ouvrir le lot suivant. Il conserve les navigateurs nécessaires
aux vérifications à plusieurs utilisateurs jusqu'à leur libération.

Les programmes de test externes et les programmes qu'ils ont lancés se ferment
à la fin du test, y compris en cas d'échec. Tu peux fermer le tableau de bord
avec sa commande dédiée ; son serveur local se ferme aussi après quinze minutes
sans activité. Pour arrêter les tests, utilise le bouton Arrêter.

L'actualisation du tableau de bord ne fait aucun appel à l'IA. La consommation
d'IA s'affiche lorsque ton assistant fournit la mesure ; sinon elle reste
indiquée comme indisponible.

## Lire et partager les résultats

Le rapport affiche une note provisoire lorsque l'audit est incomplet et attend
un premier résultat avant de donner une note chiffrée. Les pages découvertes
par plusieurs agents en même temps restent toutes dans la liste à vérifier.

Les copies à partager conservent les résultats, les tests retirés et leur état
d'avancement. Elles retirent les observations brutes et les messages détaillés
de rejeu qui peuvent contenir des valeurs saisies. Tu retrouves ces détails dans
la session privée, dont les fichiers ont des droits d'accès restreints.
L'export d'un scénario réutilisable est refusé lorsqu'il contient un champ
sensible ou un lien d'authentification reconnu. Les anciens scénarios restent
à relire avant de les partager.

Les sondes de pages et les contrôles d'accessibilité refusent désormais les
redirections, même vers une autre adresse du même site. Donne-leur l'adresse
finale autorisée pour poursuivre le contrôle. Sinon, le résultat reste
« non concluant ».

Le mode Approfondi sélectionne tous les tests du catalogue. Le rapport distingue
ceux qui s'appliquent à ton application, ceux qui sont bloqués et le travail
encore à faire. Un scan interrompu reste donc visible comme incomplet.

Les [notes sur les niveaux de scan](product-audit-scans.fr.md) expliquent les
choix Rapide, Standard et Approfondi. Les commandes sont décrites dans le
[guide des audits](../audit-runs.md).
