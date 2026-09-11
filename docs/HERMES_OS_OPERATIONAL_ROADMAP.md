# HERMES OS — OPERATIONAL ROADMAP

> **Source de vérité opérationnelle pour l'exécution courante du projet.**
> Lire ce fichier avant de choisir le prochain chantier.
>
> Il complète `docs/HERMES_OS_MASTER_ROADMAP.md` : le document maître décrit l'architecture, l'historique et les écarts ; ce document impose l'ordre de travail.
>
> Dernière mise à jour : 2026-09-11
> Dernier jalon vérifié : HOS-291 / A-3
> Dernier commit de code vérifié : voir `git log -1` — A-3 fermé sur la
> base `884f8b7214fbbcc3ff7b78e094f8ac771fd7c0eb` (HOS-290 / A-10)

## 1. Règles d'exécution

1. Un seul chantier actif à la fois.
2. On suit strictement l'ordre ci-dessous, sauf décision explicite de l'opérateur.
3. Une passe Claude doit couvrir en une seule fois : diagnostic → implémentation → corrections directement liées → tests → mutations adversariales → vérification runtime/browser → documentation minimale → commit/push → rapport.
4. Une correction découverte pendant la passe et nécessaire au chantier actif est absorbée dans la même passe. Une dette sans lien direct est enregistrée, mais ne déclenche pas un nouveau chantier.
5. Aucun statut 🟢 sans preuve mesurée sur le chemin réel.
6. Échelle obligatoire : `PRESENT → IMPORTED → CALLED → REAL PATH → BEHAVIOR CORRECT → PERSISTENT → RESTART-SAFE → ACTUALLY USED → TESTED → DEMONSTRATED`.
7. Les sondes doivent elles-mêmes être validées : une mesure surprenante doit faire suspecter la sonde avant le code.
8. Les tests verts ne suffisent pas : toute mutation importante doit d'abord faire rougir la garde/test attendu, puis redevenir verte après correction.
9. Ne jamais affaiblir une vérification pour obtenir un vert : pas de skip, xfail, désélection opportuniste, assertion supprimée ou timeout artificiellement augmenté pour masquer un défaut.
10. `data/db/hermes.db` et les données utilisateur ne doivent pas être supprimées ou altérées arbitrairement.
11. Aegis reste l'autorité de sécurité/politique réelle ; ne pas réintroduire `backend/policy` comme seconde autorité.
12. Hermes Agent reste le cerveau ; Hermes OS conserve les responsabilités de mission, Ledger, vérification, sécurité, workspace, provenance, ressources et routage.
13. Une route montée n'est pas une fonctionnalité. Il faut un appelant réel et une chaîne end-to-end vérifiée.
14. Un producteur sans consommateur et un consommateur sans producteur sont tous deux des dettes.
15. Après validation d'un chantier, le rapport doit indiquer explicitement le chantier suivant. Ne pas sauter de numéro parce qu'un sujet paraît plus amusant.

## 2. Situation courante

**Chantier actif : #3 — A-4 habilitation Workspace / MCP**

Statut : 🟠 **À EXÉCUTER**

**#2 — A-3 checkpoints / restauration : 🟢 FERMÉ le 2026-09-11 (HOS-291).**
`prendre` avait un appelant — `GraphExecutor._prendre_le_filet`, sur le
chemin de **toute** mission — et `restaurer` en avait zéro : aucune route,
aucun outil MCP, aucun script. Le dépôt prenait un filet par mission, les
affichait, et ne savait y revenir par aucun chemin.

**ADOPT**, pas reclassification : un appelant naturel existait déjà — le
panneau « Points de reprise » du Center Supervision — donc rien n'a été
inventé pour obtenir du vert. La lecture reste sur `routes/operations.py`,
en lecture seule par contrat ; la mutation vit sur `routes/checkpoints.py`,
symétrique de `routes/snapshots.py`. Aegis reste l'unique autorité :
`data_migration` étant `mandatory_validation`, le premier appel ne
restaure **jamais** et dépose un accord.

Preuve au navigateur, chaîne complète : clic → HTTP → Aegis → accord en
attente **workspace inchangé** → décision humaine → second clic →
fichiers réécrits/recréés/supprimés conformes à l'aperçu → accord `used`.
Puis un **second processus** relit l'état restauré. Trois défauts absorbés
en chemin, tous sur le chemin d'A-3 : l'accord n'identifiait pas son point
de reprise (empreintes identiques, mesuré), un état refusé était annoncé
repris (faux succès), une copie abîmée rendait une 500. Quatre mutations
rouges puis vertes.

