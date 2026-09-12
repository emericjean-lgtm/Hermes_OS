# HERMES OS — OPERATIONAL ROADMAP

> **Source de vérité opérationnelle pour l'exécution courante du projet.**
> Lire ce fichier avant de choisir le prochain chantier.
>
> Il complète `docs/HERMES_OS_MASTER_ROADMAP.md` : le document maître décrit l'architecture, l'historique et les écarts ; ce document impose l'ordre de travail.
>
> Dernière mise à jour : 2026-09-12
> Dernier jalon vérifié : HOS-300 / G-44 (chantier #9)
> Dernier commit de code vérifié : voir `git log -1` — chantier #9 fermé
> sur la base `d1e6f1339ab60d8849707a4d9d0fb80486e61889` (HOS-299)

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

**Chantier fermé : #9 — Assistant UX / Workspace / Mission UX (HOS-300)**

**Chantiers #5 à #8, fermés depuis la dernière mise à jour de ce
document (détail complet : `docs/HERMES_OS_ROADMAP_STATE.md`) :**

- **#5 — G-11** fermé (HOS-294) : `TaskExecution.tools_used` vient des
  outils réellement invoqués (`tools_invoked`), plus jamais de la
  recommandation `assigned_tools` jamais appelée.
- **#6 — G-10** fermé (HOS-296) : **ADOPT** — `POST /memory/{id}/promote`
  existait déjà, sans appelant frontend ; panneau Quarantaine ajouté au
  Memory Center, promotion vérifiée persistée après redémarrage.
- **#7 — T-28** tranché (HOS-297) : **OPTION B** — Chat et Cowork sont
  deux contrats produit distincts sur une infrastructure partagée, pas
  deux modes d'une même exécution.
- **#8 — §15.5** livré en deux lots (HOS-298, HOS-299) : routage d'un run
  et comptabilité physique branchés dans l'Operations Center ; le
  tri-état `measured` de `VerificationReport` cesse de se recompresser
  en faux succès côté Mission Center. A-8/`DecisionExplainer` et G-3
  hors de ces Centers restent ouverts.

**#9 — Assistant UX / Workspace / Mission UX : 🟢 FERMÉ le 2026-09-12
(HOS-300).** Diagnostic des trois surfaces (Assistant/Chat, Workspace,
Mission Center) : aucune rupture aussi concrète et démontrable que G-44,
déjà nommée, n'a été trouvée ailleurs — confirmée toujours vraie par
lecture directe du code avant correction. Le harnais ACP (HOS-141) ne
traduisait que `agent_message_chunk`/`agent_thought_chunk` ; les
notifications `tool_call`/`tool_call_update` que l'agent émet à chaque
lecture/écriture réelle étaient lues puis jetées sans traduction, si
bien qu'un projet lié — le cas où l'agent touche vraiment des fichiers —
faisait disparaître tout chip d'outil de l'Assistant, alors que le
chemin direct les affiche depuis longtemps.

**Correction** : `hermes_agent_acp.py:morceau()` traduit désormais
`tool_call`/`tool_call_update` (statut terminal), corrélés par un cache
posé par session (`SessionAgent.appels_outils_en_cours` — l'agent ne
répète pas le nom/les arguments à la complétion) ; `harnais.py` porte la
charge structurée déjà déclarée sur `Morceau.tool_calls` (jamais remplie
avant) ; `routes.py` sérialise `tool_calls` sur le fil exactement comme
le chemin direct. Aucune route neuve, aucun changement frontend, aucun
contournement d'Aegis. **G-43 n'est pas concerné et reste exact** : la
frontière réelle pour les écritures de l'agent via ACP reste
`_hors_workspace`/`_touche_un_protege`, pas Aegis.

Preuves : 7 tests neufs (`test_acp_protocole.py`,
`test_chat_par_le_harnais.py`), mutation rouge→vert sur `_GENRES`, suite
complète inchangée par ailleurs (6315 passed, 3 skipped, 273 deselected).
Démontré en runtime réel : projet scratch lié à une conversation, tour
demandant de lire puis remplacer un fichier — chips `READ: NOTE.TXT` puis
`WRITE: NOTE.TXT` affichés en direct, fichier vérifié modifié sur disque
après coup (« ancien contenu » → « chantier9-ok »), artefacts scratch
supprimés ensuite. Détail : `CHANGELOG.md` HOS-300.

**#4 — G-15 invalidation des probes : 🟢 FERMÉ le 2026-09-12 (HOS-293).**
Le magasin de `agentic_probe.py` (`db/agentic_probe_results.json`) indexait
un verdict sur le seul tag du modèle. Mesuré : `ollama pull` remplaçant
les poids sous un tag inchangé, ou un Modelfile édité pour servir un autre
`num_ctx`, laissaient le verdict stocké en place — `measured_success_for`
continuait de répondre `True` pour un modèle qui n'était plus celui sondé,
jusqu'au prédicat de production (`service_registry._agentic_capable_for`)
et à la décision du routeur (`RealTaskExecutor._agentic_model`).

**Correction** : chaque entrée du magasin porte désormais l'**empreinte**
mesurée avec elle — `digest` (`/api/tags`, un hash de contenu, jamais une
horloge) et `num_ctx` (parsé du Modelfile que `/api/show` renvoie).
`measured_success_for` la revérifie à **chaque lecture** contre ce
qu'Ollama sert maintenant pour ce tag ; un écart rend `None` — non prouvé,
pas prouvé négatif (T-29) — plutôt que la valeur perimée. `save_result`
applique la même règle en écriture : une empreinte différente de celle
stockée repart d'une série à zéro, pour ne jamais mélanger des essais
mesurés sur deux modèles distincts dans le même compteur. Une empreinte
introuvable (Ollama injoignable, tag disparu de son catalogue) échoue
**ouvert** — elle ne fabrique pas un faux échec à partir d'une panne
réseau ; le seul appelant réel a de toute façon déjà réussi un `/api/show`
sur ce modèle avant de poser la question. Aucune horloge, aucun TTL :
l'invalidation suit un changement d'état réel, comme
`hermes_agent_bridge.NegociationRuntime` le fait déjà pour le pont — le
même remède, appliqué au second magasin qui en avait besoin.

Preuves : 15 tests neufs (`test_agentic_probe.py`, `test_preuve_agentique.py`),
rouges sur le code d'avant-passe puis verts après, dont un aller-retour
inter-processus (`HERMES_DATA_DIR` partagé, trois interprètes distincts)
qui mesure, invalide après un changement de poids simulé, puis remesure
sous la nouvelle empreinte sans mélanger l'ancienne série — et une chaîne
bout en bout sur le chemin réel : verdict `True` → poids changés sous le
même tag → `_agentic_capable_for` rend `None` → le repli, mesuré capable
entre-temps sous sa propre empreinte, l'emporte dans `_agentic_model`
(T-29). Suite complète : voir rapport HOS-293.

**#3 — A-4 habilitation Workspace / MCP : 🟢 FERMÉ le 2026-09-11
(HOS-292).** Valider un projet élargissait la liste blanche d'Aegis pour
**toute** action, y compris celles qui ne nommaient aucun projet. Mesuré
sur deux projets valides, lecture de `ws-b/secret.txt` : `project_id=A`
refusé, `project_id=None` **autorisé et le contenu rendu**. Sur la base
réellement servie, cette union comptait **60 racines** — dont
`Skill360 Industry` et sept dossiers sous `C:\Users\emeri`. Un
`files_read` MCP sans `project_id` les atteignait toutes.

**ADAPT** : l'habilitation devient **nominative** — la racine n'est
accordée qu'à l'action qui nomme son projet, et seulement tant qu'il est
actif et validé. La liste blanche statique, écrite par un humain dans la
configuration, est inchangée. Le prédicat « ce projet autorise-t-il, en
ce moment ? » était écrit trois fois ; il vit désormais dans
`projects.store.authorized_root` et les trois appelants y délèguent.

Deux défauts absorbés, tous deux sur le chemin d'A-4 : l'offre d'outils
du chat était gardée mais **pas l'exécution** (un `project_root=""`
résolvait sous la racine du dépôt, et le refus ne tenait qu'à une mise en
file de validation humaine) ; et un `project_id` introuvable
**court-circuitait la frontière** — le moteur n'était jamais appelé, donc
un seul accord humain ouvrait n'importe quel chemin du disque. Le `''`
que MCP transmet pour un argument omis tombait sur cette branche.

