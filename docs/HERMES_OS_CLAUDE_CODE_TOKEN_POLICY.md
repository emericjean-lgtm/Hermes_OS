# Hermes OS — politique d'économie Claude Code

## But

Réduire la consommation et la dérive de contexte de Claude Code sans réduire la qualité des preuves, des tests, de la sécurité ou de l'intégration réelle.

## Politique par défaut

| Situation | Modèle | Effort | Contexte |
|---|---|---|---|
| Planification complexe / architecture / sécurité | `opus` via `opusplan` | `high` | session dédiée |
| Implémentation courante | `sonnet` via `opusplan` | `medium` ou `high` selon risque | session dédiée |
| Micro-tâche mécanique isolée | `haiku` | `low`/`medium` | session courte |
| Raisonnement exceptionnel sur un tour | modèle courant | `max` ou `ultrathink` | ponctuel uniquement |

Le réglage partagé du dépôt utilise `opusplan`, avec `sonnet` puis `haiku` comme fallback et l'Artifact tool désactivé. Cette décision est volontaire : Anthropic recommande Sonnet pour la majorité du coding et Opus pour les décisions complexes ; `opusplan` utilise Opus en planification puis Sonnet en exécution. Les modèles doivent être changés le moins possible pendant une même tâche, car chaque modèle possède son propre prompt cache. 

## Gestion des sessions

1. **Nouveau chantier** : `/clear`.
2. **Même chantier, contexte gros** : `/compact` uniquement à une pause logique.
3. **Trajectoire devenue mauvaise** : `/rewind` avant de repartir sur une branche utile, lorsque la commande est appropriée.
4. **Surveillance** : `/usage` pour les tokens/cache/limites ; `/context` pour repérer les gros consommateurs.
5. **Ne pas compacter pour le plaisir** : la compaction est elle-même une reconstruction de contexte.

Lors d'un bilan Claude, ChatGPT doit toujours indiquer avant le prochain prompt :
- `/clear` : OUI/NON ;
- `/compact` : OUI/NON ;
- modèle recommandé ;
- effort recommandé ;
- raison en une phrase.

## Contexte permanent

`CLAUDE.md` doit contenir uniquement les faits et règles nécessaires à presque chaque session. Les procédures détaillées vont dans des Skills ou des règles ciblées. Les fichiers importés depuis `CLAUDE.md` ne sont pas gratuits : ils entrent quand même dans le contexte de démarrage.

Pour les règles spécifiques à un sous-système, préférer les règles path-scoped. Pour les procédures occasionnelles, préférer les Skills chargées à la demande. Pour les Skills purement manuelles, envisager `disable-model-invocation: true` afin qu'elles ne soient pas auto-sélectionnées.

## Outils et MCP

- Garder les outils MCP déférés ; ne pas précharger une grande collection.
- Éviter `alwaysLoad` sauf bénéfice démontré.
- Préférer les CLI déjà disponibles quand ils donnent la même information sans ajouter de définitions d'outils.
- Réduire les descriptions MCP au strict nécessaire : objectif, contraintes essentielles, sortie utile.
- Ne pas multiplier les serveurs MCP permanents dans tous les projets.

## Sorties d'outils

Le principal objectif d'un hook d'économie est de diminuer **l'information reçue par Claude**, pas de cacher des erreurs.

Exemple recommandé :
- tests : renvoyer seulement les échecs et un résumé des succès ;
- logs : extraire les lignes d'erreur pertinentes ;
- gros fichiers : rechercher d'abord, lire ensuite la zone utile ;
- résultats répétitifs : dédupliquer avant injection.

Un hook qui remplace une grosse sortie par une autre grosse sortie n'apporte rien. Un filtre ne doit jamais supprimer une donnée nécessaire à la preuve.

## Subagents

Les sous-agents servent à isoler un contexte, explorer en parallèle ou effectuer une tâche réellement indépendante. Ils ne doivent pas devenir un réflexe. Pour les agents auxiliaires, privilégier `sonnet` et réserver `haiku` aux tâches simples et bien bornées. Les équipes doivent rester petites et les agents arrêtés dès leur travail terminé.

## Mesure avant adoption

Aucune optimisation communautaire n'est adoptée sur sa seule promesse marketing. Hermes OS applique la règle : mesurer sur une tâche réelle, comparer qualité + durée + consommation, puis conserver l'outil uniquement si le gain est reproductible.

Les tests indépendants JetBrains de 2026 donnent un bon garde-fou : RTK a augmenté le coût de 7,6 % à faible effort et n'a pas apporté de gain net à effort élevé ; Ponytail a réduit le coût médian d'environ 10,3 % sur 80 tâches Sonnet. Ces chiffres ne sont pas une garantie pour Hermes OS, seulement un signal pour éviter les hypothèses non mesurées.

## Ne jamais optimiser contre la preuve

Interdiction d'économiser des tokens en supprimant :
- tests de sécurité ;
- tests de mutation RED/GREEN lorsque le chantier l'exige ;
- vérification runtime ;
- vérification navigateur lorsqu'elle constitue la preuve ;
- persistance/restart lorsqu'ils font partie du contrat ;
- inspection causale du caller et du consumer.

L'objectif est **moins de contexte inutile**, pas **moins de validation**.

## Sources de référence

- Anthropic — Claude Code settings : https://code.claude.com/docs/en/settings
- Anthropic — Manage costs effectively : https://code.claude.com/docs/en/costs
- Anthropic — Model configuration : https://code.claude.com/docs/en/model-config
- Anthropic — MCP : https://code.claude.com/docs/en/mcp
- Anthropic — Memory / CLAUDE.md : https://code.claude.com/docs/en/memory
- Anthropic — Status line : https://code.claude.com/docs/en/statusline
- JetBrains — RTK benchmark : https://blog.jetbrains.com/ai/2026/07/rtk-claude-code-token-savings/
- JetBrains — Ponytail benchmark : https://blog.jetbrains.com/ai/2026/07/ponytail-skill-claude-tested/