**#1 — A-10 pare-feu OpenRouter : 🟢 FERMÉ le 2026-09-11 (HOS-290).**
Le motif `\bsk-[A-Za-z0-9]{16,}\b` excluait `-` de sa classe et ne pouvait
donc pas voir `sk-or-v1-<64 hex>` — le pare-feu était aveugle à la clé de
son propre fournisseur. Relevé avant correctif : `sk-<32 alnum>` refusé,
`sk-or-v1-…` autorisé aux **huit** placements essayés. Corrigé dans
`audit_log._SECRET_PATTERNS`, l'unique scanner — `pare_feu` y délègue
déjà, aucun second détecteur créé. Segments de fournisseur bornés et
plancher d'entropie de 16 conservé : 7 textes légitimes vérifiés non
bloquants. **Preuve à la socket** (`transport=None`, serveur HTTP local
comptant les connexions) : 0 requête sur `chat` et `chat_events` avec
secret, 1 requête et réponse reçue sans secret. Cinq mutations rouges
puis vertes. **§4 passe 🟢.**

**Prochain chantier obligatoire : #3 — A-4 habilitation Workspace / MCP.**

Base de travail : HOS-291 / A-3.

## 3. Ordre obligatoire des chantiers

| # | Chantier | Statut opérationnel | Condition de clôture |
|---:|---|---|---|
| 1 | ~~**A-10 — Pare-feu OpenRouter**~~ | 🟢 **FERMÉ (HOS-290)** | rempli : `sk-or-v1-*` reconnu ; refus prouvé à la socket sur `chat` et `chat_events` (0 requête) ; 7 faux positifs conservés ; 5 mutations rouges puis vertes |
| 2 | ~~**A-3 — Checkpoints / restauration**~~ | 🟢 **FERMÉ (HOS-291)** | rempli : **ADOPT** ; `apercu` + `restaurer` appelables depuis le panneau Supervision ; Aegis seule autorité, accord humain nommant le point de reprise ; restauration prouvée au navigateur et après redémarrage ; 4 mutations rouges puis vertes. Limites dites : A-22, A-23, A-24 |
| 3 | **A-4 — Habilitation Workspace / MCP** | 🟠 **ACTIF** | workspace actif comme frontière d'autorisation ; MCP et filesystem contraints par Project validé ; chemin UI→backend→Aegis→outil démontré |
| 4 | **G-15 — Invalidation des probes** | 🟠 | invalidation/re-évaluation automatique lorsque poids, `num_ctx`, paramètres ou état agentique changent sous un même tag ; preuves datées et consommées |
| 5 | **G-11 — `assigned_tools` réellement utilisé** | 🟠 | champ relié au vrai chemin d'exécution et démontré par allow/deny contrastés |
| 6 | **G-10 — Promotion mémoire HTTP/UI** | 🟠 | route produit réelle ; contrôle humain nommé ; provenance/quarantaine conservées ; absence d'auto-promotion par agent |
| 7 | **T-28 — Contrat Chat / Cowork** | 🟠 | contrat comportemental tranché et adopté avant travail produit correspondant |
| 8 | **§15.5 — Explainability + Resources + Proofs** | 🟠 | décisions, provenance, coûts/ressources et preuves réellement visibles dans l'Assistant sur données réelles |
| 9 | **Assistant UX / Workspace / Mission UX** | 🟠 | consolidation produit end-to-end ; Workspace, sessions, artefacts et missions cohérents avec les contrats précédents |
| 10 | **§7 — Advanced Agent Orchestration** | 🟠 | sous-agents/délégation/supervision et cycle de vie réels, avec ownership persistant et isolation claire |
| 11 | **§11 — Collaboration / Council** | 🟠 | coordination spécialisée, supervision, budget dérivé de la Mission ; Council/MoA seulement si producteur/consommateur réels |
| 12 | **§10 — Skills lifecycle** | 🟡 | versioning, rollback, création/édition/suppression, hot reload et gouvernance démontrés |
| 13 | **§8 — Learning avancé / isolation mémoire** | 🟡 | expérience→connaissance→procédure→skill, provenance, isolation par projet, confiance et rollback |
| 14 | **§16 — Bridge : surfaces restantes** | 🟡 | surfaces restantes mesurées une par une ; intégration seulement là où le runtime possède un vrai producteur |
| 15 | **§6.6 — Cognitive Scheduler** | 🟠 | ordonnancement cognitif réellement distinct du RAL et du ResourceManager, mesuré sur charges pertinentes |
| 16 | **Context engineering / long-context** | 🟠 | compression/synthèse de contexte et tool outputs sans perte critique ; tests de très long contexte réels |
| 17 | **Observabilité OTLP / tracing avancé** | 🟠 | traces corrélables de bout en bout ; coûts/latences/causes observables sans métriques inventées |
| 18 | **Installation / Update / Distribution Windows** | 🟠 | installer, détection hardware, mise à jour, rollback et conservation d'état démontrés sur la cible Windows |
| 19 | **Plugins / Extensibility générique** | 🟠 | manifestes, permissions, isolation, lifecycle ; uniquement après preuve qu'une couche générique apporte quelque chose au-delà de MCP |
| 20 | **Voice / Multimodal** | ⚪ | STT/TTS, interruption, vision/documents selon capacité matérielle et valeur produit |
| 21 | **Recherche avancée / Radar / Knowledge UX** | 🟠 | veille, ingestion, synthèse, recherche globale et exposition frontend avec producteurs réels |
| 22 | **Telegram / connecteurs utilisateur** | 🟠 | connecteur réellement borné par identité/projet/permissions, avec audit et chemin de retour local |
| 23 | **Studios spécialisés** | ⚪ | seulement après stabilisation du noyau produit ; chaque Studio doit avoir données réelles et consommateur réel |

