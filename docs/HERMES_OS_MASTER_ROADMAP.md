# HERMES OS — MASTER ROADMAP

> Source de vérité documentaire de la trajectoire du projet.
> Le pointeur d'état court vit dans `docs/HERMES_OS_ROADMAP_STATE.md` et
> se lit **avant** ce document.
>
> Baseline : `528a0d37ac2fb323f338a68e325e69cdb192478e` — J24 / HOS-254.

---

## Index de navigation

| Section | Sujet | Statut | Prochaine action | Sources principales |
|---|---|---|---|---|
| §1 | Contract & Verification | 🟢 | aucune | Hermes OS |
| §2 | Run Ledger & Execution Lineage | 🟢 | aucune | Hermes OS |
| §3 | Checkpoints / Approval / Sandbox / Security | **🟡** | ~~A-2~~ fermé · **fermer A-3** | Hermes OS |
| §4 | Cloud / Providers / Quota | **🟡** | ~~A-1~~ fermé · **fermer A-10** | Hermes OS |
| §5 | Runtime / RAL / Model Intelligence | 🟢 | aucune | Hermes OS |
| §6 | Cognitive Scheduler / Resource Intelligence | 🟡 | §6.1 audité · §6.2 livré · A-15 fermé · R-3/R-4 fermés · **R-6 ouvert** | AIOS ; Hermes Agent |
| §7 | Advanced Agent Orchestration | 🟠 | audit de décision | Hermes Agent ; OpenHands ; Autonomous OS |
| §8 | Memory Learning / Experience | 🟡 | analyse d'écart | Hermes Agent |
| §9 | Mission Control / Operator Observability | 🟡 | analyse d'écart | Paperclip ; Hermes Agentic OS |
| §10 | Skills / Procedural Knowledge | 🟠 | audit de décision | Hermes Agent ; OpenHands |
| §11 | Collaboration / Agent Council / Delegation | 🟡 | audit de décision | Hermes Agent ; Paperclip |
| §12 | Plugins / Extensibility | 🟠 | reporté | Hermes Agent |
| §13 | Voice / Multimodal | ⚪ | reporté | Hermes Agent |
| §14 | Specialized Studios | ⚪ | observation | multiples |

> **§3 et §4 divergent du statut attendu par le cahier de la passe 25.**
> Celui-ci les annonçait 🟢. L'audit global J25 a mesuré, sur le code au
> baseline, deux contrôles de sécurité sans appelant et deux
> contournements du pare-feu cloud. La règle §0 ci-dessous prime sur
> l'attente : une section ne passe pas 🟢 sans preuve, et ici la preuve
> dit l'inverse. Les deux statuts remonteront quand A-1 et A-2 seront
> fermés.

---

## §0 — Comment ce document se lit, et ce qui vaut preuve

Ce projet a déjà payé cher la confusion entre « le code existe » et « la
fonctionnalité existe ». `CLAUDE.md` la nomme : *ne jamais croire un
succès sur parole*. Cette roadmap l'applique à elle-même.

### Les dix niveaux

Une capacité se qualifie sur une échelle, pas par oui/non :

```
PRESENT           le code existe
IMPORTED          quelque chose l'importe
CALLED            quelque chose l'appelle
REAL PATH         un chemin de production y passe
BEHAVIOR CORRECT  il fait ce qu'il annonce
PERSISTENT        son effet survit au processus
RESTART-SAFE      son effet survit à un redémarrage
ACTUALLY USED     le produit s'en sert
TESTED            un test le couvre
DEMONSTRATED      une mesure le prouve, mutation à l'appui
```

Les quatre défauts les plus coûteux de l'histoire du projet vivaient tous
entre `PRESENT` et `CALLED` : le pipeline de connecteurs HOS-049, la
façade `MissionControlAPI`, `Statut.PERDU` que rien ne posait, et — trouvé
en J25 — deux contrôles de sécurité livrés et jamais branchés.

**Aucun de ces niveaux ne s'infère d'un autre.** Une route montée n'est
pas une route appelée ; un champ persisté n'est pas un champ consommé ; un
test vert n'est pas une architecture saine.

### Statuts de section

| | |
|---|---|
| 🟢 **COMPLETED** | `DEMONSTRATED` sur le chemin réel, mutation vérifiée |
| 🟡 **PARTIAL** | fonctionne, mais intégration, exposition ou preuve incomplète |
| 🟠 **PLANNED** | décidé comme chantier, rien d'écrit |
| 🔴 **BLOCKED / INCOMPATIBLE** | empêché par un contrat existant |
| ⚪ **OBSERVATION ONLY** | observé, aucune intention à court terme |

### Statuts de décision

`ADOPT` · `ADAPT` · `DEFER` · `REJECT` · `OBSERVE`

**Une idée rejetée n'est jamais supprimée.** Elle reste avec son motif :
c'est ce qui empêche de la reproposer tous les six mois, et ce qui permet
de la rouvrir si le motif tombe.

---

# PARTIE A — CONSOLIDATION HISTORIQUE (J0 → J24)

> Cette partie est un **historique**. Elle ne se réécrit pas, et elle ne
> se transforme pas rétroactivement en étapes de la roadmap comparative de
> la partie B. Les deux dimensions sont distinctes : ici on a réparé ce
> qui existait ; là-bas on décide ce qui n'existe pas encore.