Preuves : 19/19 sur le serveur en marche, 14/14 par un **vrai client
MCP** streamable-HTTP, chaîne navigateur complète (enregistré →
`unvalidated`, 403 ; validé → 200 en nommant, 403 sans), tour de chat
réel sur un jeton écrit entre deux tours, et redémarrage en deux
processus sans élévation implicite. **14 mutations rouges puis vertes**,
dont une — la traversée non normalisée — qui a d'abord laissé toute la
suite verte et a révélé que les tests de traversée résolvaient le chemin
eux-mêmes avant de le passer.

Une régression trouvée **au navigateur** et corrigée : le panneau Projet
appelait `/git/status` sans `project_id` (403 avant, 400 après, soit la
vraie réponse de git). Aucune suite verte ne l'aurait attrapée : l'appel
était correct, seule son autorisation avait changé.

Limites dites : G-43, G-44, A-26 (§6).

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

**Prochain chantier obligatoire : #10 — §7 Advanced Agent Orchestration.**

Base de travail : HOS-300 / chantier #9.

## 3. Ordre obligatoire des chantiers

| # | Chantier | Statut opérationnel | Condition de clôture |
|---:|---|---|---|
| 1 | ~~**A-10 — Pare-feu OpenRouter**~~ | 🟢 **FERMÉ (HOS-290)** | rempli : `sk-or-v1-*` reconnu ; refus prouvé à la socket sur `chat` et `chat_events` (0 requête) ; 7 faux positifs conservés ; 5 mutations rouges puis vertes |
| 2 | ~~**A-3 — Checkpoints / restauration**~~ | 🟢 **FERMÉ (HOS-291)** | rempli : **ADOPT** ; `apercu` + `restaurer` appelables depuis le panneau Supervision ; Aegis seule autorité, accord humain nommant le point de reprise ; restauration prouvée au navigateur et après redémarrage ; 4 mutations rouges puis vertes. Limites dites : A-22, A-23, A-24 |
| 3 | ~~**A-4 — Habilitation Workspace / MCP**~~ | 🟢 **FERMÉ (HOS-292)** | rempli : **ADAPT** ; habilitation **nominative** — la racine n'est accordée qu'à l'action qui nomme son projet ; prédicat unique dans `authorized_root` ; chaîne UI→HTTP→Aegis→outil démontrée au navigateur et par un vrai client MCP ; 14 mutations rouges puis vertes. Limites dites : G-43, G-44, A-26 |
| 4 | ~~**G-15 — Invalidation des probes**~~ | 🟢 **FERMÉ (HOS-293)** | rempli : chaque verdict porte l'empreinte (digest `/api/tags` + `num_ctx` du Modelfile) mesurée avec lui ; `measured_success_for` la revérifie à chaque lecture, `save_result` repart d'une série neuve sur un écart ; None (non prouvé) remplace un verdict périmé jusqu'au prédicat et à `_agentic_model` ; 15 mutations rouges puis vertes, chaîne bout en bout et redémarrage inter-processus démontrés |
| 5 | ~~**G-11 — `assigned_tools` réellement utilisé**~~ | 🟢 **FERMÉ (HOS-294)** | rempli : `TaskExecution.tools_used` vient de `tools_invoked`, réellement observé par `_run_tool_loop` — jamais repêché depuis `assigned_tools` ; 6 tests neufs, mutation vérifiée |
| 6 | ~~**G-10 — Promotion mémoire HTTP/UI**~~ | 🟢 **FERMÉ (HOS-296)** | rempli : **ADOPT** ; `POST /memory/{id}/promote` existait déjà (HOS-250) — panneau Quarantaine ajouté au Memory Center, promotion vérifiée persistée après redémarrage |
| 7 | ~~**T-28 — Contrat Chat / Cowork**~~ | 🟢 **TRANCHÉ (HOS-297)** | rempli : **OPTION B** — Chat et Cowork sont deux contrats produit distincts sur une infrastructure partagée (registre de session ACP, base SQLite), pas deux modes d'une même exécution |
| 8 | ~~**§15.5 — Explainability + Resources + Proofs**~~ | 🟢 **LIVRÉ (HOS-298, HOS-299)** | rempli : routage d'un run et comptabilité physique branchés dans l'Operations Center (HOS-298) ; le tri-état `measured` de `VerificationReport` cesse de se recompresser en faux succès (HOS-299). A-8/`DecisionExplainer` et G-3 hors de ces Centers restent ouverts, non traités par ces lots |
| 9 | ~~**Assistant UX / Workspace / Mission UX**~~ | 🟢 **FERMÉ (HOS-300)** | rempli : G-44 — le harnais ACP traduit désormais `tool_call`/`tool_call_update` (corrélés par session), même contrat NDJSON que le chemin direct ; 7 tests neufs, mutation rouge→vert, démontré en runtime (chips READ/WRITE réels, fichier vérifié modifié sur disque). G-43 non concerné, reste exact |
| 10 | **§7 — Advanced Agent Orchestration** | 🟠 **ACTIF** | sous-agents/délégation/supervision et cycle de vie réels, avec ownership persistant et isolation claire |
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
- §3 Checkpoints / Approval / Sandbox / Security : 🟡 PARTIAL (A-2, A-3 et A-4 fermés ; restent A-5, A-17)
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
- A-4 / HOS-292 : l'habilitation de workspace est **nominative** — valider un projet n'accorde sa racine qu'aux actions qui le nomment. Un prédicat unique (`authorized_root`), trois surfaces (HTTP, MCP, chat) sous la même décision.
- §6.1 / HOS-263 : décision du routeur réellement consommée et repli borné par la preuve.
- G-14 / HOS-264 : capacité agentique mesurée sur les six modèles du catalogue.
- G-15 / HOS-293 : un verdict agentique porte l'empreinte (digest + `num_ctx`) sous laquelle il a été mesuré, revérifiée à chaque lecture — un `ollama pull` ou un `num_ctx` de Modelfile changé sous le même tag ne laisse plus un verdict périmé en place.
- §16 / HOS-265→274 : pont Hermes Agent, matrice et capacités intégrées selon preuves ; G-23 convergence ACP↔Gateway rejetée ; G-24 interruption ACP adoptée.
- §10 / HOS-274→286 : population, provenance, corrélation Run↔Skill, observateur, gouvernance et installation Aegis démontrés ; versioning/rollback restent ouverts.
- G-39 / HOS-288 : faux tableaux du Security Center corrigés ; Aegis réaffirmé comme autorité.
- G-40 / HOS-289 : 22 Centers ouverts dans le navigateur, 304 requêtes, aucun 404/5xx ; System/Evolution/Tools corrigés ; métriques documentaires recalées.
- G-11 / HOS-294 : `TaskExecution.tools_used` vient des outils réellement invoqués, jamais de la recommandation `assigned_tools`.
- G-10 / HOS-296 : promotion mémoire appelable depuis un panneau Quarantaine réel, persistée après redémarrage.
- T-28 / HOS-297 : Chat et Cowork sont deux contrats produit distincts sur une infrastructure partagée (OPTION B).
- §15.5 / HOS-298, HOS-299 : routage et comptabilité physique d'un run visibles à l'Operations Center ; le tri-état `measured` de `VerificationReport` ne se recompresse plus en faux succès.
- G-44 / HOS-300 : le harnais ACP traduit `tool_call`/`tool_call_update` en `tool_calls`/`tool_result`, corrélés par session — un chip d'outil réel s'affiche dans l'Assistant dès qu'un projet est lié, démontré en runtime. G-43 non concerné, reste exact.