## 4. État de référence des grandes sections

- §1 Contract & Verification : 🟢 COMPLETED
- §2 Run Ledger & Execution Lineage : 🟢 COMPLETED
- §3 Checkpoints / Approval / Sandbox / Security : 🟡 PARTIAL (A-2 et A-3 fermés ; restent A-5, A-17)
- §4 Cloud / Providers / Quota : 🟢 COMPLETED (A-1 + A-10 fermés)
- §5 Runtime / RAL / Model Intelligence : 🟢 COMPLETED
- §6 Cognitive Scheduler / Resource Intelligence : 🟡 PARTIAL
- §7 Advanced Agent Orchestration : 🟠 PLANNED
- §8 Memory Learning / Experience : 🟡 PARTIAL
- §9 Mission Control / Operator Observability : 🟡 PARTIAL
- §10 Skills / Procedural Knowledge : 🟡 PARTIAL
- §11 Collaboration / Agent Council / Delegation : 🟡 PARTIAL
- §12 Plugins / Extensibility : 🟠 PLANNED / DEFERRED
- §13 Voice / Multimodal : ⚪ OBSERVATION ONLY
- §14 Specialized Studios : ⚪ OBSERVATION ONLY
- §15 Frontend ↔ Backend Product Parity / Hermes Assistant : 🟠 PLANNED
- §16 Hermes Agent Bridge : 🟡 PARTIAL

## 5. Jalons déjà validés à ne pas rouvrir sans preuve nouvelle

- §1 / §2 / §5 : fondations démontrées.
- A-1 / HOS-255 : pare-feu cloud inévitable (défaut de **routage**).
- A-10 / HOS-290 : format de secret OpenRouter `sk-or-v1-*` reconnu (défaut de **détection**). Les deux étaient distincts et sont fermés ; §4 est 🟢.
- A-2 / HOS-256 : contrôles HOS-217/218 câblés sur le chemin réel.
- A-3 / HOS-291 : la restauration d'un point de reprise est appelable, gouvernée par Aegis et démontrée au navigateur puis après redémarrage.
- §6.1 / HOS-263 : décision du routeur réellement consommée et repli borné par la preuve.
- G-14 / HOS-264 : capacité agentique mesurée sur les six modèles du catalogue.
- §16 / HOS-265→274 : pont Hermes Agent, matrice et capacités intégrées selon preuves ; G-23 convergence ACP↔Gateway rejetée ; G-24 interruption ACP adoptée.
- §10 / HOS-274→286 : population, provenance, corrélation Run↔Skill, observateur, gouvernance et installation Aegis démontrés ; versioning/rollback restent ouverts.
- G-39 / HOS-288 : faux tableaux du Security Center corrigés ; Aegis réaffirmé comme autorité.
- G-40 / HOS-289 : 22 Centers ouverts dans le navigateur, 304 requêtes, aucun 404/5xx ; System/Evolution/Tools corrigés ; métriques documentaires recalées.

## 6. Gaps connus à ne pas confondre avec le chantier actif