| Jalon | Sujet | Résultat |
|---|---|---|
| J0 | Deux arbres de tests réparés | `tests/` (53 % du dépôt) n'était exécuté par personne |
| J1 | HOS-215 — état hors du dépôt | 26,6 Mio qu'une mise à jour effaçait |
| J2 | HOS-216 — origine non humaine en quarantaine | défense contre l'injection de prompt |
| J3 | HOS-217 — dix fichiers gouvernants surveillés | livré ; **câblé en HOS-256** (A-2) |
| J4 | HOS-218 — canary, report, silence, coût | livré ; **câblé en HOS-256** (A-2) |
| J5 | HOS-221 — Contract tri-état + Run Ledger + lignée | 56 gardes |
| J6 | HOS-222 — verdict tri-état | « on ne sait pas » ≠ « c'est bon » |
| J7 | HOS-223 — commit détaché + repli vérifié | ⚠️ **la moitié restauration est injoignable** (A-3) |
| J8 | HOS-224 — empreinte canonique + portée bornée | 37 gardes |
| J9 | HOS-225 — onze causes classées sur indices nommés | 34 gardes |
| J10 | HOS-226 — `CloudCapability` dans le RAL | 29 gardes |
| J11 | HOS-227 — pare-feu de données cloud | ⚠️ **deux contournements** (A-1) |
| J12 | HOS-228 — disjoncteur, quota tri-état | 429 → fournisseur B, mesuré |
| J13 | HOS-229 — relais de contexte sérialisable | la colonne `contrat` n'était ni écrite ni relue |
| J14 | HOS-230 — six arrêts nommés | ne raisonne pas, gardé sur l'AST |
| J15 | HOS-231 — la cause voyage jusqu'au profileur | un manque de VRAM n'abaisse plus la note du modèle |
| J16 | HOS-232/233 — mise à jour, self-check, retour arrière | `preserve_set()` oubliait `checkpoints` puis `workflows` |
| J17 | HOS-234→236 — Control Rooms, vérifié en navigateur | `success_rate: 100` sur zéro tâche |
| J18–J19 | HOS-240→244 — runs perdus, routage canonique | `PERDU` existait et rien ne le posait |
| J20 | HOS-245 — persistance des missions | le journal survivait, son sujet non |
| J21 | HOS-247/248 — budget missionnel | un budget que chaque nœud remettait à zéro |
| J22 | HOS-249/250 — provenance, quarantaine, promotion | la mémoire de l'agent était un fait dès qu'il l'écrivait |
| J23 | HOS-251/252 — adoption T-13/T-16 ; T-17→T-20 | la suite complète s'exécute pour la première fois |
| J24 | HOS-253/254 — Mission ↔ Ledger ; catalogue d'événements | deux topics que le Cockpit ne pouvait pas filtrer |
| **J25** | **Audit global final indépendant** | **🟠 partiellement conforme — 9 défauts, 2 en P1** |

### Ce que cette histoire a appris, et qui vaut plus que les correctifs

1. **Les mesures sont fausses plus souvent que le code.** Sur les 25
   passes, une quinzaine de « découvertes » étaient des erreurs de sonde :
   chercher un nom au lieu d'un appel, un import de module au lieu d'un
   import local, un littéral au lieu d'une publication, une clé de
   métadonnée inventée. **Une sonde qui trouve un défaut doit d'abord être
   soupçonnée elle-même.**
2. **Le défaut dominant du dépôt n'est pas le code incorrect, c'est le
   code correct que rien n'appelle.** Il n'existe aucun mécanisme qui
   rende visible qu'un module n'a pas d'appelant.
3. **Un test qui ne visite qu'un chemin ne garde qu'un chemin** (HOS-254).
4. **Une durée absurde et deux modèles qui échouent identiquement** sont
   les deux signaux qui ont démasqué le plus de défauts.

---

# PARTIE B — ROADMAP COMPARATIVE (§1 → §14)

---

## §1 — Contract & Verification — 🟢 COMPLETED

**Contenu.** Contrat de mission, critères, vérification tri-état,
preuve, exécution *verification-first*, refus d'un succès sans preuve.

**Provenance.** Architecture Hermes OS et consolidation interne (J5, J6).
Le modèle de données et l'invariant tri-état ont été **comparés** au code
d'un système tiers lu localement (voir « Agent OS, archive locale » en fin
de document) — comparaison, pas import : aucune ligne n'en est reprise.

**Preuve au baseline.**
- `EtatCritere` porte `INVERIFIABLE` distinct de `NON_ATTEINT`, et
  l'agrégation est **conjonctive** : un seul `INVERIFIABLE` suffit à dire
  non (`runs/contrat.py:165-207`).
- La vérification de workspace est **consommée** : elle alimente
  `mission.metadata["verification"]`, `_suggest_retry`, et l'événement
  `mission.unverified` (`graph_executor.py:319-351`).
- Niveau atteint : `DEMONSTRATED`.

**Reste ouvert.** Rien de bloquant.

---

## §2 — Run Ledger & Execution Lineage — 🟢 COMPLETED

**Contenu.** Journal immuable, tentatives, parent, instantané
modèle/runtime/fournisseur, workspace/projet, causes et remèdes,
terminalité, `PERDU`, réconciliation, redémarrage.

**Provenance.** Hermes OS (J5, J9, J18–J20, J24). L'invariant d'état écrit
dans le SQL vient de la comparaison avec l'archive Agent OS ; leur table
`run_events` a été **rejetée** (voir T-registre) parce que Hermes a déjà un
bus durable.

**Preuve au baseline** — six sondes d'état impossible, six refus :

| Tentative | Résultat mesuré |
|---|---|
| terminal → terminal | reste `reussi` ; cause et raison **gelées** |
| `constater` après terminal | `modele` reste vide |
| reprise d'un run inexistant | `KeyError` |
| reprise sans motif | `ValueError` |
| run sans empreinte | `indécidable`, jamais `perdu` |
| réconciliation ×2 | idempotente |

