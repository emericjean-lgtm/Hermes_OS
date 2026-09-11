# Hermes OS — discipline Claude Code

## Économie de contexte

- Un chantier roadmap = une session Claude Code. Entre deux chantiers distincts : `/clear`, pas `/compact`.
- Même chantier devenu volumineux : `/compact` seulement à une pause logique, avec conservation des tests, changements, erreurs, décisions et prochaine action. Ne compacter pas par réflexe.
- Mauvaise branche de travail abandonnée : `/rewind` si cela permet de revenir à un préfixe utile ; ne pas compacter une trajectoire devenue obsolète.
- Utiliser `/usage` et `/context` quand une session devient coûteuse ou avant une décision de modèle.
- Ne pas charger de documentation, de logs ou de fichiers entiers sans besoin. Préférer recherche ciblée, symboles et petits extraits.
- Les sorties terminal volumineuses doivent être filtrées avant d'entrer dans le contexte quand le projet possède un hook adapté.

## Politique modèles

- Modèle de session par défaut : `opusplan`. Opus sert la planification complexe, Sonnet l'exécution quotidienne.
- Pour une tâche simple et bornée : préférer `sonnet`; pour une micro-tâche mécanique isolée : `haiku` peut suffire.
- Effort : `medium` pour travail routinier sensible au coût, `high` pour architecture, sécurité, debugging difficile et preuves critiques. `max` ou `ultrathink` seulement pour un besoin ponctuel démontré.
- Éviter de changer de modèle au milieu d'un chantier : le changement a son propre cache et peut provoquer une reconstruction de contexte.
- Les sous-agents ne sont pas obligatoires. Les utiliser seulement pour une séparation réelle des tâches ou du contexte ; privilégier `sonnet` pour les sous-agents de coordination et garder les équipes petites.

## Outils et MCP

- Les outils MCP sont déférés par défaut : ne pas rechercher une stratégie qui précharge inutilement des centaines d'outils.
- Préférer le CLI lorsqu'il fournit déjà la même information sans surcharge de définitions d'outils.
- Ne jamais ajouter `alwaysLoad` ou une Skill permanente sans bénéfice mesuré.

## Sortie et rapport

- Le rapport final est factuel et compact : baseline, changements, chemin réel, mutations, tests, runtime/browser, persistance, sécurité, gaps, commit, prochain chantier.
- Ne recopie pas le code ou les logs déjà présents dans le dépôt. Donne les résultats et les preuves.
- Ne sacrifie jamais une preuve, un test de sécurité ou une vérification réelle uniquement pour économiser des tokens.

Référence détaillée : `docs/HERMES_OS_CLAUDE_CODE_TOKEN_POLICY.md`.