- G-13 : deux dimensions de score encore inertes.
- A-16 : probe d'occupation Linux `rocm-smi` non exercée.
- A-17 : test de sous-système réel encore >60 s.
- A-20 : détection d'un Modelfile étendu sous fingerprint déclaré.
- G-15 : invalidation des probes.
- G-2 : isolation mémoire par projet.
- G-10 : promotion mémoire HTTP/UI.
- G-11 : `assigned_tools` non consommé.
- T-28 : contrat Chat/Cowork.
- G-21 : mémoire Hermes Agent non exposée via RPC.
- G-25 : steering différé, car ACP n'offre pas d'injection dans le tour actif.
- G-41 : trou documentaire HOS-112→189, volontairement non reconstruit rétrospectivement.
- A-25 : `test_le_depot_reste_la_source_du_plugin_installe` compare des **octets** entre le plugin installé et celui du dépôt, ce qui le rend sensible à la normalisation des fins de ligne à la sortie de git. Mesuré HOS-291, en montant une copie de travail neuve : `plugin.yaml` 304 → 310 octets, `__init__.py` 4795 → 4914 (LF → CRLF), et la garde rougit sur un dépôt pourtant identique. Elle est juste sur son sujet — deux versions du même observateur —, son instrument est trop strict d'un cran.
- A-22 : `data_migration` est `path_based: false`, donc `ALLOWED_PATHS` n'est **pas** consulté pour une restauration — le seul verrou est la validation humaine obligatoire. Mesuré HOS-291. Basculer la catégorie refuserait toute restauration d'instantané (`target_path=None` → `deny`, mesuré) : décision de politique à part entière.
- A-23 : le **couple** fichiers + état demande deux accords distincts (empreintes `{checkpoint}` et `{snapshot}`), et les accords étant à usage unique une reprise complète en demande trois. Non atteignable aujourd'hui — le seul producteur prend `avec_etat=False`. Dit honnêtement à l'opérateur plutôt que masqué.
- A-24 : `prune_snapshots` et `StepCounter` sans appelant de production. Le §19.3 demande un instantané tous les N pas ; `every=10` et personne ne compte. Rien ne borne la croissance : 26 instantanés pour un `keep` de 20 sur la machine réelle.
- A-21 : la règle `clé=valeur` de `redact` couvre `…_API_KEY` et `…_SECRET` mais **pas un nom en `…_KEY` seul** — mesuré HOS-290. Sans danger pour une clé dont la *forme* est reconnue (le cas OpenRouter), ouvert pour une clé d'une autre forme derrière un tel nom. Défaut de nommage, pas de format : hors périmètre A-10.
- Capability assertions sans producteur : garde fiable non encore résolue car les regex confondaient affirmation et négation.
- Secondary Center tabs : ouverture visuelle exhaustive non encore réalisée.

## 7. Discipline des prochains rapports Claude

Chaque rapport de fin de passe doit contenir, dans cet ordre :

1. verdict `🟢 PASS` / `🟠 PARTIAL` / `🔴 BLOCKED` / `REWORK` ;
2. baseline et commit final ;
3. diagnostic/root cause ;
4. fichiers et architecture touchés ;
5. chemin réel avant/après ;
6. mutations rouges puis vertes ;
7. tests complets + éventuels skips/deselections explicités ;
8. vérification runtime/browser ;
9. persistance/restart-safety ;
10. données sensibles et `hermes.db` inchangées ;
11. scope réellement absorbé et dettes nouvelles ;
12. prochain chantier **numéro exact** de ce document.

## 8. Règle de reprise pour ChatGPT

Lorsqu'un nouveau travail Hermes OS commence, utiliser d'abord :

1. `docs/HERMES_OS_OPERATIONAL_ROADMAP.md` — ordre et chantier actif ;
2. `docs/HERMES_OS_ROADMAP_STATE.md` — état historique détaillé si cohérent avec ce fichier ;
3. `docs/HERMES_OS_MASTER_ROADMAP.md` — preuve et contexte complet ;
4. le dernier commit mesuré sur `main` pour les faits runtime actuels.

**En cas de conflit, la mesure actuelle et ce document opérationnel priment sur un ancien pointeur documentaire.**

## 9. Actuel

**ACTIVE: A-4**

**NEXT: G-15**

*(A-10 fermé le 2026-09-11, HOS-290 ; A-3 fermé le 2026-09-11, HOS-291.)*

**DO NOT JUMP AHEAD.**