Le gel vit dans le `CASE WHEN` SQL, sur **chaque** colonne : aucun chemin
oublié ne peut le contourner. La réconciliation décide sur la **seule**
preuve du processus porteur — prouvé par symétrie, mission présente et
absente donnant le même verdict.

C'est le composant le plus solide du dépôt. Niveau : `DEMONSTRATED`.

---

## §3 — Checkpoints / Approval / Sandbox / Security Boundary — 🟡 PARTIAL

> **Statut attendu par le cahier J25 : 🟢. Mesuré : 🟡.**

**Ce qui est démontré.**
- **Bac à sable Aegis** — huit chemins hostiles, huit refus : `../`,
  `../../`, absolu hors bac, UNC, racine du dépôt, **voisin par préfixe**
  (`autorise_bis`), variation de casse. `Path.resolve()` +
  `is_relative_to()`, et la liste blanche s'élargit dynamiquement aux
  Projects validés sans que le moteur touche une base.
- **Approbations** — empreinte canonique, discriminants, portée
  d'arborescence bornée, expiration (J8).
- **Aegis reste l'unique autorité** : `approval_engine` est délibérément
  débranché — « deux portes vivantes valent moins qu'une ».

**A-2 — fermé le 2026-09-04 (HOS-256).** Les deux invariants étaient
réels et non couverts : ni Aegis ni `_est_protege` ne traitent les dix
fichiers gouvernants, et rien n'examinait la sortie d'un agent lancé avec
tout l'environnement du parent. Ils sont branchés sur des coutures
existantes — l'instantané de mission pour HOS-217, les deux lanceurs
d'agent pour HOS-218 — sans nouvelle politique ni nouvelle autorité. Une
garde structurelle sur les lanceurs de sous-processus a d'ailleurs trouvé
le second lanceur avant qu'on déclare la protection active.

**Ce qui l'empêche encore d'être 🟢.**

| Défaut | Mesure |
|---|---|
| **A-2** `security/derive_workspace.py` (J3) et `security/surveillance_flux.py` (J4) | **0 référence** hors module pour `relever`, `a_derive`, `LigneDeBase`, `SurveillanceFlux`, `fabriquer_canary`, `environnement_avec_canary` |
| **A-3** points de reprise | `checkpoint.prendre` : 1 appelant · `checkpoint.restaurer` : **0** · aucune route (`/operations/checkpoints` est en `GET`) · aucun script |
| **A-5** workflows utilisateur | `save_workflow()` écrit dans `./data/workflows` (dépôt, suivi par git), hors `preserve_set()` et hors sauvegarde |

A-2 est le plus grave : deux contrôles **déclarés faits au ROADMAP**
créent une posture de sécurité imaginaire — plus dangereuse que leur
absence, parce qu'on compte dessus.

**Prochaine action.** Câbler les deux contrôles, ou retirer le ✅. Les
deux sont acceptables ; le silence ne l'est pas. Puis décider du sort de
la restauration des points de reprise : l'exposer, ou cesser d'en prendre.

---

## §4 — Cloud / Providers / Quota — 🟡 PARTIAL

> **Statut attendu par le cahier J25 : 🟢. Mesuré : 🟡.**

**Ce qui est démontré.**
- Le goulet `_cloud_chat` appelle `pare_feu.examiner(messages, racines=…)`
  **avant** l'envoi, lève si non envoyable, puis laisse le courtier choisir
  en écartant le fournisseur qui vient de rendre un 429.
- Traçabilité complète dans le Ledger : `runtime_demande`,
  `runtime_servi`, `modele`, `fournisseur`, et `repli` **quand les deux
  diffèrent** — les trois cas mesurés (local, cloud, repli).
- `CloudCapability` dans le RAL, `QuotaBroker` tri-état, taxonomie
  d'échecs.

**A-1 — fermé le 2026-09-04 (HOS-255).** La garde vit désormais dans
`OpenRouterClient.chat` et `chat_events`, c'est-à-dire là où est la
socket : tout appelant y passe par construction. Router les replis vers
`_cloud_chat` était impossible sans perdre le streaming de `BaseAgent`.
Une liste blanche structurelle de fichiers autorisés à parler à
OpenRouter empêche la réapparition d'un troisième chemin. Le goulet garde
courtier, quota et publication. Trois mutations vérifiées.

**Ce qui l'empêche encore d'être 🟢 — A-10.** Le pare-feu reconnaît
`sk-…` comme secret et **ignore `sk-or-v1-…`**, le format de clé
d'OpenRouter lui-même — mesuré. Défaut de **détection**, distinct du
défaut de **routage** que A-1 était. Le corriger touche aux motifs et
peut produire des faux positifs bloquants : passe dédiée.

<details><summary>A-1 — le défaut tel qu'il était (conservé)</summary>

Le commentaire de `_cloud_chat` affirme : *« c'est le seul passage par
lequel un prompt part chez un tiers »*. **Faux, mesuré :**

```
base_agent.py:279        self._cloud_client.chat_events(cloud_model, messages, …)
task_decomposer.py:489   self._cloud_client.chat_events(model, messages, …)
agent_registry.py        partage le client avec chaque agent
grep -c pare_feu  →  0   dans les trois fichiers
```

HOS-066C (repli de résilience) précède HOS-227 (pare-feu) et n'a jamais
été routé à travers lui. Le déclencheur est une **panne locale d'Ollama**,
condition de routine sur ce matériel. La fuite que HOS-227 décrit dans sa
propre docstring — le chemin absolu du workspace, donc le nom de
l'utilisateur et de son client — repart par ces deux chemins, non filtrée.