## 6. Gaps connus à ne pas confondre avec le chantier actif

- G-13 : deux dimensions de score encore inertes.
- A-16 : probe d'occupation Linux `rocm-smi` non exercée.
- A-17 : test de sous-système réel encore >60 s.
- A-20 : détection d'un Modelfile étendu sous fingerprint déclaré (distinct de G-15 : celui-ci porte sur l'empreinte VRAM déclarée en §6.2, pas sur le verdict agentique).
- G-2 : isolation mémoire par projet.
- G-21 : mémoire Hermes Agent non exposée via RPC.
- G-25 : steering différé, car ACP n'offre pas d'injection dans le tour actif.
- G-41 : trou documentaire HOS-112→189, volontairement non reconstruit rétrospectivement.
- A-25 : `test_le_depot_reste_la_source_du_plugin_installe` compare des **octets** entre le plugin installé et celui du dépôt, ce qui le rend sensible à la normalisation des fins de ligne à la sortie de git. Mesuré HOS-291, en montant une copie de travail neuve : `plugin.yaml` 304 → 310 octets, `__init__.py` 4795 → 4914 (LF → CRLF), et la garde rougit sur un dépôt pourtant identique. Elle est juste sur son sujet — deux versions du même observateur —, son instrument est trop strict d'un cran.
- A-22 : `data_migration` est `path_based: false`, donc `ALLOWED_PATHS` n'est **pas** consulté pour une restauration — le seul verrou est la validation humaine obligatoire. Mesuré HOS-291. Basculer la catégorie refuserait toute restauration d'instantané (`target_path=None` → `deny`, mesuré) : décision de politique à part entière.
- A-23 : le **couple** fichiers + état demande deux accords distincts (empreintes `{checkpoint}` et `{snapshot}`), et les accords étant à usage unique une reprise complète en demande trois. Non atteignable aujourd'hui — le seul producteur prend `avec_etat=False`. Dit honnêtement à l'opérateur plutôt que masqué.
- A-24 : `prune_snapshots` et `StepCounter` sans appelant de production. Le §19.3 demande un instantané tous les N pas ; `every=10` et personne ne compte. Rien ne borne la croissance : 26 instantanés pour un `keep` de 20 sur la machine réelle.
- G-43 : un chat **lié à un projet** est servi par le harnais dès que Hermes Agent est prêt, donc ses lectures de fichiers passent par la frontière du client ACP et le hook `pre_tool_call` (HOS-141), **pas** par Aegis. Ce que HOS-292 décide sur ce chemin, c'est *quel* workspace est remis à l'agent (`authorized_root`) ; ce qu'il fait à l'intérieur relève d'une autre autorité, par construction — Hermes Agent est le cerveau et possède sa boucle d'outils. Conséquence à ne pas oublier : lier un projet est précisément ce qui bascule vers le harnais, donc la surface d'outils de chat gardée par Aegis est le **repli**, pas le cas courant.
- ~~G-44~~ : **fermé HOS-300** (chantier #9) — le harnais traduit désormais `tool_call`/`tool_call_update` en `tool_calls`/`tool_result`, même contrat que le chemin direct.
- A-26 : `ProjectStore.ensure_for_path` crée **et valide** un projet par objectif autonome lancé sur un chemin, et rien n'en retire jamais. Mesuré le 2026-09-11 sur la base réellement servie : 66 projets dont 60 actifs et validés, la plupart pointant vers des dossiers `pytest-of-Emeric` disparus. Sans conséquence d'accès depuis HOS-292 — une racine ne s'accorde qu'à qui la nomme — mais la table croît sans borne et le Workspace Center l'affiche.
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

**ACTIVE: #10 — §7 Advanced Agent Orchestration**

**NEXT: #11 — §11 Collaboration / Council**

*(G-11 fermé HOS-294 ; G-10 fermé HOS-296 ; T-28 tranché HOS-297 ; §15.5
livré HOS-298/HOS-299 ; #9 — Assistant UX / Workspace / Mission UX (G-44)
fermé le 2026-09-12, HOS-300.)*

**DO NOT JUMP AHEAD.**
