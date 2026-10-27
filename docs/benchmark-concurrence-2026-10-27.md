# Benchmark concurrentiel de Chaosfolk

Recherche du 27 octobre 2026. Comparaison établie à partir des documentations et
des pages des éditeurs, ainsi que du dépôt local de Chaosfolk au commit `0cf8a44`.
Les produits concurrents n'ont pas été exécutés sur une application commune :
leurs fonctionnalités sont celles qu'ils documentent, pas des performances
mesurées indépendamment. Les priorités et estimations ci-dessous sont des avis.

## Conclusion

Chaosfolk a déjà une proposition reconnaissable : des profils d'utilisateurs,
des perturbations choisies, des replays avec preuves et un rapport local. Sa
mémoire de campagnes, sa cartographie des parcours, ses contrôles de formulaires
et ses sessions coordonnées existent déjà. Le sujet prioritaire n'est donc pas
d'ajouter encore des personnages, mais de transformer les défauts confirmés en
tests que l'équipe peut garder et exécuter sur chaque changement.

## Solutions comparées

| Solution | Catégorie et usage | Ce qu'elle documente | Ce que Chaosfolk peut en retenir |
| --- | --- | --- | --- |
| [Momentic](https://momentic.ai/) | Plateforme commerciale de QA par agents | Exploration, tests YAML versionnés, exécution locale ou hébergée, triage, maintenance, mobile et génération depuis les changements. | Partir d'une PR pour choisir les parcours à explorer ; classer les échecs et proposer des corrections de tests sous contrôle humain. |
| [Playwright Test Agents](https://playwright.dev/docs/test-agents) | Agents open source pour créer des tests web | Un agent planifie, un génère des tests Playwright et un autre répare les tests en échec. | Exporter les scénarios prouvés en tests Playwright relisibles et exécutables indépendamment. |
| [QA Wolf](https://www.qawolf.com/pricing) | Plateforme commerciale et service de QA | Exploration, cartographie, export Playwright, CI et exécution multi-utilisateur ; le service ajoute une vérification humaine. | Faciliter l'utilisation continue dans la CI et rendre l'artefact de test portable. Le service humain est un modèle différent, pas une fonction à reproduire immédiatement. |
| [mabl](https://www.mabl.com/web-application-testing) | Plateforme commerciale de tests web, mobile et API | Tests rédigés en langage naturel, navigateurs multiples, différences visuelles, intégration aux PR et analyse des échecs. | Ajouter comparaison visuelle et matrice de navigateurs ; expliquer la cause d'un échec sans masquer l'incertitude. |
| [testRigor](https://testrigor.com/features/) | Plateforme commerciale de tests en langage naturel | Tests web, mobile, API, e-mail, SMS, fichiers téléchargés et plusieurs sessions. | Étendre progressivement les parcours au-delà du navigateur, d'abord avec une boîte mail de test et des fichiers. |
| [Midscene](https://github.com/web-infra-dev/midscene) | Outil open source de contrôle d'interface par IA | Actions et assertions visuelles, intégration Playwright, web et plusieurs environnements mobiles ou desktop. | Utiliser la vision lorsque l'arbre accessible ne suffit pas ; envisager les applications natives après stabilisation du web. |
| [Browser Use](https://github.com/browser-use/browser-use) | Bibliothèque open source et infrastructure d'agents navigateur | Automatisation locale ou hébergée, choix du modèle et navigateur, actions et sorties structurées. Ce n'est pas une plateforme QA complète comparable point par point. | Réduire la friction d'installation et permettre le choix des moteurs et fournisseurs sans enfermer les utilisateurs. |
| [Applitools](https://applitools.com/solutions/developers/) | Solution commerciale de tests visuels | Comparaison d'écrans, tests de composants et intégration à des frameworks existants. | Montrer avant, après et différence dans le rapport, avec une référence validée par l'utilisateur. |

## Point de départ de Chaosfolk

Le dépôt décrit déjà sept thèmes sélectionnables, trois tailles de run, seize
profils, un catalogue de contrôles, des injections de pannes, des essais répétés
avec témoins, un rapport FR/EN et un replay multi-écrans. Il dispose aussi d'une
mémoire de campagnes avec comparaison des constats et d'une carte des routes
observées. Les sessions peuvent employer des rôles ou des données partagées.

Ces éléments restent limités par le périmètre réellement exploré : le choix d'un
thème ne garantit pas sa couverture ; l'accessibilité ne constitue pas une
certification ; les contrôles de sécurité sont limités ; les vues mobiles sont
émulées sous Chromium. Une observation n'est pas forcément un défaut reproduit.

## Fonctionnalités à ajouter

Effort estimé de manière relative pour un premier périmètre utilisable : S
(quelques jours), M (une à deux semaines), L (plusieurs semaines). Ces ordres de
grandeur ne sont pas des devis.

| Priorité | Fonction | Valeur pour l'utilisateur | Premier périmètre proposé | Effort |
| --- | --- | --- | --- | --- |
| P0 | Export en tests Playwright | Un bug trouvé devient un test conservé dans le dépôt et relancé sans modèle. | Exporter un scénario confirmé vers Playwright, avec assertion, configuration explicite et aperçu à relire. Signaler les actions non convertibles. | M |
| P0 | Exécution CI et résultat exploitable | Les régressions remontent sur chaque PR sans relancer une exploration coûteuse. | Exécuter les scénarios sauvegardés sans IA, sortie JUnit et codes de sortie documentés, exemple GitHub Actions, rapport en artefact. Distinguer échec produit et infrastructure. | M |
| P0 | Jeu d'évaluation public | Mesurer si Chaosfolk trouve de vrais défauts et limiter les faux positifs avant de promettre une meilleure couverture. | Applications synthétiques versionnées, défauts connus, scénarios témoins, répétitions et mesures de rappel, précision, coût et durée. Publier les cas non couverts. | M–L |
| P1 | Tests guidés par les changements | Concentrer le budget sur les parcours affectés par une PR. | Lire un diff, proposer une liste de parcours à partir de la carte existante, expliquer le lien et laisser l'utilisateur valider. Prévoir un mode « toute l'application ». | M–L |
| P1 | Comparaison visuelle | Détecter un écran cassé sans attendre qu'une assertion fonctionnelle échoue. | Images de référence validées, comparaison avant/après, masquage des zones dynamiques et seuils réglables. Montrer la différence, sans déclarer tout écart comme bug. | M |
| P1 | Couverture et trous de parcours | Savoir précisément ce qui a été exploré et ce qui reste à tester. | Étendre la carte existante avec attentes, rôles, états et contrôles exécutés ; distinguer prévu, tenté, réussi, échoué et non testé. Ne pas confondre routes visitées et couverture fonctionnelle. | M |
| P1 | Diagnostic et déduplication | Réduire le temps de tri quand plusieurs profils rencontrent la même cause. | Regrouper les constats candidats par route, action, message et preuve ; permettre séparation manuelle ; conserver les occurrences et les niveaux de confiance. | M |
| P1 | Confidentialité des preuves | Partager le rapport plus facilement sans exposer données ou identifiants. | Masquer les champs sensibles avant capture, nettoyer URL et journaux, proposer une revue avant export ; avertir que la détection automatique ne garantit pas l'absence de secrets. | M |
| P1 | Budget et coût réellement observés | Choisir un run selon le temps et le coût, pas seulement un nombre d'actions. | Afficher les limites disponibles par hôte, les compteurs remontés par le fournisseur et les valeurs indisponibles ; avertissement et arrêt quand une limite est effectivement contrôlable. | M |
| P2 | Firefox et WebKit | Trouver des régressions propres à un moteur navigateur. | Rejouer les tests déterministes sur Chromium, Firefox et WebKit et comparer les résultats par moteur. WebKit ne remplace pas Safari sur appareil réel. | M |
| P2 | E-mail et fichiers | Couvrir inscription, mot de passe oublié, export et import de documents. | Connecteur optionnel Mailpit pour une boîte de test ; vérification de téléchargements CSV/PDF et liens, avec données synthétiques. | M |
| P2 | Accessibilité outillée | Compléter les signaux existants par des contrôles reconnus et reproductibles. | Intégration optionnelle d'axe-core avec règle, élément et preuve ; garder un contrôle humain pour les sujets non automatisables. | M |
| P2 | MCP et connecteurs de suivi | Retrouver les constats depuis les agents et outils d'équipe. | Exposer lecture de campagne, état et repro via MCP ; export Markdown/JSON. Création de tickets uniquement sur demande explicite. | M |
| P3 | Mobile natif et charge | Couvrir applications mobiles et comportement à grande échelle. | Explorer des intégrations Appium et k6 plutôt que prétendre que l'émulation Chromium ou le petit probe couvrent ces besoins. | L |

## Ordre conseillé

1. **Fiabilité** : jeu d'évaluation, classification des résultats et confidentialité.
2. **Usage quotidien** : export Playwright, exécution CI et visualisation des régressions.
3. **Meilleure couverture au même budget** : sélection à partir d'une PR et
   suivi détaillé des parcours ; mesurer l'économie réelle plutôt que la supposer.
4. **Élargissement** : autres navigateurs, e-mail, fichiers et accessibilité
   outillée ; mobile natif et charge via intégrations spécialisées.

Le jeu d'évaluation sert aussi à comparer les modes low, medium et high sur les
mêmes applications : défauts retrouvés, fausses alertes, temps, tokens quand ils
sont fournis par l'hôte et coût quand il est connu. Aucun niveau ne doit promettre
une couverture exhaustive.

## Positionnement proposé

« Chaosfolk explore votre application avec des utilisateurs simulés, reproduit
les défauts et transforme les cas confirmés en tests que vous pouvez garder. »

La dernière partie décrit la cible après l'export Playwright, pas une capacité
annoncée comme disponible aujourd'hui. L'avantage à construire est la combinaison
d'un outil local et ouvert, de preuves vérifiables, d'un coût maîtrisable et de
tests portables. Cette hypothèse de positionnement reste à valider auprès
d'utilisateurs ; le benchmark ne démontre ni supériorité ni demande de marché.

## Références complémentaires

- [Playwright : snapshots accessibles et coût de contexte](https://github.com/microsoft/playwright.dev/blob/main/mcp/snapshots.mdx)
- [Playwright : comparaison visuelle](https://playwright.dev/docs/test-snapshots)
- [Playwright : traces et diagnostic](https://playwright.dev/docs/trace-viewer)
- [QA Wolf : génération de tests depuis une fonctionnalité ou une PR](https://www.qawolf.com/changelog/automation-ai)
- [GitHub : affichage de résultats SARIF](https://docs.github.com/en/code-security/reference/code-scanning/sarif-files/sarif-support) — utile aux constats de sécurité liés à du code, avec localisation valide ; ce n'est pas un format universel pour tous les bugs d'interface.