`OPENROUTER_API_KEY` n'étant pas posée sur cette machine, le chemin était
**inerte** et s'activait par configuration seule.

</details>

---

## §5 — Runtime / RAL / Model Intelligence — 🟢 COMPLETED

**Contenu.** RAL, arbitrage canonique, distinction fournisseur/runtime,
capture modèle+runtime, repli explicite, routage par rôle, Model Trust.

**Preuve.** `arbitrer()` est appelé **une seule fois**
(`task_executor.py:673`) et son résultat lu à 702.

```
mission → node → execute_task → arbitrer(propositions)
        → runtime/modèle → exécution → outcome → _clore_le_run → Ledger
```

Deux mutations postérieures, toutes deux légitimes et tracées : le repli
cloud→local (inscrit dans `decision.repli`) et `_agentic_model()`, qui est
une **porte de capacité** — elle écarte un modèle incapable de piloter la
boucle d'outils — et non un second routeur : la substitution est
journalisée et le modèle servi atterrit dans le Ledger.

**Aucune troisième autorité trouvée** (J18/J19, gardes croisées).

---

## §6 — Cognitive Scheduler / Resource Intelligence — 🟠 PLANNED

**§6.1 audité, §6.2 livré, la section reste ouverte.**

L'audit §6.1 a trouvé que §6 n'était pas absent mais **fragmenté en
quatre décisions locales qui ne se parlent pas** : le plafond de
parallélisme, le budget de mission, l'admission VRAM, le courtier de
quotas. La frontière retenue, sans autorité nouvelle :

> Le **RAL** choisit *avec quoi* travailler. **`ResourceManager`** dit *si
> la machine peut le porter*. **`Mission`** dit *combien de temps on a*.
> **`QuotaBroker`** dit *si le fournisseur veut bien*.

§6.2 (HOS-257) a fermé les trois MUST HAVE : l'admission couvre désormais
le chemin agentique, la décision compte les réservations — deux
réservations de 8 Gio ne passent plus sur une carte de 16 — et le
compteur GPU du Cockpit lit par processus au lieu de par adaptateur.

