# HERMES OS — CHATGPT EXECUTION PROTOCOL

> Règle persistante pour tout travail Hermes OS effectué avec ChatGPT.
> Cette règle est un complément obligatoire de `docs/HERMES_OS_OPERATIONAL_ROADMAP.md`.

## Règle 1 — Lecture obligatoire avant toute tâche

Avant toute analyse, audit, recommandation, décision, ou génération de prompt concernant Hermes OS, ChatGPT doit consulter dans cet ordre :

1. `docs/HERMES_OS_OPERATIONAL_ROADMAP.md` — chantier actif, ordre obligatoire et règles d'exécution ;
2. `docs/HERMES_OS_ROADMAP_STATE.md` — historique détaillé, uniquement comme contexte et seulement s'il ne contredit pas la roadmap opérationnelle ;
3. `docs/HERMES_OS_MASTER_ROADMAP.md` — contexte architectural, preuves et écarts ;
4. le dernier état Git mesuré de `main` — pour confirmer le commit de référence et éviter de raisonner sur un état obsolète.

Une tâche ne doit jamais être lancée à partir de la seule mémoire conversationnelle lorsque ces sources persistantes sont disponibles.

## Règle 2 — La source persistante prime

En cas de conflit entre mémoire conversationnelle, ancien message, ancien rapport ou ancien état documentaire :

`mesure actuelle du dépôt > roadmap opérationnelle > roadmap maître > état historique > mémoire conversationnelle`.

Un souvenir de ChatGPT ne constitue jamais une preuve et ne peut jamais justifier un saut de chantier.

## Règle 3 — Respect strict de l'ordre

Le chantier actif indiqué par la roadmap opérationnelle est le seul chantier prioritaire.

ChatGPT ne doit pas proposer de passer au chantier suivant ou à un chantier plus séduisant avant la clôture du chantier actif, sauf décision explicite de l'opérateur.

Une dette découverte pendant la tâche :
- est absorbée immédiatement si elle est directement nécessaire au chantier actif ;
- sinon elle est enregistrée comme gap/dette et ne change pas l'ordre.

## Règle 4 — Mise à jour persistante après chaque tâche

À la fin de chaque chantier ou passe Hermes OS, ChatGPT doit mettre à jour la source persistante avant de générer ou valider le chantier suivant.

La mise à jour doit au minimum contenir :

- chantier terminé ou état réel (`PASS`, `PARTIAL`, `BLOCKED`, `REWORK`) ;
- preuve principale et limites de la preuve ;
- baseline et commit final ;
- corrections effectivement absorbées ;
- nouvelles dettes/gaps découverts ;
- chantier actif suivant ;
- numéro exact du prochain chantier dans l'ordre obligatoire.

Si la passe n'est pas validée, le pointeur ne doit pas avancer artificiellement.

## Règle 5 — Relecture de sécurité du pointeur

Avant de conclure chaque tâche, ChatGPT doit vérifier que :

- le chantier actif du document correspond à celui réellement audité ;
- aucun chantier n'a été sauté ;
- aucun statut `🟢` n'a été déduit sans preuve mesurée ;
- les gaps nouvellement découverts sont enregistrés sans réordonner arbitrairement la roadmap ;
- le prochain chantier est toujours identifiable sans interprétation humaine supplémentaire.

## Règle 6 — Mémoire interne non fiable comme unique stockage

ChatGPT peut conserver le contexte du projet dans la conversation, mais ce contexte n'est pas considéré comme un registre persistant garanti.

Le dépôt GitHub est donc le stockage durable de la trajectoire Hermes OS. La mémoire conversationnelle sert à accélérer la lecture et l'analyse, jamais à remplacer le registre documentaire versionné.

## Règle 7 — Format de travail standard

Pour chaque nouveau rapport Claude :

`LECTURE PERSISTANTE → AUDIT INDÉPENDANT → VERDICT → MISE À JOUR PERSISTANTE → PROCHAIN CHANTIER → PROMPT COMPLET`

Le prompt Claude doit être produit seulement après que le chantier actif et son contexte ont été vérifiés contre la source persistante.

## État d'installation de cette règle

- Protocole créé : 2026-09-11
- Roadmap opérationnelle : `docs/HERMES_OS_OPERATIONAL_ROADMAP.md`
- Roadmap maître : `docs/HERMES_OS_MASTER_ROADMAP.md`
- État historique : `docs/HERMES_OS_ROADMAP_STATE.md`
- Chantier actif au moment de l'installation : **#1 A-10 — Pare-feu OpenRouter**
- Prochain chantier : **#2 A-3 — Checkpoints / restauration**
- Règle : **DO NOT JUMP AHEAD**