*(§6.2 chiffrait la sous-déclaration de l'adaptateur à un facteur trois.
Remesurée en A-15, elle est de 0,445 Gio — 2,9 %. Le chiffre est amendé
au CHANGELOG ; la direction de l'erreur, elle, tient.)*

A-15 (HOS-258) a canonisé la source. L'admission ne lit plus `/api/ps` :
elle lit l'occupation physique de la machine, définie une seule fois dans
`runtime/resources/vram_physique.py`, et **refuse** quand aucune sonde ne
répond alors qu'une carte existe. Mesuré, carte de 15,984 Gio portant
qwen3.6-35b avec son cache KV : `/api/ps` annonçait 12,737 Gio occupés
là où la carte en portait 15,115, et laissait admettre un modèle de
1,5 Gio sur 0,870 Gio libres.

R-3/R-4 (HOS-259) ont fermé la concurrence. Elle ne vient plus d'une
constante : `GraphExecutor` demande la borne à `ResourceManager` à chaque
étape, avec l'empreinte relevée du plus lourd des rôles configurés
(13,68 Gio, `config/models.yaml`). Mesuré : la carte de 15,98 Gio en
tient **une**, pas les deux que la constante annonçait. Et le portillon
qui fait respecter cette borne est porté par l'unique `GraphExecutor` du
conteneur, donc partagé — deux missions concurrentes donnaient
auparavant quatre nœuds simultanés pour une borne de deux.

**Restent ouverts** : R-6 (comptabilité VRAM/CPU par mission), A-16
(aucune sonde d'occupation sur Linux sans `rocm-smi` — `/sys/class/drm`
existe, rien ici ne permet de l'exercer), A-17.

Ce qui suit reste le cadrage d'origine.

### §6.1 — Capability routing
`tâche → capacités requises → runtimes/modèles/agents disponibles → route`.
Aujourd'hui l'arbitrage tranche runtime et modèle, mais aucune notion de
*capacité requise* n'est extraite de la tâche.

### §6.2 — Ordonnancement conscient des ressources
VRAM, RAM, CPU, fenêtre de contexte, coût, latence, disponibilité,
spécialisation. **Existant réutilisable** : `model_bench.gpu_dedicated_bytes`
mesure l'occupation réelle du processus d'inférence, `/api/ps` ne mesurant
que les poids — écart mesuré à 3,7 Gio sur Muse-Glimmer-30B, et à 2,4 Gio
sur qwen3.6-35b pendant A-15.

**La frontière des mesures, arrêtée en A-15 :**

| Source | Ce qu'elle mesure | Admission | Observabilité |
|---|---|:--:|:--:|
| `rocm-smi` / `nvidia-smi` | occupation physique de la carte | ✅ prioritaire | ✅ |
| `vram_physique` (compteurs Windows, par processus) | occupation physique de la machine | ✅ canonique ici | ✅ |
| `/api/ps` | **poids** des modèles résidents d'Ollama | ❌ jamais | ✅ inventaire |
| `_allocations` (réservations Hermes) | ce qui est promis, pas encore chargé | ✅ **en plus** de la télémétrie | ✅ |

Les réservations ne se mélangent pas à la télémétrie : elles s'ajoutent à
la décision, jamais à la mesure. Confondre les deux ferait disparaître
l'une des deux grandeurs.

### §6.3 — Contrôle d'admission
Vérifier les ressources **avant** d'engager. `_check_vram_admission` existe
déjà dans `task_executor` : point de départ, pas à réinventer.

### §6.4 — VRAM / résidence des modèles
Estimation mémoire, admission, chargement/déchargement, éviction,
coexistence, prévention d'OOM. Contrainte matérielle documentée :
RX 6800, ~16 Gio, et le motif d'attention change le calcul du cache KV
d'un facteur 7 (Muse Glimmer, fenêtre glissante 2048).

### §6.5 — Séquentiel vs parallèle — 🟢 fermé par R-3/R-4 (HOS-259)
Le graphe exécutait en parallèle borné par `mission_max_parallel_tasks`.
La borne vient désormais de `ResourceManager`, relue à chaque étape, et
un portillon partagé par toutes les missions l'applique globalement.

**La frontière, écrite pour qu'on ne la refranchisse pas :**

| Qui | Décide de quoi |
|---|---|
| RAL | quel modèle, quel runtime, quel fournisseur |
| **`ResourceManager`** | **la capacité physique — seule autorité** |
| `GraphExecutor` | quels nœuds sont candidats, et combien à la fois |
| `Mission` | le budget temporel |
| `QuotaBroker` | la capacité du fournisseur |
| Run Ledger | la trace |

Le graphe **demande** la borne ; il ne la calcule pas. Le portillon
n'autorise rien : franchir le portillon ne donne aucun droit sur la
carte, c'est la réservation de §6.2 qui en donne, et elle peut refuser
après. Un ordonnanceur déciderait *qui* passe et *quand* ; celui-ci
décide seulement *combien à la fois*, sur un chiffre qu'il ne possède
pas. §6.6 reste ouvert, et le restera tant que ce contrat suffit.

### §6.6 — Ordonnancement cognitif
Choix de stratégie selon difficulté, coût, confiance, criticité, ressources,
délai, spécialisation.

**Contraintes non négociables héritées.** Le budget missionnel (§HOS-248)
décide de ce qu'on **engage**, jamais de ce qu'on interrompt ; un nœud
engagé n'est pas interruptible. Tout ordonnanceur doit vivre avec cette
règle ou la faire changer **explicitement**.

**Sources externes à instruire.** AIOS en premier (scheduling, context
switch, memory/storage/tool management), puis Hermes Agent, Autonomous OS,
OpenHands. Aucune n'est adoptée avant analyse de compatibilité.

**Risque identifié d'avance.** Un ordonnanceur est par nature une
**seconde autorité** au-dessus de l'arbitrage RAL. La décision §6.1 doit
trancher qui décide de quoi avant qu'une ligne soit écrite.

---

## §7 — Advanced Agent Orchestration — 🟠 PLANNED

§7.1 agents séquentiels · §7.2 agents parallèles · §7.3 **Context Relay
(déjà présent)** · §7.4 délégation · §7.5 isolation · §7.6 supervision ·
§7.7 Council / arbitrage multi-agent · §7.8 orchestration tolérante à
l'échec.

**Existant mesuré.** Le Context Relay est réel et applique le **même**
`confiance.filtrer` que le chemin agent — une seule politique de
quarantaine, gardée par test. `MultiAgentSupervisor` existe mais opère sur
un concept de mission distinct (`MissionInstance`), non relié au `Mission`
du DAG : **deux vocabulaires « mission » coexistent** et c'est un piège
documenté (une route `/missions/{id}/cancel` par concept, une seule
montée).

**Dette d'entrée.** Le modèle de propriété des processus (J-passe 7.1) est
défini mais immature : `absence d'enregistrement ≠ propriété utilisateur`
tient, mais aucune identité de processus n'est **persistée** par Hermes OS
— elle ne vit que dans la ligne de commande de l'enfant.

**Sources.** Hermes Agent (subagents, délégation, parallélisation, appel
d'outils programmatique) ; OpenHands (séparation agent/serveur, skills &
context) ; Autonomous OS (abstraction de backend agentique).

---

## §8 — Memory Learning / Experience — 🟡 PARTIAL

**Ce qui est démontré** (J22) :

```
humain, systeme   → fiables
agent, web, dépôt, outil, document, inconnue → quarantaine
ORIGINES_DE_CONFIANCE = {humain, systeme}
```

`memory_remember` n'expose **aucun** paramètre de provenance ; aucun outil
MCP ne contient `promo`/`eleve`/`trust` ; la promotion n'existe que par
l'API locale, exige un acteur nommé, et relit la ligne pour constater le
succès au lieu de le supposer. `confidence=1.0` et les tags rassurants
n'accordent rien.

**Ce qui reste.** Expérience → connaissance → procédure → skill ;
apprentissage contrôlé ; validation ; versioning ; rollback ; provenance
de l'apprentissage.

**Le risque à nommer d'avance.** Une boucle d'auto-renforcement non
vérifiée annulerait la quarantaine par la porte de derrière : un agent
dont l'expérience devient un skill se déclare fiable en deux temps. Toute
décision §8 doit dire **qui valide** une connaissance apprise, et cette
réponse ne peut pas être « l'agent ».

**Gap ouvert.** `unified_memory` n'a **aucune isolation de projet**.

**Source.** Hermes Agent (learning loop, skills issus de l'expérience).

---

## §9 — Mission Control / Operator Observability — 🟡 PARTIAL

**Existant.** Mission Control est une **vue** stricte : `vue_operations`
est en lecture seule, gardé par deux vérifications d'arbre syntaxique
(n'écrit rien, n'ouvre aucun magasin). 10 routes d'opérations, Control
Rooms, progression, runs, lignée, contrat.

**Écarts mesurés en J25.**
- **142 des 302 routes `/api/v1` montées ne sont jamais appelées** par le
  frontend (29 `runtime`, 10 `collaboration`, 9 `security`, 7 `memory`…).
- La quarantaine et la provenance sont **exposées par l'API** (`origine`,
  `en_quarantaine`, `promu_par`, `verifie_le`) et **affichées nulle part**.
- `DecisionExplainer` est instancié par le bootstrap, ses 3 routes sont
  montées, **aucune n'est appelée** : une décision peut être expliquée,
  personne ne le demande.
- `client.ts:642-643` appelle `/runtimes/health` et `/runtimes/metrics`,
  **non montées** (le backend sert `/runtime/*`) — et ce client n'est
  lui-même jamais consommé.

**À étudier.** Traces de décision, vue de trajectoire, rejeu,
explicabilité, intervention humaine, supervision multi-agent,
visualisation ressources/budget.

**Sources.** Paperclip (objectifs organisationnels, budgets, gouvernance
visibles) ; `gdotbat/Hermes-agentic-os` — **projet distinct** du Hermes
Agent de NousResearch, toujours citer le dépôt exact.

---

## §10 — Skills / Procedural Knowledge — 🟠 PLANNED

Découverte, activation, divulgation progressive, cycle de vie, création,
validation, versioning, rollback, provenance, appariement automatique
skill ↔ tâche, annuaires externes, standardisation.

**Existant.** `backend/skills/` est chargé au démarrage (11/12 modules) et
13 routes sont montées. `assigned_skills` traverse jusqu'au contexte de
l'agent (`runtime_ctx["skills"]`) et jusqu'à la ligne de commande du
harnais. Ce qui manque n'est pas la machinerie : c'est **l'adoption** —
aucun cycle de vie, aucune provenance, aucune validation.

**Lien avec §8.** Un skill créé depuis l'expérience est une connaissance
promue. La décision de provenance de §8 vaut ici : un skill que l'agent
crée pour lui-même ne doit pas naître fiable.

**Sources.** Hermes Agent (skills chargés à la demande, divulgation
progressive, compatibilité agentskills.io) ; OpenHands en comparaison.

---

## §11 — Collaboration / Agent Council / Delegation — 🟡 PARTIAL

**Existant, et son état réel.** `CollaborationEngine`, `AgentCoordinator`,
`CapabilityMatcher`, `TaskScheduler`, `ValidationEngine`, `FeedbackLoop`,
`OptimizationEngine` existent ; 14 routes `collaboration` sont montées et
**10 ne sont jamais appelées**. `CapabilityMatcher` et le
`AgentTrustEngine` sont branchés dans `MissionExecutor` (J17), donc pas
décoratifs — mais le Council n'existe pas.

**À décider.** Délégation, agents spécialisés, collaboration
séquentielle/parallèle, council, vote/arbitrage, supervision, contexte
vérifié partagé, isolation, **budget par agent**, propriété, cycle de vie
des processus.

**Contrainte.** Un budget par agent au-dessus d'un budget par mission crée
deux autorités de budget. HOS-248 a déjà tranché que la mission est
l'autorité ; toute sous-allocation doit en **dériver**, pas la concurrencer.

**Sources.** Hermes Agent (délégation, subagents) ; Paperclip
(orchestration d'équipe, objectifs, budgets, gouvernance).

---

## §12 — Plugins / Extensibility — 🟠 PLANNED / DEFERRED

Points d'extension, MCP, outils externes, fournisseurs de capacités, cycle
de vie, bac à sable, versioning, compatibilité.

**Fait mesuré qui commande cette section.** Le pipeline générique
d'outils (HOS-049) est **décoratif** : `register_executor()` n'est jamais
appelé, les 7 connecteurs (`browser`, `database`, `docker`, `filesystem`,
`github`, `gitlab`, `rest_api`) et `mcp_client` n'ont **aucun appelant**,
et `/tools/execute` échoue toujours. La véritable surface d'extension
vivante est **MCP** (`_ALL_TOOLS`, 81 outils, dont 26 accordés par la
liste blanche hors dépôt `%LOCALAPPDATA%\hermes\config.yaml`).

**Instruction permanente.** Ne pas créer de `PluginRegistry` si les
abstractions existantes — MCP + `_ALL_TOOLS` + la liste blanche —
remplissent le rôle sans nouvelle autorité.

---

## §13 — Voice / Multimodal — ⚪ OBSERVATION ONLY

STT, TTS, vision, outils image, contexte multimodal, passerelle voix.
`backend/voice/` et `backend/studio/` existent et sont partiellement
chargés. **Non prioritaire pour le noyau.**

---

## §14 — Specialized Studios / Product Surfaces — ⚪ OBSERVATION ONLY

Coding Studio, Research Studio, Data Studio, Automation Studio.
**Ne pas commencer** tant que §6 → §11 ne sont pas consolidées : un studio
bâti sur un ordonnanceur et une collaboration non tranchés hérite de leurs
ambiguïtés.

---

# KNOWN OPEN GAPS

Chaque écart porte sa classe. **Dette actuelle et capacité future ne se
mélangent pas** : les premières se ferment, les secondes se décident.

| ID | Classe | Gap | Section | Preuve |
|---|---|---|---|---|
| ~~A-1~~ | **security** | ~~Deux chemins envoient un prompt cloud sans pare-feu~~ — **fermé HOS-255** | §4 | garde dans `OpenRouterClient`, liste blanche structurelle, 3 mutations |
| **A-10** | **security** | Le pare-feu ignore `sk-or-v1-…`, le format de clé d'OpenRouter | §4 | mesuré : `sk-…` → refusé ; `sk-or-v1-…` → autorisé, aucun constat |
| ~~A-2~~ | **security** | ~~HOS-217/218 livrés, testés, 0 appelant~~ — **fermé HOS-256** | §3 | câblés sur les coutures existantes, 6 mutations, garde structurelle des lanceurs |
| A-3 | **functional** | Points de reprise pris, jamais restaurables | §3 | `prendre` 1 appelant, `restaurer` 0, aucune route |
| A-4 | **security** | Portée projet MCP validée, non **autorisée** | §8/§10 | `_projet_resolu` vérifie l'existence seule ; le `project_id` vient du texte du modèle |
| A-5 | **technical debt** | Workflows utilisateur écrits dans le dépôt | §3 | `save_workflow()` → `./data/workflows`, hors `preserve_set()` |
| A-6 | **technical debt** | `runtimesClient` pointe vers des routes inexistantes et n'est pas consommé | §9 | `/runtimes/health` absent des 423 routes |
| A-7 | **technical debt** | 43 modules sans appelant, 13 sans test | §12 | sonde AST, imports relatifs compris |
| A-8 | **observability** | Explications produites, jamais affichées | §9 | 3 routes montées, 0 appel frontend |
| A-9 | **technical debt** | `migrer_etat.py` plante en console cp1252 | §3 | reproduit sur l'arbre remisé |
| G-1 | **architectural** | Mission → MCP : propagation du `project_id` par le texte du prompt | §7/§8 | `runtime_ctx` sérialisé dans le prompt ; aucun contexte MCP implicite |
| G-2 | **architectural** | `unified_memory` sans isolation de projet | §8 | — |
| G-3 | **UX** | Quarantaine/provenance non affichées | §9 | API expose 4 champs, frontend 0 |
| G-4 | **architectural** | `CollaborationEngine` non intégré au noyau | §11 | 10 des 14 routes jamais appelées |
| G-5 | **future capability** | Adoption pratique des skills | §10 | machinerie présente, cycle de vie absent |
| G-6 | **technical debt** | Complétude outils/capacités génériques (HOS-049) | §12 | `register_executor()` jamais appelé |
| G-7 | **architectural** | Maturation du modèle de propriété des processus | §7 | identité seulement dans la ligne de commande |
| G-8 | **technical debt** | Deux vocabulaires « mission » (`Mission` / `MissionInstance`) | §7 | deux routes homonymes, une seule montée |
| G-9 | **technical debt** | 8 runs orphelins ; aucune suppression exposée par `Registre` | §2 | dette acceptée, voir STATE |

---

# EXTERNAL REFERENCE POLICY

Une source externe est une **référence architecturale, jamais une
autorité**. Le seul chemin autorisé :

```
Observation → Analyse d'écart → Décision → Adaptation → Implémentation → Preuve
```

Interdit : `dépôt externe → copie directe`.

### Règles de citation

1. Nommer **la primitive ou le mécanisme observé**, jamais « inspiré de X ».
2. Donner le dépôt **exact**. Ne jamais attribuer une capacité à un projet
   parce que son nom ressemble à un autre — `NousResearch/Hermes-Agent`,
   `gdotbat/Hermes-agentic-os` et l'archive locale « Agent OS » sont
   **trois choses différentes**.
3. Porter le **niveau de preuve** de l'observation :
   `LU` (source consultée dans le dépôt, trace datée) ·
   `DÉCLARÉ` (rapporté par un cahier de mission, non vérifié en session) ·
   `SUPPOSÉ` (à ne pas utiliser).

### Classification obligatoire de toute idée externe

🟢 primitive compatible · 🟡 extension architecturale ·
🟠 remplacement potentiel · 🔴 incompatible · ⚪ observation seule

### Fiches sources

Le tableau ci-dessous consigne les sources **telles que le cahier de la
passe 25 les décrit**. Aucune n'a été consultée pendant cette session :
leur niveau de preuve est donc `DÉCLARÉ`, et il devra passer à `LU` — avec
la date — avant qu'une décision `ADOPT` s'appuie dessus.

| Source | Dépôt | Concepts observés (déclarés) | Sections | Preuve |
|---|---|---|---|---|
| **Hermes Agent** | `NousResearch/Hermes-Agent` | learning loop ; skills créés/améliorés depuis l'expérience ; mémoire persistante ; recherche inter-sessions ; subagents & délégation ; parallélisation ; appel d'outils programmatique ; gateway/toolsets ; MCP ; routage de fournisseurs ; replis ; pools d'identifiants ; automatisation cron ; backends de terminal ; fichiers de contexte ; checkpoints ; skills agentskills.io | §7, §8, §10, §11, §12, §13 | DÉCLARÉ |
| **AIOS** | `agiresearch/AIOS` | séparation kernel/SDK ; gestion de ressources LLM ; ordonnancement ; context switch ; gestion mémoire/stockage/outils ; dispatch de type appel système ; multi-frameworks | **§6** | DÉCLARÉ |
| **Autonomous OS** | `autonomous-ai/autonomous-os` (`docs/agentic/hermes.md`) | séparation serveur OS / backend agentique ; « AgentGateway » ; cerveau interchangeable | §7 | DÉCLARÉ |
| **OpenHands** | `OpenHands/OpenHands`, `docs.openhands.dev` | boucle raisonnement/action ; Agent Server ; réglages sérialisables ; délégation vers serveurs ACP ; Skills & Context | §7, §10 | DÉCLARÉ |
| **Paperclip** | `paperclipai/paperclip` | orchestration d'équipes ; objectifs organisationnels ; budgets ; gouvernance ; coordination ; supervision | §9, §11 | DÉCLARÉ |
| **Hermes Agentic OS** | `gdotbat/Hermes-agentic-os` | Mission Control, Goals, Journal, pont CLI | §9 | DÉCLARÉ — **projet distinct** de Hermes Agent |
| **« Agent OS », archive locale** | `agent-os-main.zip`, 2026-07-03, 11,5 Mo — **non identifié à un dépôt public** | Contract (`contract.ts`), Run Ledger (`ledger.ts`), Checkpoints, loop engine, sandbox ; SQLite `node:sqlite` | §1, §2, §3 | **LU le 2026-09-02** |

> L'archive locale est la seule source dont le code a réellement été lu.
> Elle est en TypeScript/Next.js : **aucune ligne n'en est reprenable**,
> et ce qui a été transféré est son **modèle de données et ses
> invariants**. Ne pas la confondre avec `autonomous-ai/autonomous-os` :
> rien dans le dépôt ne permet d'affirmer qu'il s'agit du même projet.

---

# DECISION REGISTER

La numérotation **continue** après les décisions existantes. Les
identifiants `T-0` à `T-21` sont utilisés ; les décisions passées ne sont
pas réécrites ici, et celles dont la trace ne vit que dans l'historique
des passes ne sont pas reconstituées.

**Prochain identifiant libre : `T-22`.**

| ID | Date | Sujet | Décision | Raison | Impact | Référence | Statut |
|---|---|---|---|---|---|---|---|
| T-13 | 2026-09-04 | Identité de projet | ADOPT | un identifiant inventé rendait une liste vide au lieu d'un refus | `project_id` = `projects.id`, inconnu refusé | HOS-249 | 🟢 appliqué |
| T-16 | 2026-09-04 | Relecture mémoire AGENT | ADOPT | le modèle écrivant depuis ce qu'il a lu est le chemin d'une injection | quarantaine jusqu'à promotion humaine | HOS-250 | 🟢 appliqué |
| T-17 | 2026-09-04 | Frontière du test EventWiring | ADAPT | 4 800 s de plafond pour une preuve acquise à 187 s | test rapide + test lent borné | HOS-252 | 🟢 appliqué |
| T-18 | 2026-09-04 | Annulation | ADAPT | `cancel_goal` posait un drapeau que personne ne lisait | branché sur `cancel_mission`, sans interrompre | HOS-252 | 🟢 appliqué |
| T-19 | 2026-09-04 | Persistance de mission | ADOPT | `started_at` ne franchissait pas la frontière du processus | écriture aux transitions déterminantes | HOS-252 | 🟢 appliqué |
| T-20 | 2026-09-04 | Isolation des tests | ADAPT | l'isolation existait, sa vérification non | garde-fou négatif au conftest | HOS-252 | 🟢 appliqué |
| T-21 | 2026-09-04 | Mission ↔ Run Ledger | ADOPT | un journal dont les lignes s'effacent avec leur sujet n'est plus un journal | pas de cascade ; l'absence de mission n'est pas une `Cause` | HOS-253 | 🟢 appliqué |
| **T-22** | — | §6.1 — autorité d'ordonnancement | **ouvert** | un ordonnanceur est par nature une seconde autorité au-dessus du RAL | à trancher **avant** toute ligne de §6 | §6 | 🟠 à décider |
| T-23 | 2026-09-04 | A-1 — replis cloud hors pare-feu | **ADAPT** | le goulet prétendait être seul et ne l'était pas ; le router était impossible sans perdre le streaming | garde dans le client, autorité inchangée | HOS-255 | 🟢 appliqué |
| **T-27** | — | A-10 — motifs de détection du pare-feu | **ouvert** | il ignore le format de clé de son propre fournisseur | élargir les motifs sans produire de faux positifs bloquants | §4 | 🟠 à décider |
| T-24 | 2026-09-04 | A-2 — contrôles de sécurité non câblés | **ADOPT** | les deux invariants étaient réels *et* non couverts par ailleurs | câblés sur les coutures existantes, aucune politique nouvelle | HOS-256 | 🟢 appliqué |
| **T-25** | — | A-3 — restauration des points de reprise | **ouvert** | on prend ce qu'on ne sait pas rendre | exposer ou cesser de prendre | §3 | 🟠 à décider |
| **T-26** | — | A-4 — habilitation de portée projet | **ouvert** | l'isolation repose sur la bonne foi du modèle | modèle d'habilitation à définir | §8 | 🟠 à décider |

### Décisions de rejet conservées

| Sujet | Décision | Raison — conservée pour ne pas la reproposer |
|---|---|---|
| Table `run_events` (archive Agent OS) | **REJECT** | Hermes a déjà un bus durable, rejouable, à identifiants idempotents ; en porter un second ferait deux magasins d'événements |
| Couche SQLite propre au Ledger | **REJECT** | `DatabaseManager` et `MigrationManager` existent ; les doubler ferait une troisième couche |
| Fusion `ModelRouter` / `AdaptiveModelRouter` | **REJECT** (T/P-4) | spécialisés sur des chemins de production distincts ; l'arbitrage tranche la précédence |
| `approval_engine` branché en parallèle d'Aegis | **REJECT** | deux portes vivantes valent moins qu'une |
| Reconstruction d'une `Mission` depuis un `Run` | **REJECT** | produirait une mission plausible et fausse — la famille de défaut la plus coûteuse du projet |
| Import de `AgentGateway` (Autonomous OS) | **OBSERVE** | référence architecturale ; rien n'indique que Hermes OS doive reproduire cette structure |

---

## Journal des mises à jour de cette roadmap

| Date | Baseline | Changement |
|---|---|---|
| 2026-09-04 | `528a0d3` | Création. §3 et §4 rétrogradées 🟡 sur les mesures de l'audit J25, contre le statut 🟢 attendu par le cahier. Registre ouvert à T-22. |
