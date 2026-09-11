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
| §3 | Checkpoints / Approval / Sandbox / Security | **🟡** | ~~A-2~~ ~~A-3~~ fermés · restent A-5, A-17 | Hermes OS |
| §4 | Cloud / Providers / Quota | **🟢** | ~~A-1~~ fermé · ~~A-10~~ fermé (HOS-290) | Hermes OS |
| §5 | Runtime / RAL / Model Intelligence | 🟢 | aucune | Hermes OS |
| §6 | Cognitive Scheduler / Resource Intelligence | 🟡 | §6.1 🟢 · §6.2 · A-15 · R-3/R-4 · R-6 · A-18 fermés · **§6.6 non ouverte** | AIOS ; Hermes Agent |
| §7 | Advanced Agent Orchestration | 🟠 | audit de décision | Hermes Agent ; OpenHands ; Autonomous OS |
| §8 | Memory Learning / Experience | 🟡 | analyse d'écart | Hermes Agent |
| §9 | Mission Control / Operator Observability | 🟡 | analyse d'écart | Paperclip ; Hermes Agentic OS |
| §10 | Skills / Procedural Knowledge | 🟠 | audit de décision | Hermes Agent ; OpenHands |
| §11 | Collaboration / Agent Council / Delegation | 🟡 | audit de décision | Hermes Agent ; Paperclip |
| §12 | Plugins / Extensibility | 🟠 | reporté | Hermes Agent |
| §13 | Voice / Multimodal | ⚪ | reporté | Hermes Agent |
| §14 | Specialized Studios | ⚪ | observation | multiples |
| §15 | Frontend ↔ Backend Product Parity / Hermes Assistant | 🟠 | **§15.1 contrat à trancher (T-28)** · §15.5 réalisable | ChatGPT ; LM Studio Bionic |

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

> **G-39 (HOS-288) — le Security Center affichait une sécurité inventée.**
> Trois tableaux écrits en dur y survivaient : quatre menaces
> (« Unauthorized file access · agent.unknown_dev · 3 occurrences »), six
> politiques (« tool.exec: allow (Safety First) ») et six profils
> d'isolation. Les routes réelles rendent `[]`, `[]` et
> `total_profiles: 0`. Pire, `useSecurityThreats()` était **déjà appelé et
> sa donnée liée puis jetée** : le réseau montrait un appel qui réussit
> pendant que l'écran montrait autre chose. Une passe antérieure avait
> retiré les mocks **nommés** (`MOCK_STATUS`, `MOCK_TRUST_SCORES`) et
> laissé les tableaux littéraux inlinés dans le JSX — on cherche `MOCK_`,
> on ne cherche pas un tableau d'objets. Corrigé, et gardé.

> **G-37 (HOS-286) — `backend/policy/` n'est pas un contrôle de sécurité.**
> L'audit J25 comptait ce module parmi l'outillage de gouvernance. Mesuré :
> `set_policy_engine` n'est jamais appelé, aucun de ses trois événements
> déclarés n'a jamais été émis, et deux de ses dix règles contredisent la
> politique appliquée. Le seul contrôle de sécurité sur le chemin réel est
> **Aegis**, et `test_autorite_de_politique.py` garde les deux moitiés :
> que le moteur de politique ne soit pas câblé, *et* qu'Aegis le reste.


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
| ~~**A-3** points de reprise~~ — **fermé HOS-291** | relevé avant : `prendre` 1 appelant · `restaurer` **0** · aucune route. Après : `GET /checkpoints/{id}/apercu` et `POST /checkpoints/{id}/restaurer`, appelés par le panneau « Points de reprise » de Supervision ; prouvé au navigateur puis dans un second processus |
| **A-5** workflows utilisateur | `save_workflow()` écrit dans `./data/workflows` (dépôt, suivi par git), hors `preserve_set()` et hors sauvegarde |

A-2 est le plus grave : deux contrôles **déclarés faits au ROADMAP**
créent une posture de sécurité imaginaire — plus dangereuse que leur
absence, parce qu'on compte dessus.

**Prochaine action.** Câbler les deux contrôles, ou retirer le ✅. Les
deux sont acceptables ; le silence ne l'est pas. Puis décider du sort de
la restauration des points de reprise : l'exposer, ou cesser d'en prendre.

**Les deux sont faits.** A-2 est fermé le 2026-09-04 (HOS-256), A-3 le
2026-09-11 (HOS-291) — **exposer**, pas cesser d'en prendre : l'appelant
naturel existait déjà. Ce qui retient encore §3 en 🟡 est A-5 (workflows
utilisateur écrits dans le dépôt) et A-17 (le test de sous-système réel
dépasse le délai de garde de 60 s), plus les trois limites mesurées en
fermant A-3 : A-22, A-23 et A-24.

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

**A-10 — fermé le 2026-09-11 (HOS-290).** Le pare-feu reconnaissait
`sk-…` et **ignorait `sk-or-v1-…`**, le format de clé d'OpenRouter
lui-même — aveugle à la clé de son propre fournisseur. Défaut de
**détection**, distinct du défaut de **routage** que A-1 était.

La cause tenait en un caractère : `\bsk-[A-Za-z0-9]{16,}\b`, dont la
classe exclut `-`. Après `sk-`, le moteur lit `or`, bute sur le tiret, et
le quantificateur échoue. Relevé au commit `25ddb52` : `sk-<32 alnum>`
→ REFUSE, `sk-or-v1-<64 hex>` → AUTORISE **aux huit placements
essayés**.

Corrigé dans `audit_log._SECRET_PATTERNS`, l'unique scanner — ni second
détecteur, ni règle dans `pare_feu`, qui délègue déjà à `redact`. Les
segments de fournisseur (`or-v1-`, `ant-`) sont bornés et le plancher
d'entropie de 16 caractères est conservé : c'est lui qui garde la prose
dehors — « le préfixe sk-or », « le format est sk-or-v1-<hex> » et
« risk-reward » restent autorisés, vérifié.

**Preuve au niveau de la socket**, pas du joint de test : avec
`transport=None` — donc le vrai transport réseau — et `base_url` pointé
sur un serveur HTTP local qui compte les connexions, un secret produit
**0 requête** sur `chat` comme sur `chat_events`, un message légitime en
produit exactement **1** et reçoit sa réponse. Cinq mutations
adversariales vérifiées.

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

**§6.1 fermée, §6.2 livré, la section reste ouverte** — §6.6 n'a jamais été ouverte.

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

R-6 (HOS-260) a fermé la comptabilité physique. Un run conserve ce que
la machine portait, en octets, et **ce qu'il ne sait pas attribuer** :
l'occupation est celle de la machine, pas du run, et `exclusif` dit si
l'écart est attribuable. L'attribution exacte est impossible ici — le
serveur Ollama sert tous les runs depuis un seul processus — et le
système le dit au lieu de le masquer.

A-18 (HOS-261) a établi que l'empreinte déclarée n'est pas une propriété
du modèle : elle dépend du **contexte servi**. `lfm2.5-2.6b-125k` coûte
2,02 Gio à 16k et 4,33 à 131072, et le harnais agentique passe par `/v1`,
qui ne transporte pas `num_ctx`. Le catalogue porte donc deux chiffres —
`vram_gb` pour le routeur, `vram_gb_max` pour l'admission. R-3 n'était pas
faussée : elle dérive du maximum, et ce rôle-là est homogène.

**Restent ouverts** : A-16 (aucune sonde d'occupation sur Linux sans
`rocm-smi` — `/sys/class/drm` existe, rien ici ne permet de l'exercer),
A-17, A-19, A-20 (rien ne détecte qu'un Modelfile a été élargi sous une
empreinte déclarée).

Ce qui suit reste le cadrage d'origine.

### §6.1 — Capability routing — 🟢 COMPLETED (HOS-262 + HOS-263)

`tâche → capacités requises → runtimes/modèles/agents disponibles →
route`. La capacité requise **est** extraite : le type de tâche porté par
le nœud de mission (HOS-070) atteint le routeur, qui le confronte à des
notes par type mesurées (HOS-144).

**Ce qui a été trouvé et fermé.** Le routeur classait juste et n'était
jamais écouté. `rank_models` filtrait sur `predict_vram_usage`, qui
multipliait l'empreinte **mesurée** par `task.complexity + 1.0` — et
`complexity` est le **nombre de mots du titre**. Les cinq modèles
compétents étaient éliminés et seul le plus petit survivait, sur les cinq
types de tâche essayés, avec le motif « Low VRAM footprint » qui
attribuait mal la cause. C'était une **troisième** autorité de capacité,
après `ResourceManager` (R-3) et l'empreinte déclarée (A-18), et c'est
elle qui gagnait. Après correction, cinq tâches sur trois modèles
différents, motif « Excellent task fit (100 %) ».

**Les autorités, délimitées.**

| chemin | autorité de sélection |
|---|---|
| Chat / agents | `core.router.ModelRouter` — rôles de `models.yaml`, tier, candidats |
| Mission / `task_executor` | `model_intelligence.AdaptiveRouter` — profils mesurés, `TaskType`, plafond VRAM |

Deux autorités sur deux chemins disjoints, décision T/P-4 (**REJECT** de
la fusion) confirmée par cette passe : chacune est seule sur son chemin.
`ResourceManager` ne choisit aucun modèle ; il fournit le plafond et
décide l'admission. Le RAL reste l'autorité du routage fournisseur.

**G-12 fermé le 2026-09-06 (HOS-263) — la décision atteint l'exécution.**

`_agentic_model` défaisait ensuite **la totalité** de ces décisions :
mesuré, 0 sur 5 survivait au chemin agentique, qui est le chemin normal
d'une mission liée à un workspace. La règle disait « substituer un repli
**connu-bon** à tout modèle non prouvé » ; sa prémisse était fausse ici.
Mesuré sur les six modèles du catalogue, **aucun n'est disqualifié** — tous
passent chat, outils, paramètres, débordement et contexte servi — et aucun
n'est sondé, le repli compris. La substitution échangeait un inconnu contre
un autre, en jetant le seul signal mesuré du système.

La règle devient : **on ne défait une décision que si le repli porte une
preuve que le modèle choisi n'a pas.** Le prédicat du bootstrap rend
désormais trois états au lieu de deux — `False` quand un contrôle
structurel écarte (preuve négative), sinon le verdict mesuré (`True`,
`False` ou `None`, « on ne sait pas »). Mesuré après correction, sur le
`_agentic_model` construit par le vrai bootstrap : **5 décisions sur 5
conservées**, trois modèles distincts pour cinq types de tâche.

Aucune autorité nouvelle : `AdaptiveRouter` reste seul à choisir sur le
chemin Mission, `ResourceManager` seul à admettre. `_agentic_model` ne rend
toujours que deux choses — ce qu'on lui a donné, ou le repli configuré — et
un test lui interdit d'en choisir une troisième. La **conservation** est
journalisée au même titre que la substitution : « on a conservé la
décision » est un fait d'exécution autant que « on l'a défaite », et
c'était celui qui manquait.

**Ce que 🟢 couvre, et ce qu'il ne couvre pas.** Il couvre le contrat de
§6.1 : le type de tâche atteint le routeur, le routeur classe sur des notes
**mesurées** par type (HOS-144), et sa décision est celle qui s'exécute.
Deux écarts subsistent et ne le rouvrent pas — ni l'un ni l'autre ne rétablit
un écrasement silencieux de la décision :
- **G-13** — `_get_records_for_task` rend `[]` en dur et
  `_compute_speed_score` rend 0,000 : deux dimensions sur cinq de
  `compute_model_score` sont inertes. La note est juste sur trois
  dimensions, pas sur cinq.
- ~~**G-14**~~ — **fermé le 2026-09-06 (HOS-264)**. Le catalogue est sondé :
  dix-huit essais réels, six modèles, **6 sur 6 prouvés capables**, verdicts
  persistés sous `db/` et relus par le prédicat après redémarrage. La sonde
  elle-même mesurait autre chose que ce qu'elle annonçait — sa consigne ne
  nommait pas le répertoire de travail alors que la production le nomme, si
  bien qu'un modèle qui écrivait le bon fichier au mauvais endroit était
  noté en échec. Sixième défaut de mesure du catalogue, sixième faux échec.
  ~~Restait **G-15**~~ — **fermé le 2026-09-12 (HOS-293)** : un verdict
  était une mesure datée que rien ne réévaluait quand les poids ou le
  `num_ctx` d'un Modelfile changeaient sous le même tag. Le magasin porte
  désormais l'empreinte (digest + `num_ctx`) mesurée avec chaque verdict,
  et `measured_success_for` la revérifie à chaque lecture avant de faire
  confiance à la mesure stockée.

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

### §6.4 — VRAM / résidence des modèles — comptabilité fermée par R-6
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

## §16 — Hermes Agent Bridge — 🟡 PARTIAL (HOS-265)

**Infrastructure transverse**, consommée par §7, §8, §10, §11, §13 et §15.
Ce n'est pas une section produit : c'est la couture par laquelle ces
sections atteindront le moteur agentique, et elle n'ajoute **aucune
autorité**. Hermes OS garde Mission, Run Ledger, lignage, vérification,
Aegis, workspace, provenance, `ResourceManager`, l'admission VRAM,
`AdaptiveRouter` et le RAL ; le pont rapporte et relaie. Une garde sur
l'arbre syntaxique le lui interdit.

> **G-40 (HOS-289) — la surface MCP, comptée.** Le Tools Center oppose les
> outils **déclarés**, qui ne s'exécutent pas (`POST /tools/execute` répond
> « No executor registered »), aux **outils MCP**, que Hermes Agent appelle
> vraiment. Ce contraste portait « 71 outils » ; `_ALL_TOOLS` en compte
> **81** — 12 fichiers, 10 studio, 9 git, 7 mémoire, 7 workflows, 6
> projets, 6 compétences, 5 tâches, le reste sur instantanés, approbations,
> vérification et évolution. Le détail par famille était resté exact ; seul
> le total avait dérivé quand les dix outils Studio sont arrivés. Une garde
> tient désormais le chiffre au serveur : il ne peut plus bouger seul.

**Runtime.** Hermes Agent v0.20.0 → **v0.21.0** (`693641aa8b`). Le tag
`v0.21.0` n'existe pas — l'amont étiquette en CalVer ; c'est `origin/main`
qui déclare cette version. 31 918 commits, avance rapide propre, état
persistant identique avant/après (63 sessions, 559 fichiers de skills,
4 mémoires, 5 crons). Suite Hermes OS inchangée : 5877 passed.

**Transport.** `tui_gateway`, JSON-RPC sur stdio. L'adaptateur existant
lance l'agent en un coup par tâche et meurt ; le gateway vit, émet
`gateway.ready` et accepte des ordres pendant qu'il travaille.

**Négociation, et non déclaration.** `-32601` prouve une absence ; toute
autre réponse — résultat ou erreur applicative — prouve une présence.

**Mais la négociation ne vaut que ce que valent les noms sondés** (G-19,
HOS-268). Relevé du registre réel : **206 méthodes** sur v0.21.0, là où le
pont en sondait 62, et les trois surfaces déclarées absentes l'étaient sur
des noms **inventés**. Reconstruite depuis le registre — versé au dépôt,
daté et empreint dans `config/gateway_registre.json` — la matrice compte
**19 surfaces, 19 complètes**. Elle mesurait notre vocabulaire.

Deux surfaces sont `SANS_RPC` : la capacité existe dans l'agent, aucune
méthode ne l'expose. `memory` est un **outil interne** (`tools/memory_tool.py`,
présent dans les toolsets actifs) ; **rien ne lance un subagent** —
`spawn_tree.*` lit l'arbre, `subagent.steer`/`interrupt` pilotent un enfant
existant. Un subagent naît de l'agent, ce qui est cohérent avec la règle qui
prime sur tout.

### La matrice, honnêtement

| surface | gateway | pont | backend | frontend | statut |
|---|---|---|---|---|---|
| capabilities | ✅ | ✅ | ✅ 2 routes | ✅ Runtime Center | 🟢 **DEMONSTRATED** |
| sessions (lecture) | ✅ | ✅ | ✅ `/bridge/agent` | ✅ Cerveau · Sessions | 🟢 **DEMONSTRATED** |
| tools/toolsets (lecture) | ✅ | ✅ | ✅ | ✅ Cerveau · Outils | 🟢 **DEMONSTRATED** |
| profiles/Bots (lecture) | ✅ | ✅ | ✅ | ✅ Cerveau · Bots | 🟢 **DEMONSTRATED** |
| delegation (lecture) | ⚠️ partielle | ✅ | ✅ | ✅ Cerveau · Délégation | 🟡 lecture seule |
| cron/routines (lecture) | ✅ | ✅ | ✅ | ✅ Cerveau · Routines | 🟢 **DEMONSTRATED** |
| **fork/branch (mutation)** | ✅ `session.branch` | ✅ contrat G-18 | ✅ POST `/bridge/agent/.../brancher` | ✅ Cerveau · Sessions | 🟢 **DEMONSTRATED** |
| **lecture d'une session** | ✅ `session.history` | ✅ | ✅ GET `.../historique` | ✅ Cerveau · Sessions | 🟢 **DEMONSTRATED** |
| **renommage (mutation)** | ✅ `session.title` | ✅ contrat G-18 | ✅ POST `.../titre` | ✅ Cerveau · Sessions | 🟢 **DEMONSTRATED** |
| **toolsets (mutation)** | ✅ `tools.configure` | ✅ contrat G-18 | ✅ POST `/bridge/agent/toolsets/{nom}` | ✅ Cerveau · Outils | 🟢 **DEMONSTRATED** — écrit `config.yaml`, porte sur les missions |
| **permissions d'édition (ACP)** | ✅ `session/request_permission` | ✅ adaptateur ACP | ✅ GET `/bridge/agent/permissions` | ✅ Cerveau · Permissions | 🟢 **DEMONSTRATED** — 4 décisions dont 3 refus sur un tour réel |
| approvals (gateway) | ✅ 3 méthodes | ✅ négociée | ✗ **écartée** | — | 🔴 file en mémoire du **gateway** ; le chat passe par **ACP** — deux transports, deux files |
| **interruption (ACP)** | ✅ `session/cancel` | ✅ adaptateur ACP | ✅ POST `/conversation/{id}/cancel` | ✅ bouton stop de l'Assistant | 🟢 **DEMONSTRATED** — 217 s → 17 s sur un tour réel |
| steering | ⚠️ cancel + re-prompt | — | ✗ | ✗ | 🟠 **DEFER** — rien n'injecte dans un tour actif |
| delegation — pause | ✅ `delegation.pause` | ✗ **écartée** | — | — | 🔴 process-local : bride le gateway du pont, pas les missions |
| delegation — lancer | ✗ pas de RPC | — | — | — | 🔴 `delegate_tool.py`, l'agent décide |
| groups / Bot-à-Bot | ✅ 18 méthodes | ✅ négociée | ✗ | ✗ | 🟠 PLANNED — `endpoint: not_configured`, 0 salon |
| chat/streaming · steering · approvals · skills · learning · MCP · browser · projects · config · insights | ✅ | ✅ négociée | ✗ | ✗ | 🟠 PLANNED |
| activation d'un toolset · création de Bot | ✅ | ✅ contrat posé | ✗ | ✗ | 🟠 PLANNED — le contrat les couvre, aucune UI ne les demande |
| suppression / réinitialisation | ✅ | ✗ hors contrat | — | — | 🔴 destructif : reprise non tranchée |
| memory | ✗ absente | ✅ négociée | — | — | 🔴 pas de méthode amont |

### G-18 — le contrat d'autorité, établi par la mesure

    la conversation stockee          Hermes Agent      state.db, durable
    la session vivante               le gateway        ephemere
    le recit de ce qu'on a demande   Hermes OS         son bus d'evenements

**Hermes OS demande, il n'écrit pas.** `state.db` fait 114 Mio avec son
schéma, son WAL et ses transactions ; deux programmes qui l'écrivent, c'est
la base de l'utilisateur qui arbitre. Deux gardes structurelles le tiennent :
aucun module n'ouvre `state.db`, et `hermes_home` ne sert qu'à poser un `cwd`.

Mesuré : `session.resume` **ne mute rien** (empreinte identique, handle mort
au redémarrage) — c'est une activation, pas une mutation. `session.branch`
mute vraiment, et **additivement**. `MUTATIONS_CONNUES` ne porte aucune
mutation destructive, et un test l'interdit.

Une surface **négociée et visible** n'est pas une surface **intégrée**, et
la règle anti-orphelin existe pour que cette distinction ne puisse plus se
perdre. HOS-266 a fait passer cinq surfaces de la seconde catégorie à la
première, en **lecture** : le pont sait désormais demander, pas seulement
négocier. Tout ce qui *écrit* dans l'état de l'agent reste PLANNED, faute
d'avoir tranché qui en est autorité — un bouton qui l'ignorerait serait un
bouton sans backend.

### Les Skills (HOS-274)

Septième surface, et la première dont la moitié mutation est **refusée sur
mesure** plutôt que reportée faute d'avoir regardé. Détail en §10.

Deux choses que le pont en retient. `MUTATIONS_CONNUES` ne porte aucune
méthode `skills.*`, et un test l'interdit — parce que la seule qui réponde,
`install`, rend `true` sans avoir rien vérifié. Et le pont **n'a pas** servi
la population installée, bien qu'il le puisse : Hermes OS la lisait déjà
sur le disque, et une seconde lecture par RPC aurait fabriqué la vérité
concurrente que cette passe est allée fermer. Une surface négociable qu'on
choisit de ne pas offrir est aussi un résultat.

### Ce que le pont ne porte pas (HOS-288)

La vérification transversale confirme que la chaîne agentique ne traverse
aucun reste de l'ancienne couche : zéro import, zéro requête, et les
quatre autorités — Aegis, journal §18, Run Ledger, bus d'événements —
répondent. `/operations` le dit lui-même, source par source :
`approbations` ← `backend.security.approvals`, `runs` ←
`backend.runs.registre`.

### Le module retiré, et ce que son retrait a coûté (HOS-287)

Rien. C'est le résultat, et il n'était pas acquis : un module monté au
bootstrap, déclarant trois événements et servant six routes, peut très
bien avoir un consommateur qu'aucune lecture ne montre. Le retrait le
prouve mieux que l'audit — 338 routes au lieu de 344, et les six sont
exactement celles qu'on visait.

### Une seule autorité, et elle est nommée (HOS-286)

Le pont ne touche pas à `backend/policy/`, et c'est le résultat : rien
dans la chaîne agentique ne le traverse. L'audit le confirme par la
mesure — aucun module hors `backend/policy/` ne l'importe, sauf le
bootstrap qui le construit et monte ses routes.

La politique que l'agent subit vient d'un seul fichier,
`config/security.yaml`, relu par `AegisEngine` à chaque évaluation. Le
cockpit la montre désormais telle quelle, avec l'effet de chaque
catégorie **au niveau courant** — calculé par le backend depuis la même
comparaison que le moteur, jamais recalculé à l'écran.

### La pose, demandée et gardée (HOS-285)

Le pont porte enfin une mutation de Skill — `skills.manage` — et c'est la
quatrième de `MUTATIONS_CONNUES`. G-26 l'avait refusée pour une raison
exacte (« install n'écrit pas de façon vérifiable ») que G-35 a corrigée
par la mesure : c'est le *compte rendu* qui ne vaut rien, l'écriture se
vérifie à l'octet.

Elle ajoute aussi un troisième magasin au contrat de G-23 — `skills/`, à
côté de `state.db` et `config.yaml`. Un magasin, pas une sémantique : il
est stocké, il survit au redémarrage, et il ne vise aucun tour vivant. La
ligne de partage entre l'état stocké et le tour vivant ne bouge pas.

### Le dossier de l'agent, enfin lu (HOS-283)

Quatrième lecture du disque de l'agent — après les compétences (HOS-274),
leur provenance (HOS-275) et les mutations observées (HOS-281) — et la
posture n'a pas bougé d'un pouce : lire, jamais écrire, jamais recopier.

Ce que cette quatrième ajoute est la **confrontation**. Les trois
précédentes rendaient ce que l'agent dit ; celle-ci compare ce qu'il a
enregistré à ce que son disque porte, et les trois écarts possibles ont
chacun leur nom. C'est la première fois que Hermes OS contredit l'agent
sur son propre terrain — et il le peut parce qu'il recalcule, sans rien
lui demander.

### Le quatrième transport, consommé (HOS-282)

Un transport dont rien ne lit la sortie n'est pas un transport, c'est une
dette. `_meta.hermes.turnId` fait désormais l'aller-retour complet jusqu'à
un écran : Hermes OS pose l'étiquette dans la requête ACP, l'agent la
restitue dans son événement de cycle de vie, l'observateur la note, et le
Skills Center l'affiche à côté du Run qui l'a frappée.

Le pont n'y est pour rien, et c'est le résultat : la chaîne n'emprunte
**aucune** des 206 méthodes du gateway. G-19 avait relevé le registre pour
que personne n'invente de nom ; G-34 confirme par l'usage que la relation
n'en avait besoin d'aucun.

### L'observateur, en service (HOS-281)

Le quatrième transport n'est plus théorique : du code de Hermes OS tourne
dans le processus de l'agent, en observateur pur, et rend compte. Cinq
passes auront été nécessaires pour y arriver honnêtement — et chacune a
refusé de livrer la moitié suivante avant d'avoir mesuré la précédente.

### La corrélation, bouclée (HOS-280)

Quatre passes pour une seule question : « quelle Skill vient de quel Run ? »
G-29 a mesuré que la relation n'existait pas et refusé de l'inventer ; G-30
a trouvé que le protocole portait déjà le canal ; G-31 l'a fait restituer par
l'agent ; G-32 y a branché un Run réel. Le résultat tient en une phrase :
**la corrélation n'a jamais eu besoin d'une surface nouvelle — elle avait
besoin qu'on ne jette pas celle qui existait**, et que chacun garde ses
identités.

### La corrélation : un quatrième transport, patché (HOS-279)

Le contrat turnId ne passe ni par le pont, ni par le Gateway, ni par le
plugin : il passe par le **protocole ACP lui-même**, dans un champ que la
spécification réserve aux extensions. Trois lignes chez l'agent, et
l'identité du client traverse jusqu'à l'événement Skill. Le pont n'y est
pour rien — et c'est le résultat : la corrélation n'avait pas besoin d'une
surface nouvelle, elle avait besoin qu'on ne jette pas celle qui existait.

### La corrélation, et ce que le pont n'y peut rien (HOS-277, corrigé par HOS-278)

Le pont sait demander à l'agent ce qu'il porte. Il ne sait pas lui dire pour
quel Run il travaille. HOS-277 en concluait que « aucune méthode du runtime
ne le permettrait » : **c'était trop fort**, et G-30 l'a mesuré. Le champ
`_meta` de `session/prompt` est réservé par ACP aux extensions, il arrive
jusqu'au handler de l'agent, et l'agent l'ignore. Le protocole accepte donc
la métadonnée ; c'est la **restitution** qui manque.

Ce qui reste vrai : le mode jetable lance l'agent sans aucun identifiant, et
le Gateway n'offre aucun canal ouvert. La limite n'est ni dans le pont ni
dans le protocole — elle est dans trois lignes que l'agent n'écrit pas
encore. Détail, spécification et décision en §10.

### L'observateur (HOS-276)

Une quatrième, et elle ne passe pas par le pont du tout. `on_skill_lifecycle`
est un hook **plugin** de l'agent : le chemin qui porte l'identité complète
d'une mutation de Skill n'est ni le Gateway, ni ACP, mais un troisième
transport — du code de Hermes OS s'exécutant *dans* le processus de l'agent.
Légitime, mesuré, et volontairement pas emprunté aujourd'hui (§10).

### La provenance (HOS-275)

Et une troisième, mesurée en G-27 : `commands.catalog` **expose** bien une
provenance — `{usage, origin}` par compétence — mais son `origin` ne consulte
jamais `created_by`. Il rend `hub` / `bundled` / `local`, si bien qu'une
compétence générée par l'agent y est indistinguable d'une compétence écrite
à la main. Mesure : les 5 `local` de cette installation *sont* les 5
`created_by: "agent"` — par coïncidence, puisque aucune compétence n'a été
écrite à la main. En conclure une équivalence serait exactement l'inférence
que G-27 interdit. La provenance se lit donc sur le disque, où le marqueur
est écrit.

### La règle anti-orphelin

`test_pas_de_backend_orphelin.py` : toute route `/api/v1` doit avoir un
appelant dans `frontend/src`, ou figurer dans une dette gelée. **Mesure :
120 routes sur 306 — 39 % — n'ont aucun appelant frontend.** Le chiffre a
été faux deux fois avant d'être juste, et une **mutation** a trouvé le
second défaut là où la relecture avait échoué.

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

> **G-40 (HOS-289) — les vingt-deux Centers ont été ouverts.** Aucun
> n'avait jamais été regardé dans un navigateur. Tous rendent, aucun en
> état d'erreur ; **304 requêtes API observées, aucun 404, aucun 5xx**, et
> aucune vers `/approval`, `/audit` ou `/policy/*`. Deux écrans
> présentaient des données inventées comme mesurées : le System Center
> (douze composants avec latences, dont `policy.engine` supprimé en G-38 ;
> puis « 25 composants », « 42 arêtes de dépendance suivies », « aucune
> dépendance cyclique détectée » — `health()` ne rend ni arête, ni ordre,
> ni cycle) et l'Evolution Center (quatre motifs à « 12x, 85 %, +22 % »,
> quand `/evolution/patterns` rend 404). Le Tools Center annonçait
> « 71 outils » MCP là où `_ALL_TOOLS` en compte **81** — un chiffre juste
> le jour où il fut écrit. **Limite de couverture** : chaque Center a été
> ouvert sur sa vue par défaut, et la classe « affirmation de capacité sans
> producteur » n'a pas de garde — aucune regex ne sépare une affirmation
> d'une négation sans se tromper, ce que la tentative a prouvé.

> **G-39 (HOS-288) — vérifié sur le chemin réel.** L'onglet Audit du
> Governance Center affiche « 6 entrée(s) — /api/v1/logs (journal §18) »
> avec ses entrées réelles : agent, demande, modèle choisi par le routeur,
> résultat, durée. Rendu observé dans le navigateur, pas seulement en test.

> **G-37 (HOS-286) — le journal d'audit du §18 a enfin un lecteur.**
> `backend/core/audit_log.py` écrit dans SQLite *et* dans des fichiers
> sous `data/logs/`, avec rédaction des secrets **à l'écriture** — « un
> secret qui a atteint le disque a déjà fui ; le filtrer à l'affichage
> serait du théâtre ». Il portait six entrées réelles depuis le
> 2026-08-14 et personne ne les lisait : le Governance Center affichait
> l'anneau en mémoire de `backend/policy/`, vide par construction.
> L'onglet Audit sert désormais `/logs`, avec le modèle choisi par le
> routeur et sa raison en infobulle.


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

## §10 — Skills / Procedural Knowledge — 🟡 PARTIAL (HOS-274 → HOS-286)

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

### Ce que G-26 a mesuré, et ce qui en découle (HOS-274)

Le cycle a été mesuré bout en bout sur le runtime v0.21.0 installé, pas
supposé.

#### La découverte principale : Hermes OS avait déjà tort

`backend/skills/registre.py` lit les compétences de l'agent depuis
HOS-153, et le Skills Center les affiche. Il lisait
`hermes/hermes-agent/skills` — les compétences livrées avec le **dépôt**
de l'agent — au lieu du dossier **actif** `hermes/skills` que le runtime
résout, et il ignorait le champ `platforms:` que chaque `SKILL.md`
déclare :

    registre.py (avant)   60 noms
    skills.manage list    65 noms
    en commun             40

L'écran montrait donc `imessage`, `findmy` et `apple-notes` à un agent
**Windows** qui ne les chargera jamais, et taisait vingt-cinq compétences
qu'il porte vraiment. Corrigé — le foyer suit `HERMES_HOME` comme le fait
`hermes_constants.get_hermes_home()`, et la lecture honore `platforms:` —
les deux concordent **exactement** : 65 contre 65, aucun écart dans un
sens ni dans l'autre.

Lire `platforms:` n'est pas réimplémenter la résolution du runtime : c'est
lire un champ que le fichier déclare. Le reste de cette résolution
(`skill_matches_environment`, la liste des désactivées, les dossiers
externes) reste au runtime, et c'est pourquoi la RPC demeure l'autorité.

#### `skills.manage` : cinq actions, sept absentes

    list search install browse inspect                répondent
    create edit delete pending diff approve reject    4017

`4017` n'est pas `-32601`, et la nuance décide : la méthode existe, elle a
été construite **sans** ces gestes. Côté agent la machinerie complète
existe pourtant — `skill_manager_tool.py` crée, édite, patche et supprime
— mais comme **outil que l'agent s'appelle à lui-même**, jamais comme
méthode que Hermes OS peut demander. Même forme que les approvals (G-23).

#### Le faux succès d'`install`

`_skills_install` appelle `do_install` et **jette sa valeur de retour**.
`do_install` rend `None` sur six chemins — sources absentes, identifiant
irrésoluble, bundle non récupéré, nom non résolu, déjà installée sans
`--force`, et **installation bloquée par le scanner de sécurité**. Le
gateway répond `{"installed": true}` dans tous les cas.

Mesure : `skill-qui-nexiste-absolument-pas-hos274` rend `installed: true`,
sans quarantaine ni ligne d'audit — rien n'a été récupéré, rien examiné,
rien posé. Le même runtime, interrogé par `inspect`, rend honnêtement `{}` :
il *sait* que ce nom n'existe pas ; c'est le chemin d'installation qui ne
le dit pas. **REJECT**, et la garde porte sur la route, pas sur le nom
d'un bouton.

#### La persistance est réelle, la fraîcheur ne l'est pas

Mesure sur un `HERMES_HOME` de substitution, sans écrire un octet dans le
vrai :

    processus qui écrit la skill   scan True  / liste False
    nouveau processus              scan True  / liste True

`skills.manage list` passe par `banner.get_available_skills()`, mémoïsé
**pour la vie du processus** sans TTL ni signature — alors que
`_find_all_skills`, qu'il enveloppe, se re-déclenche dès que les dossiers
changent. Et `skills.reload` ne rattrape pas : il annonce
`added=['hos274-reload']` pendant que `list` continue de l'ignorer dans le
même processus. Deux RPC de la même surface se contredisent.

C'est une raison de plus de garder le **disque** comme source de la
population installée : il n'a pas ce cache.

#### Le pending existe, et il est hors de portée

Contrairement aux approvals du Gateway (G-23, process-locales en mémoire),
`write_approval` est **adossé à des fichiers** :
`<hermes_home>/pending/skills/*.json`, avec `stage_write`, `list_pending`,
`get_pending`, `discard_pending` et `skill_pending_diff`. De l'état
inter-processus, donc — exactement ce qui manquait à G-23.

Mais aucune RPC ne l'expose ; `%LOCALAPPDATA%\hermes\pending` **n'existe
pas**, ce qui dit que rien n'a jamais été mis en attente ; la porte est
fermée par défaut (`skills.write_approval` absent de `config.yaml`) ; et
`config.get` refuse cette clé — `4002 unknown config key`. L'approbation
elle-même, `apply_skill_pending`, s'appelle en **intra-processus** depuis
le `/skills approve` de la CLI.

L'activer depuis Hermes OS mettrait chaque écriture de Skill de l'agent
dans une file que rien, côté cockpit, ne pourrait vider. **DEFER**, et la
raison est nommée : le producteur existe, l'approbateur est injoignable.

### Verdicts

    population installée     ADOPT    le disque, corrigé — 65, avec les
                                      descriptions, sans gateway
    catalogue du hub         ADOPT    browse + search, pagination du runtime
    détail d'une entrée      ADAPT    du hub seulement ; `connu` porte le
                                      « ce nom n'y est pas » sans le
                                      confondre avec une panne
    installation             REJECT   `installed: true` sans vérification,
                                      y compris après un blocage sécurité
    création / édition /
    suppression              DEFER    outil que l'agent s'appelle, pas
                                      méthode que Hermes OS peut demander
    pending / diff /
    approve / reject         DEFER    file réelle sur disque, sans RPC et
                                      sans approbateur atteignable
    rafraîchissement à chaud DEFER    `reload` ne rafraîchit pas `list`

**Livré.** La correction de `registre.py` ; `backend/services/vue_skills.py`
(le **catalogue seul**, lecture gardée sur l'arbre syntaxique) ; trois
routes `GET` ; et un troisième onglet au Skills Center. Aucune façade de
mutation, et **aucune seconde liste des compétences installées** : offrir
la population locale par RPC aurait rouvert la vérité concurrente que
cette passe vient de fermer.

**Et « lecture seule » y décrit l'autorité, pas l'absence d'effet.**
`browse`, `search` et `inspect` font rafraîchir à l'agent son propre cache
d'index de hub (`skills/.hub/index-cache/*.json` — 705 Ko réécrits pendant
la mesure). C'est l'agent qui écrit, par son propre chemin ; Hermes OS ne
touche pas son disque. La nuance est notée parce que confondre les deux est
exactement ce que ce dépôt paie cher.

### G-27 — le contrat de provenance, mesuré (HOS-275)

G-26 avait conclu que la provenance n'existait pas sur la surface de
lecture. C'était vrai de la **RPC**, et faux du **disque** : l'agent tient
trois fichiers qui la portent réellement.

    .bundled_manifest   69 entrées `nom:hash` — et 69/69 encore intactes
    .hub/lock.json      VIDE : aucune compétence n'est passée par le hub
    .usage.json         75 enregistrements, dont 5 `created_by: "agent"`

`created_by` est **écrit par `skill_manage`**, jamais déduit. La chaîne
complète a été démontrée sur un `HERMES_HOME` de substitution : création au
premier plan → `created_by: null` ; création sous `BACKGROUND_REVIEW` →
`created_by: "agent"` ; **un nouveau processus relit les deux**. Persistance
et redémarrage acquis, sans écrire un octet dans le foyer réel.

Sur l'installation : **60 système intactes, 4 générées par l'agent, 1 en
conflit**.

#### Le piège que G-27 ferme

`skill_usage.is_agent_created()` ne lit **jamais** `created_by` : il rend
« ni bundled ni hub ». Mesure — une compétence créée au premier plan, donc
`created_by: null`, en ressort `True`, pendant que
`list_agent_created_skill_names()`, qui lit l'enregistrement, l'exclut à
juste titre. Deux fonctions voisines, deux méthodes opposées. Un garde
interdit son usage côté Hermes OS.

#### Le conflit de clef

Le magasin est indexé par nom de frontmatter dans 74 cas sur 75. Une
compétence dont le dossier et le `name:` diffèrent porte donc **deux
enregistrements** : `documentation-verification` (`created_by: "agent"`) et
`Documentation & Identity Verification` (`created_by: null`) désignent le
même dossier. On ne tranche pas — `conflit` est une catégorie rendue telle
quelle, avec ses deux valeurs.

#### La corrélation : REJECT, et la mesure qui le dit

`skill_manage` transmet bien `task_id` et `session_id` à `record_created` /
`bump_patch`. Mais `_apply` n'écrit que `created_by` : les deux identifiants
partent dans le hook `on_skill_lifecycle`, consommé ici par le relais de
métriques partagées, qui « émet un fait sans son identité locale » et
n'agrège que des compteurs à dimensions bucketisées. Mesure : **0 des 75
enregistrements** les porte, et `telemetry/shared_metrics` ne contient aucun
nom de compétence.

Sans clef de jointure, le Run Ledger ne peut porter aucune relation. La
table `skills` de `hermes.db` a bien une colonne `source_task_id` — elle est
**vide**, et la remplir avec les compétences de l'agent en ferait la seconde
vérité que HOS-274 est allé fermer.

Le chemin existe et il est nommé : `on_skill_lifecycle` est un hook
**plugin** documenté, et un plugin Hermes OS le recevrait avec son identité
complète. Cela demanderait d'installer du code dans l'agent — une décision
d'architecture qui n'appartient pas à une passe de diagnostic.

#### Verdicts

    origine d'une compétence installée   ADOPT    trois fichiers, lus
    système/upstream + intégrité         ADOPT    empreinte recalculée
    générée par l'agent                  ADOPT    `created_by: "agent"`
    posée par le hub                     ADOPT    lock.json (vide ici)
    modification directe hors workflow   ADOPT    détectée par l'empreinte,
                                                  pour les compétences du
                                                  manifeste seulement
    persistance + redémarrage            ADOPT    démontrés
    « utilisateur »                      REJECT   `null` couvre deux cas
    « apprise », « approuvée »           REJECT   aucun champ ne les porte
    corrélation session / Run / Mission  REJECT   0/75, émise puis agrégée
    ledger Hermes OS porteur de relation DEFER    pas de clef de jointure

**Livré.** `backend/skills/provenance.py` (lecture seule, sept catégories
bornées, chacune avec sa preuve), la provenance jointe à `GET /skills/agent`,
et une colonne au Skills Center dont l'infobulle nomme le fichier. Rien
n'est écrit, rien n'est copié dans `hermes.db`.

### G-28 — le plugin observateur : légitime, et pas installé (HOS-276)

G-27 laissait une porte nommée : `on_skill_lifecycle` est un hook **plugin**
documenté, et un plugin Hermes OS le recevrait avec son identité complète.
G-28 l'a ouverte pour voir, sur un `HERMES_HOME` de substitution.

    le point d'observation et son propriétaire      ADOPT
    l'installation dans l'agent réel, aujourd'hui   DEFER

#### La chaîne, démontrée

Avec le fichier versionné dans ce dépôt
(`integrations/hermes-agent/observateur-skills/`), trois mutations réelles :

    created  g28-depot-a  task='tache-1'  session='sess-depot'  prov='local'
    created  g28-depot-b  task='tache-2'  session='sess-depot'  prov='local'
    patched  g28-depot-a  task='tache-4'  session='sess-depot'  prov='local'

`task_id` **diffère d'une mutation à l'autre** : c'est exactement la clef de
jointure qui manquait à G-27, et qu'aucun magasin natif ne persiste. Deux
appels à `bump_use` intercalés n'ont rien laissé — `loaded` est écarté.
Un **nouveau processus** relit l'état intégralement.

#### Pourquoi ADOPT sur la légitimité

L'observateur ne peut pas devenir une autorité **par construction du hook** :
`_emit_skill_lifecycle` ignore la valeur de retour, et chaque callback est
isolée. Mesuré :

    plugin absent      non chargé   has_hook=False   mutation OK, enregistrement natif écrit
    plugin désactivé   chargé       has_hook=False   mutation OK, enregistrement natif écrit
    callback qui lève  chargé       has_hook=True    mutation OK, enregistrement natif écrit

#### Pourquoi DEFER sur l'installation

**Aucun consommateur.** Rien dans Hermes OS ne lit encore une relation
Run ↔ Skill : installer produirait un fichier qui grossit et que personne ne
lit — le producteur sans lecteur que ce dépôt passe son temps à défaire.

**Les internes de l'agent changent dans quatre jours.**
`plugin_compat.COMPAT_REMOVAL_DATE = 2026-09-14` : ce jour-là, tout plugin
externe important un module interne est *désactivé*. Celui-ci n'en importe
aucun — `scan_plugin()` rend « aucun », et un test le garde — donc il
survit. Mais le runtime d'après n'a pas été mesuré.

Préalables, dans cet ordre : une surface produit qui lit la relation, puis
le runtime post-2026-09-14 mesuré.

#### Le contrat, mesuré sur v0.21.0

    action                    created | edited | patched | installed | loaded
    skill_name                le nom local, NON anonymisé
    provenance                installed | agent_created | external | local | unknown
    task_id / session_id      str, parfois ""
    telemetry_schema_version  "hermes.observer.v1"

`loaded` part à chaque invocation de Skill ; les quatre autres sont des
mutations. `PluginState` plafonne à 10 Mio, donc l'observateur ne retient
que les mutations et borne sa liste : un observateur qui remplit son quota
cesse d'observer sans le dire.

`agent/skill_commands.py` appelle `bump_use` **sans** `session_id` : un fait
peut arriver sans session, et le compléter fabriquerait la corrélation que
G-27 a refusé d'inventer.

#### Ce que ce contrat ne permettra toujours pas

Rattacher une Skill à une **Mission** ou à un **Run**. Le `task_id` livré
est celui de la tâche de l'agent, pas d'un Run du Ledger. Les relier
demanderait une correspondance qui n'existe nulle part — c'est le sujet
suivant, pas celui-ci.

### G-29 — la corrélation Run ↔ Skill : où elle se perd (HOS-277)

G-28 avait posé un préalable à l'installation de l'observateur : *un
lecteur réel de la relation*. G-29 est allé voir si cette relation peut
seulement exister. Elle ne le peut pas aujourd'hui, et l'endroit exact où
elle se perd est mesuré.

    PRESENT       oui   l'agent émet task_id + session_id (G-28)
    PROPAGATED    NON   c'est ici que ça casse
    CALLED        n/a
    PERSISTENT    NON
    RESTART-SAFE  NON

    la relation Run ↔ Skill                            DEFER
    la déduire du temps, du compteur ou de l'unicité   REJECT

#### Rien n'est propagé vers l'agent

Le mode jetable lance l'agent avec `--query --model --provider --base_url
--max_turns [--toolsets] --quiet --usage-file`. **Aucun identifiant de
tâche.** Le `task_id` que Hermes OS tient ne sert qu'à son propre bus
d'événements. Et `session/prompt` ne transporte que `{sessionId, prompt}` :
y ajouter un champ serait inventer une API que le serveur ignorerait en
silence.

Le `task_id` qui arrive dans un événement Skill est donc **généré par
l'agent**, sans aucun rapport avec celui de Hermes OS. Les deux portent le
même nom et ne désignent pas la même chose.

#### Ce qui remonte, remonte trop tard

`_extract_session_id` récupère bien le `session_id` de l'agent, depuis
stdout ou le fichier d'usage — mais à la **complétion**, donc après les
événements Skill du tour. Et il n'est écrit nulle part : ni dans le Ledger,
ni ailleurs.

#### Le plafond de granularité est la session, pas le Run

    cle_de_session({'project_id': 'P1', 'mission_id': 'M-alpha'}) -> 'projet:P1'
    cle_de_session({'project_id': 'P1', 'mission_id': 'M-beta'})  -> 'projet:P1'

Deux missions d'un même projet **partagent la session**, et c'est délibéré :
`cle_de_session` groupe par projet pour qu'une campagne de 26 sections garde
sa continuité. Un `session_id` ne désigne donc pas une mission. Et une
mission porte plusieurs Runs — `runs.tentative`, `runs.parent` — si bien
que même une session 1:1 avec une mission ne désignerait jamais un Run.

#### Rien n'est persisté, et un commentaire l'affirmait

`SessionsDeMission._identifiants` est un dictionnaire **en mémoire** : une
instance neuve le trouve vide. Son commentaire annonçait pourtant la survie
« après un redémarrage du backend ». G-29 était venu y chercher une clef de
jointure durable ; bâtir dessus aurait pris une table volatile pour une
trace. Le commentaire est corrigé.

La table `runs` porte **29 colonnes**, aucune de session. Et `audit_log` a
exactement les colonnes qu'il faudrait — `session_id`, `task_id`,
`project_id` — pour **six lignes**, toutes des vérifications manuelles
d'août, `task_id` toujours `NULL`.

#### Pourquoi DEFER et non REJECT

Rien n'est faux dans l'architecture : les frontières d'autorité sont nettes,
et c'est précisément parce qu'elles le sont qu'aucune des deux parties ne
peut fabriquer l'identité de l'autre. Il manque une donnée que seul l'amont
peut fournir.

REJECT, en revanche, sur les trois raccourcis à portée de main —
« l'événement le plus proche dans le temps », « la seule session ouverte »,
« le dernier Run démarré ». Ils produiraient des associations confiantes et
fausses, et des tests les interdisent maintenant.

#### Le chantier suivant

Il n'est pas dans Hermes OS. La relation deviendrait possible si l'agent
acceptait — et renvoyait — une **étiquette de tour fournie par le client** :
un champ que Hermes OS pose sur `session/prompt` et que
`on_skill_lifecycle` restitue. C'est une demande à formuler en amont, pas
une capacité à construire ici. Tant qu'elle n'existe pas, l'observateur de
G-28 reste non installé : sans relation, il n'aurait rien à corréler.

### G-30 — l'étiquette de tour existe déjà, à moitié (HOS-278)

G-29 concluait qu'il faudrait un identifiant de tour fourni par le client.
G-30 est allé voir si le runtime peut le porter. **Le transport existe,
nativement, et il est mesuré.**

    le transport, côté ACP           ADOPT    natif, mesuré
    la restitution dans l'événement  ADAPT    trois points amont
    le contrat complet, aujourd'hui  bloqué   non livrable ici
    la même chose côté Gateway       REJECT   canal privilégié
    un registre propre à Hermes OS   REJECT   seconde vérité

#### `_meta` arrive déjà au handler de l'agent

`PromptRequest` d'ACP v0.11.2 (`PROTOCOL_VERSION = 1`) porte `_meta`,
*réservé par le protocole pour que clients et agents attachent des
métadonnées à leurs interactions*. Et le routeur le **déplie en arguments
nommés** :

```python
params = {k: getattr(model_obj, k) for k in model.model_fields if k != "field_meta"}
if meta := getattr(model_obj, "field_meta", None):
    params.update(meta)
return await func(**params)
```

Mesure du 2026-09-10, en envoyant `_meta: {"hermes": {"turnId":
"run-42#tour-3"}}` au runtime installé :

    kwargs reçus : {"message_id": null, "hermes": {"turnId": "run-42#tour-3"}}

La signature de l'agent est `prompt(self, prompt, session_id, **kwargs)` :
la métadonnée **arrive**, et l'agent l'ignore. L'espace de noms n'est pas
inventé non plus — `acp_adapter/provenance.py` décrit déjà une *« additive
Hermes extension under ACP `_meta.hermes` »*, dans le sens sortant.

#### Ce qui manque, et où exactement

Trois coutures, toutes existantes : lire le champ dans
`acp_adapter/server.py:prompt()`, le lier au tour dans
`agent/turn_context.py` — à côté de `set_current_write_origin`, déjà lié là
par le même mécanisme — et le restituer dans `_emit_skill_lifecycle`
(`tools/skill_usage.py`). Zéro changement de protocole, aucune méthode
nouvelle.

Hermes OS ne peut pas écrire ces trois lignes. **ADAPT** ne veut donc pas
dire « constructible maintenant » : la spécification est écrite, la demande
est formulée, et le contrat reste bloqué amont.

#### La propriété qui le distingue de tout ce que G-29 a écarté

Le `turnId` voyage **dans l'événement**, pas dans une table partagée. Il n'y
a donc rien à garder entre l'émission et la lecture, et rien à perdre au
redémarrage. `SessionsDeMission._identifiants` était volatile, le Ledger n'a
pas de colonne de session, `audit_log` a six lignes : un contrat qui
dépendrait d'un état partagé hériterait des trois. Celui-ci n'en dépend pas.

#### Les options écartées

`messageId` est **UNSTABLE** et s'échoerait dans la `PromptResponse`, pas
dans les événements Skill. Le `_hosted_task` du Gateway est le précédent le
plus proche — `prompt.submit` accepte déjà une enveloppe cliente portant un
`turn_id` — mais sa garde exige `session["source"] == "bot_room"` **et** un
callback **appelable**, un objet Python qui ne traverse pas JSON-RPC.

#### Une mesure qui corrige G-29 au passage

Sur le chemin ACP, le `task_id` de l'agent **est** son `session_id` :
`run_conversation(..., task_id=session_id)`. G-29 disait que `task_id`
n'était pas un `run_id` ; G-30 ajoute qu'il n'est même pas un identifiant
de tour.

### G-31 — le contrat turnId, implémenté et démontré (HOS-279)

G-30 avait classé la restitution **ADAPT** : trois lignes à trois coutures
existantes, que Hermes OS ne pouvait pas écrire. G-31 les a écrites chez
l'agent, et a mesuré la chaîne complète. **ADOPT.**

#### La chaîne, mesurée

Réelle à chaque maillon sauf un — le corps du tour, où le modèle déciderait
d'appeler `skill_manage`, remplacé par une mutation déterministe. C'est la
*décision* du modèle qu'on substitue, pas le mécanisme :

    _meta → MessageRouter réel → HermesACPAgent.prompt() réel
          → _run_agent_turn réel (copy_context + ExitStack)
          → skill_manage réel → _emit_skill_lifecycle réel → plugin réel

    g31-a              turn='A'
    g31-b              turn='B'
    g31-c1             turn='C'   ┐ deux Skills,
    g31-c2             turn='C'   ┘ un seul tour
    g31-sans           turn=None
    g31-meta-vide      turn=None    `_meta` sans `hermes`
    g31-hermes-vide    turn=None    `hermes` sans `turnId`
    g31-hors-tour      turn=None    hors de tout tour
    g31-x              turn='X'   ┐ deux tours
    g31-y              turn='Y'   ┘ concurrents

La clé est **absente**, pas vide, quand aucun `turnId` n'est fourni. Après
redémarrage, un tour sans `turnId` n'hérite d'aucune identité précédente,
alors que `A B C X Y` étaient sur le disque. Et `.usage.json` ne porte aucun
champ de tour : **rien n'est persisté pour la corrélation**.

#### Une couture mal nommée par G-30

G-30 désignait `agent/turn_context.py`. La mesure a corrigé :
`acp_adapter/server.py:_run_agent_turn` est le *« Executor-thread body of one
turn, run inside `contextvars.copy_context()` so ContextVar writes are
isolated from concurrent sessions »*. L'isolation entre tours concurrents y
est déjà **architecturale**, et la fonction porte un `ExitStack` où les
autres contextes de tour sont liés. Lier ailleurs aurait été lier sur le
thread de la boucle, hors du contexte copié.

#### La provenance, et sa limite

`integrations/hermes-agent/contrat-correlation/turn-id.patch` est le
`git diff` exact contre le checkout de l'agent à **`693641aa8b`** (v0.21.0) :
83 lignes, trois fichiers, zéro changement de protocole.

**Le patch vit dans un checkout local.** `hermes update` fait un `git pull`
avec autostash : le patch est mis de côté puis réappliqué, au mieux, et un
changement amont conflictuel l'échouerait. Ce n'est pas une base durable —
c'est pourquoi le patch est versionné ici, et pourquoi la seule fin correcte
est son adoption amont.

La suite de l'agent est restée à son état d'avant, mesurée avant et après par
`git stash` : **6 échecs, 232 passés, 3 ignorés**, jeu d'échecs identique —
tous des limitations Windows préexistantes (symlinks, `fcntl`, `PosixPath`).

#### Un défaut trouvé dans l'observateur de G-28

La sonde de mesure a perdu un fait sur deux quand deux tours concurrents ont
émis en même temps : `state.get(...)` puis `state.set(...)` — chaque appel
est atomique, la **paire** ne l'est pas. L'observateur de G-28 avait la même
forme. Corrigé : une clé par fait, et une façade de lecture qui les rend
ordonnés. Un observateur qui perd silencieusement la moitié de ce qu'il
observe est pire qu'absent.

### G-32 — la corrélation Run ↔ Skill, établie (HOS-280)

**ADOPT.** La chaîne que G-29 avait mesurée impossible existe, de bout en
bout, sur deux processus et par-delà un redémarrage.

    phase 1 (Hermes OS)  Run lié          : RUN-Z
                         requête ACP      : _meta.hermes.turnId = 2a374b49…
                         relation écrite  : RUN-Z
    phase 2 (agent)      Skill g32-une   → client_turn_id = 2a374b49…
                         Skill g32-deux  → client_turn_id = 2a374b49…
    phase 3 (NOUVEAU     étiquette lue → Run retrouvé : RUN-Z
             processus)  étiquette étrangère          : (aucun)

Aucune identité ne change de propriétaire : Hermes OS garde `run_id`,
l'agent garde `task_id` et `session_id`, et l'étiquette est une **troisième**
identité, opaque, que Hermes OS frappe et reconnaît.

#### Ce que la mesure a corrigé dans ma lecture

Le chemin traverse `_run_coro`, qui pousse la coroutine vers une boucle d'un
**autre thread** par `run_coroutine_threadsafe`. J'avais conclu qu'un
`ContextVar` n'y survivrait pas et que le design par contexte était mort.
Mesure : il survit — `call_soon_threadsafe` copie le contexte de l'appelant.
La lecture du code disait le contraire.

#### D'où vient le Run, et pourquoi ce n'est pas une devinette

`execute_task` résout `self._runs.get(sm._meta.execution_id)` — la table que
`_ouvrir_le_run` a posée. Une **correspondance enregistrée**, pas le dernier
Run ni le plus récent : G-29 avait REJETÉ ces trois raccourcis, et des tests
les interdisent. `run_de()`, l'accesseur que G-29 avait trouvé sans appelant,
décrivait déjà cette table.

#### Où vit la relation

Sur le **bus durable**, parce que `backend/runs/registre.py` a déjà tranché :
*« le registre porte les runs ; le bus porte les événements ; `run_id` les
relie »*. Une table `turns` serait le second magasin d'événements que ce même
commentaire refuse. Topic `run.turn.emitted`, ajouté à l'enum fermé comme sa
docstring l'exige.

**Rétention de sept jours** (`EventBusImpl(retention_days=7)`) : la relation
est interrogeable une semaine, puis élaguée. C'est la politique du bus, et la
changer serait une décision de bus.

#### La règle qui tient tout le reste

Une étiquette n'est posée que si sa relation a été **écrite**. Sans Run lié —
le chat, une tâche hors mission — ou sans bus, `etiquette_du_tour()` rend
`""`, et la requête ACP ne porte **aucune clé `_meta`** : elle est octet pour
octet celle d'avant. Une étiquette sans relation promettrait une corrélation
que personne ne pourrait résoudre.

#### L'observateur de G-28 a maintenant un lecteur

Le préalable posé en G-28 — *« rien ne lit la relation »* — est levé :
`correlation.run_du_tour()` la lit. L'observateur reste non installé dans
cette passe, comme le brief l'exigeait, mais la raison de l'attendre a
disparu. Son installation est le jalon suivant.

### G-33 — l'observateur installé, et la boucle fermée (HOS-281)

**ADOPT.** Le plugin tourne pour de vrai, sous
`%LOCALAPPDATA%\hermes\plugins\hermes-os-observateur-skills`, activé par
`plugins.enabled`, et `scan_plugin` rend « aucun import interne » — sa
condition de survie au retrait du 2026-09-14, dans quatre jours.

#### La chaîne, avec l'observateur réellement installé

    phase 1 (Hermes OS)  RUN-ALPHA → ffb603fc…    RUN-BETA → 9039b9d6…
    phase 2 (agent)      g33-une  turn=ffb603fc…
                         g33-deux turn=ffb603fc…
                         g33-trois turn=9039b9d6…
    phase 3 (NOUVEAU     RUN-ALPHA  ['g33-deux', 'g33-une']
             processus)  RUN-BETA   ['g33-trois']

#### Ce que l'agent fait quand le plugin ne marche pas

Les trois défaillances, avec les Skills vérifiées **sur le disque** :

    plugin absent      non chargé   0 fait   Skills écrites
    plugin désactivé   chargé, off  0 fait   Skills écrites
    callback qui lève  chargé, on   0 fait   Skills écrites

L'observateur ne peut pas bloquer l'agent — G-28 l'avait établi par
construction, G-33 le mesure avec le plugin en place.

#### Le patch, adopté

`turn-id.patch` est désormais un **commit** du dépôt de l'agent
(`fb6335dd14`, sur `693641aa8b`), et non plus un arbre de travail sale. Le
répertoire `integrations/hermes-agent/observateur-skills/` reste la source
du plugin : l'installation en est une copie, et un test compare les octets
pour qu'il n'existe jamais deux versions du même observateur.

#### Trois lectures, un seul propriétaire

`backend/skills/observations.py` est la **troisième** fois que Hermes OS lit
le disque de l'agent — après les compétences (HOS-274) et leur provenance
(HOS-275) — et la posture ne change pas : lire, jamais écrire, jamais
copier. Le fait appartient au plugin, la relation `T → R` au bus de Hermes
OS, et aucun des deux ne migre dans l'autre.

Les observations non rattachées sont **écartées** du groupement plutôt que
rangées sous une clé « inconnu » : une telle clé se lirait comme un Run et
finirait affichée à côté des vrais.

### G-34 — la relation, montrée (HOS-282)

**ADOPT.** L'onglet **Runs ↔ Skills** du Skills Center sert
`GET /skills/observations` : il montre quel Run a muté quelle Skill, et
c'est la première surface produit de la relation construite de G-29 à
G-33.

#### Mesuré sur la chaîne réelle, bout en bout

Bus durable réel, Run Ledger réel, quatre Runs réellement ouverts, chemin
ACP réel (`_meta.hermes.turnId`), observateur réellement installé. Seul le
disque des Skills de l'agent est substitué — y poser sept compétences de
démonstration serait l'écriture non justifiée que le brief interdit.

    RUN 0654af85…  perdu   g34-alpha (created), g34-partagee (created)
    RUN 8d1a5993…  perdu   g34-partagee (edited)
    RUN 1c9276d1…  perdu   g34-concurrent-c    ┐ deux tours réellement
    RUN e3e9d384…  perdu   g34-concurrent-d    ┘ concurrents, sans mélange
    run-hors-ledger-g34    g34-hors-ledger  → « absent du Run Ledger »
    sans Run               g34-hors-run     → « aucune étiquette »
                           g34-etrangere    → « étiquette non résolue »

`g34-partagee` porte les deux moitiés du contrat : **un même Skill muté
par deux Runs différents**, et la vue « Par Skill » l'affiche `2
mutation(s) · 2 Run(s)`. Les quatre Runs s'affichent `perdu` — la
réconciliation du Ledger les a marqués ainsi parce que le processus qui
les avait ouverts n'existait plus. C'est le Ledger qui parle, pas une
donnée figée.

#### Quatre absences, quatre libellés distincts

C'est le cœur de la passe. Un écran qui range ce qu'il ne sait pas au même
endroit que ce qu'il sait détruit à l'affichage cinq passes de mesure :

| ce qui manque | ce que l'écran dit |
|---|---|
| le tour n'avait pas de `turnId` | « aucune étiquette » |
| l'étiquette n'est pas de Hermes OS, ou est élaguée | « étiquette non résolue » |
| le Run n'est pas dans le Ledger | « absent du Run Ledger » |
| le Ledger n'a pas pu être lu | « registre indisponible » |

Les deux dernières se confondraient sans le drapeau `registre_lisible` :
une panne de base ferait dire « Run inconnu » de Runs parfaitement
enregistrés. Une **mutation** l'a prouvé — la garde initiale passait le
couple en dur et n'exerçait jamais la fonction qui le pose.

#### Un contrat périmé, corrigé

L'onglet Agent affirmait « Aucune compétence n'est rattachée à un Run ».
G-33 l'avait rendu faux **sans que rien ne rougisse**, parce que c'était
une affirmation d'écran et non une lecture de donnée. La phrase est
désormais bornée à l'inventaire — aucun fichier de compétence installée ne
nomme un Run, ce qui reste vrai — et renvoie à l'onglet où la relation
existe. Deux gardes de G-27 ont été rescopées pour la même raison : leur
**nom** décrivait le dépôt entier là où leur mesure ne portait que sur
l'inventaire.

### G-35 — la gouvernance du cycle de vie (HOS-283)

**ADOPT sur la vérification, DEFER sur le déclenchement**, et les deux
verdicts sont mesurés plutôt que supposés.

#### Le dossier existait, et personne ne le lisait

L'agent tient déjà le dossier complet du cycle de vie de ses Skills, sur
son disque, sous `<HERMES_HOME>/skills/.hub/` :

    audit.log   une ligne par opération : INSTALL, BLOCKED, UNINSTALL
    lock.json   source, identifiant, niveau de confiance, verdict du
                scanner, empreinte, et les findings avec leur sévérité

Aucun module de Hermes OS ne l'ouvrait. C'est le défaut le plus fréquent
de ce dépôt sous sa forme la plus pure : la donnée de gouvernance est
produite, complète, datée — et sans lecteur.

#### Le chemin réel, mesuré de bout en bout

Hub réel (5493 entrées), scanner réel, quarantaine réelle, sur un
`HERMES_HOME` de substitution :

| demande | disque | journal | ce que la RPC dit |
|---|---|---|---|
| `official/devops/actual-setup` | posée | `INSTALL … dangerous` | `installed: true` |
| `skills-sh/mindrally/…/docker` | posée | `INSTALL … safe` | `installed: true` |
| `skills-sh/bobmatnyc/…/docker` | **rien** | `BLOCKED … dangerous 25_findings` | `installed: true` |
| `docker`, `skill-docker`, … | **rien** | **rien** | `installed: true` |
| la même, déjà posée, sans `--force` | **rien** | **rien** | `installed: true` |

Deux verdicts `dangerous`, deux issues opposées : la première est passée
parce que sa source est `builtin`, la seconde a été bloquée parce qu'elle
est `community`. Un écran qui dirait « installée » sans montrer les deux
tairait exactement ce dont un opérateur a besoin.

Et `actual-setup` est posée avec **cinq findings critiques** — dont un
`env_exfil_curl`. La politique de l'agent l'autorise ; rien ne le montrait.

#### La vérification tient à l'octet

`content_hash` est une SHA-256 canonique sur (chemin POSIX, octets).
Recalculée dans `backend/skills/gouvernance.py`, elle rend **exactement**
celle du verrou sur les deux compétences posées. Un seul octet ajouté
après coup fait basculer l'état en `alteree` — vérifié dans le navigateur,
sur le disque, l'écran suivant.

Réimplémentée plutôt qu'importée : `plugin_compat` désactive au
2026-09-14 tout code externe qui importe les internes de l'agent, et une
empreinte de gouvernance ne doit pas mourir avec une date.

#### Pourquoi le déclenchement reste DEFER

`do_install` est annoté `-> None` et rend `None` sur **tous** ses chemins,
succès compris : il n'y a aucune valeur de retour à corriger en amont, et
G-26 avait raison de refuser le bouton. La vérification lève cette
objection — Hermes OS peut désormais dire ce qui a réellement été écrit.

Ce qui la remplace est plus dur, et c'est une **découverte de cette
passe** : il y a **deux files d'approbation**, et le cockpit regarde la
mauvaise. La file vivante, celle qu'Aegis remplit (`record_pending`,
servie par `/security/approvals`), n'a **aucun appelant frontend** — elle
figure dans les orphelins connus. Celle que le Dashboard affiche est
`/approval`, servie par `backend/policy/`, alimentée seulement par
`autonomous_guard`. Router une installation de Skill vers la file vivante
la rendrait invisible ; la router vers l'autre ne garderait rien.

C'est exactement le motif que G-26 avait nommé pour le `pending` de
l'agent — « le producteur existe, l'approbateur est injoignable » — un
étage plus haut, et cette fois chez nous. **G-36** : rendre la file
d'approbation vivante joignable depuis le cockpit.

### G-36 — l'approbation raccordée, la pose gouvernée (HOS-285)

**ADOPT.** La chaîne complète fonctionne sur le chemin réel : demande →
approbation Aegis → décision humaine → autorisation ou refus → pose
réelle → provenance et audit → résultat visible.

#### Laquelle des deux files, et pourquoi

G-35 avait trouvé deux files d'approbation sans trancher. Mesuré le
2026-09-11 :

| | Aegis (`/security/approvals`) | Policy (`backend/policy/`) |
|---|---|---|
| stockage | SQLite `PendingApproval` | dict **en mémoire** |
| producteur réel | `AegisAgent`, sur le chemin de requête | **aucun** — `set_policy_engine` n'est jamais appelé |
| survit au redémarrage | oui | non |
| lu par le cockpit | **non** | oui |

Elles ne font pas la même chose, et **elles ne sont pas fusionnées** : la
première est un jeton de passage (une fois, quinze minutes, empreinte
exacte), la seconde une demande de workflow (multi-approbateurs,
délégation). Mais une seule est branchée, et c'est elle qui garde les
actions réelles. L'approbation d'une pose de Skill lui revient.

La preuve de l'écart tient en une mesure : la file d'Aegis portait **206
demandes `pending` du 2026-08-10 au 2026-09-02** qu'aucun écran ne pouvait
montrer, pendant que le Dashboard affichait « File d'approbation vide ».

#### Le contrat d'Aegis impose l'enchaînement

« Approving here does **not** replay the action » : une approbation
autorise **la prochaine tentative identique**, une fois. Donc :

    1. demande       → REQUIRE_HUMAN_VALIDATION, rien n'est posé
    2. l'humain décide dans le cockpit
    3. on redemande  → l'approbation est consommée, et seulement là
                       quelque chose s'écrit

Ce n'est pas un détour d'implémentation : une file qui rejouerait des
actions stockées aurait besoin d'un répartiteur capable de tout
réexécuter, ce qu'une barrière de sécurité ne doit pas posséder.

#### Les huit preuves, mesurées

Foyer de substitution pour le disque des Skills ; Aegis, sa file SQLite,
le vrai gateway lancé par le pont, le scanner de l'agent et le disque sont
réels.

    1. demande                  → approbation_requise, disque VIDE
    2. visible dans la file d'Aegis (`skill_install`)
    3. refus utilisateur        → approbation_requise, disque VIDE
    4. accord puis nouvel essai → posée, `docker` conforme,
                                  sha256:916f3198efaa5a18 des deux côtés
    5. provenance               → source=skills.sh confiance=community
                                  verdict=safe ; audit : INSTALL docker
    6. cockpit                  → « Install skill … · skill_install ·
                                  hermes-os.cockpit » en tête du Dashboard
    7. processus NEUF           → pose ET décisions retrouvées ;
                                  l'accord est passé à `used`
    8a. conflit (déjà posée)    → sans_effet, disque inchangé
    8b. danger, nom libre       → bloquée_par_le_scanner, disque VIDE,
                                  audit : BLOCKED docker 25_findings

**L'approbation humaine n'est pas un contournement du scanner** : Aegis
autorise la *demande*, le scanner de l'agent garde la *pose*. 8b l'a
d'abord caché — la compétence dangereuse s'appelle aussi `docker`, et sur
un foyer où ce nom était pris `do_install` sort sur « déjà installée »
**avant** d'atteindre le scanner. On mesurait un conflit en croyant
mesurer une sécurité.

#### Le résultat vient du disque

`skills.manage install` rend `{"installed": true}` dans tous les cas. Le
verdict rendu est tiré d'un **diff du disque** pris de part et d'autre de
la demande : une clé neuve dans le verrou dont le dossier vérifie son
empreinte, une ligne `BLOCKED` neuve, ou rien. Il n'est déduit ni de
l'identifiant, ni d'un nom calculé, ni d'un booléen.

**Ce que §10 attend encore.** Le versioning et le rollback : le ledger de
l'agent (`.curator_ledger.jsonl`) les porterait, mais il **n'existe pas**
sur cette installation, et aucune RPC ne l'expose. Appariement skill ↔
tâche reste PLANNED.

**G-39 (HOS-288) a vérifié la chaîne après retrait.** La demande
`skill_install` déposée en G-36 est toujours en tête de la file d'Aegis
dans le cockpit, avec sa raison — « skill_install always requires human
validation (§17.3) » — et ses deux boutons. Rien de la suppression de
`backend/policy/` ne l'a touchée.

**G-37 (HOS-286) a confirmé l'autorité qui garde la pose.** L'audit de
`backend/policy/` cherchait si une seconde autorité pouvait revendiquer
l'approbation d'une Skill. Elle ne le peut pas : ses règles ne sont
évaluées nulle part, et aucune ne mentionne l'installation. `skill_install`
reste gardé par Aegis seul, et une garde interdit désormais de câbler
l'autre moteur sans trancher laquelle des deux politiques s'applique.

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

## §15 — Frontend ↔ Backend Product Parity / Hermes Assistant — 🟠 PLANNED

**§15 est une couche produit, pas un second backend.** Elle n'introduit
aucune source de vérité : elle consomme celles qui existent. Toute
capacité qui aurait besoin d'une autorité nouvelle n'appartient pas à
§15 — elle appartient à la section qui possède déjà le domaine, et §15
attend.

> **La règle de cette section.** Une fonctionnalité d'Assistant ne se
> déclare pas faite parce que son endpoint existe. §0 s'applique
> intégralement : `PRESENT` n'est pas `CALLED`, et une route montée que
> personne n'appelle est le défaut le plus fréquent de ce dépôt.

> **G-40 (HOS-289) — le corollaire, et il est pire.** Une route jamais
> appelée laisse un écran vide, donc visible. Un écran **rempli de
> littéraux** ne laisse rien voir du tout. Trois passes ont trouvé le même
> demi-nettoyage : les mocks **nommés** retirés, les tableaux littéraux
> laissés en ligne dans le JSX, et un commentaire affirmant que le ménage
> était fait. On cherche `MOCK_` ; on ne cherche pas un tableau d'objets.
> Une garde le cherche désormais sur les 26 Centers, et le discriminant
> tient sans liste blanche : **une donnée inventée n'a que des littéraux,
> un descripteur de présentation référence quelque chose**. Vérifiée par
> onze mutations, dont deux ont d'abord trouvé vert — l'exemption
> « description » se prenait avec un mot, et le corpus pouvait s'effondrer
> en silence.

### Pourquoi cette section existe, mesuré

L'audit J25 avait déjà chiffré l'écart, et §9 le porte : **142 des 302
routes `/api/v1` montées ne sont jamais appelées par le frontend**. Le
constat de cette passe est plus précis, et il est le sujet même de §15 —
des capacités **livrées, testées, et sans consommateur produit** :

| capacité | backend | frontend | niveau réel |
|---|---|---|---|
| Explication de décision (`DecisionExplainer`) | 3 routes montées | **0 appel** | `CALLED` = non (A-8) |
| Quarantaine / provenance mémoire | 4 champs exposés | **0 affichage** | `ACTUALLY USED` = non (G-3) |
| Promotion d'un souvenir | 4 niveaux, testé | **aucune route HTTP** | `PRESENT` (G-10) |
| Points de reprise | `prendre` appelé | aperçu + restauration branchés (HOS-291) | `DEMONSTRATED` (A-3 fermé) |
| Cycle de vie des skills | 9 routes, **aucune création** | liste seule | `PRESENT` (G-5) |
| `assigned_tools` d'une tâche | planifié, jamais invoqué | — | décoratif, rapport corrigé (G-11 fermé HOS-294) |

§15 n'invente donc pas un produit : elle **branche celui qui est déjà
construit**, et nomme ce qui manque réellement.

**Précision apportée par HOS-274, et une correction.** La ligne « cycle de
vie des skills » ci-dessus parle des 9 routes de `backend/skills/` — le
magasin de Hermes OS, toujours vide. Les compétences du **cerveau**, elles,
vivent sous `%LOCALAPPDATA%\hermes\skills`.

Le Skills Center les affichait déjà — **et se trompait de dossier** : 60
noms au lieu de 65, dont vingt que l'agent ne sert pas sur cette
plateforme. C'était un consommateur produit réel branché sur une source
fausse, ce qui est pire qu'une route sans appelant : §15 mesure l'absence
de consommateur, pas la justesse de ce qu'il consomme, et les deux
manquent. §10 porte la mesure et la correction.

Le catalogue du hub y rejoint les deux registres existants, en lecture
seule (trois routes `GET`, trois appelants). Trois registres, un écran, et
aucun qui raconte l'autre.

**Et depuis HOS-275, la colonne « d'où elle vient ».** Elle porte une
catégorie **et sa preuve** — le fichier de l'agent qui la soutient, en
infobulle. C'est la règle que §15 devait déjà appliquer et n'appliquait
nulle part : une interface qui affirme sans pouvoir montrer sa source est
une affirmation, pas une lecture.

**HOS-276 n'ajoute aucune surface, et c'est la décision.** Le plugin
observateur est écrit, mesuré, et **pas installé** : sans écran qui lise la
relation Run ↔ Skill, le poser créerait un producteur sans lecteur. §15
mesure d'ordinaire l'inverse — des routes sans appelant — et la symétrie
vaut : un producteur sans consommateur est le même défaut, pris par
l'autre bout.

**HOS-277 ferme la question autrement qu'attendu.** L'écran manquant n'était
pas le blocage : la relation qu'il aurait affichée **n'existe pas** (§10,
G-29). §15 n'a donc rien à brancher ici, et c'est un résultat, pas un
report — une parité ne se mesure qu'entre deux choses qui existent.

**HOS-278 nomme la condition de réouverture.** La relation deviendrait
affichable si l'agent restituait un `turnId` fourni par le client — le
transport existe déjà et la mesure le prouve (§10, G-30). §15 reste donc
fermé sur ce point, mais plus pour une raison inconnue : pour une raison
écrite, localisée en trois fichiers amont.

**HOS-279 lève cette condition, sur un agent patché.** La restitution est
implémentée et démontrée (§10, G-31). §15 ne s'ouvre pas pour autant : le
patch est local, et Hermes OS n'envoie toujours pas de `_meta` — poser le
champ sans savoir si l'agent en face le restitue produirait un écran qui
affiche « non corrélé » sans pouvoir dire pourquoi.

**HOS-280 ouvre la porte, et §15 reste volontairement fermé.** La relation
existe et se lit (`correlation.run_du_tour()`), mais aucun écran ne la
montre — et c'est la bonne séquence. Un écran demanderait d'abord que
l'observateur soit installé chez l'agent, faute de quoi il afficherait « non
corrélé » pour tous les Runs. §15 attend donc **deux** jalons, dans cet
ordre : l'observateur, puis la surface.

**HOS-281 franchit le premier.** L'observateur est installé et observe
(§10, G-33) ; `backend/skills/observations.py` rend les mutations groupées
par Run.

**HOS-282 franchit le second, et ferme la séquence.** L'onglet
**Runs ↔ Skills** consomme `GET /skills/observations` et montre la
relation sur de vrais événements — vérifié dans le navigateur, pas
seulement en test. C'est la première fois de cette série qu'une capacité
traverse §16 (le transport), §10 (la donnée) et §15 (l'écran) sans
qu'aucun maillon ne soit `PRESENT` sans être `ACTUALLY USED`.

### G-39 — la vérification transversale (HOS-288)

Après le retrait, ce que le dépôt porte encore, mesuré :

| vérification | résultat |
|---|---|
| imports de `backend.policy` | **0** — les deux mentions restantes sont des commentaires qui documentent le retrait |
| clients frontend visant une route absente | **0** — 131 chemins littéraux confrontés aux 338 routes montées |
| entrées d'orphelins désignant une route disparue | **0** sur 118 |
| requêtes vers `/approval`, `/audit`, `/policy/*` | **0**, observées dans le navigateur |
| Aegis, journal §18, Run Ledger, Event Bus | les quatre répondent 200 |

#### Ce que la vérification a trouvé

**Trois tableaux fabriqués dans le Security Center** — voir §3. C'est la
trouvaille de la passe, et elle n'a rien à voir avec Policy : elle a été
trouvée en balayant les écrans pour des références Policy.

**Un document de référence qui se trompait.**
`security-systems.md` — le fichier écrit pour empêcher qu'on confonde les
systèmes de permission — affirmait que `PolicyEngine` avait « de vrais
appelants » dans `recovery_engine`, `workspace_manager` et
`runtime_decision`. Aucun des trois n'importait `backend.policy` : ils ont
leurs propres moteurs, qui portent le même nom. Quatre objets appelés
« PolicyEngine », et le document censé les distinguer les confondait. Un
lecteur qui lui aurait fait confiance aurait cru que G-38 cassait trois
sous-systèmes ; il n'en a cassé aucun.

Corrigés aussi : `backend-map.md` (ligne décrivant le module comme
« live »), `POLICY_ENGINE_ARCHITECTURE.md` (124 lignes décrivant le module
comme « the central governance authority » — supprimé), et le sous-titre
du Governance Center, qui annonçait encore « moteur de politiques ».

#### La limite de preuve, levée

Depuis G-34, je rapportais que la navigation du cockpit ne répondait pas à
l'automatisation. Diagnostiqué ici : le clic atteint bien le bouton — rien
ne l'intercepte, la position est exacte — mais l'événement synthétique du
panneau ne déclenche pas le gestionnaire React. Un `click()` programmatique
bascule la vue immédiatement. **L'application n'avait rien ; c'est
l'instrument qui ne mordait pas**, et trois passes ont porté une réserve
qui n'avait pas lieu d'être.

### G-37 — l'audit de `backend/policy/` (HOS-286)

**REJECT comme autorité**, et les trois responsabilités du module sont
re-attribuées à leur propriétaire réel. Mesuré le 2026-09-11.

| responsabilité | verdict | autorité réelle |
|---|---|---|
| évaluation de politique | **REJECT** | Aegis — `config/security.yaml` + `AegisEngine`, relu à chaque évaluation |
| file d'approbation | **REJECT** | Aegis — `security/approvals.py` (SQLite), fermé en G-36 |
| journal d'audit | **REJECT** | `core/audit_log.py` — §18, SQLite + fichiers, rédaction à l'écriture |

#### Ce qui l'établit

- `set_policy_engine` n'est **jamais appelé**. `set_security_engine`, si —
  `service_registry` y injecte `AegisSecurityAdapter`. Le seul appelant de
  `PolicyEngine.evaluate` est `autonomous_guard`, derrière
  `if self._policy_engine:`, donc mort.
- Les trois événements que son `ServiceSpec` déclare produire —
  `approval.requested`, `approval.granted`, `audit.created` — comptent
  **zéro occurrence** sur le bus durable.
- Il porte **dix règles en dur**, jamais évaluées, dont deux
  **contredisent** la politique en vigueur : `internet_access_allowed:
  allow` contre `network_call` qui exige « high », et
  `system_modification_denied: deny` contre `system_config` qui demande un
  humain — pas un refus.
- Sa file et son journal sont **en mémoire** : zéro entrée, rien ne
  survit à un redémarrage. Ses dix règles sont des constantes de code :
  aucune route ne les crée, ne les modifie ni ne les supprime, et un
  redémarrage rend exactement les mêmes.
- Le journal du §18, lui, porte **six entrées réelles** (2026-08-14),
  écrites par les tours de chat — et **aucun lecteur**.

#### Le même défaut, trois fois, sur le même écran

Le Governance Center avait trois onglets, et les trois lisaient
`backend/policy/` :

    approbations  file en mémoire sans producteur  → file d'Aegis (SQLite)
    règles        dix règles qu'aucun chemin        → matrice Aegis, celle
                  n'évalue, et qui contredisent        qu'Aegis relit à
                  la politique en vigueur              chaque évaluation
    audit         anneau en mémoire, 0 entrée       → journal du §18

Ce n'était pas une surface manquante : c'était un consommateur branché
sur la mauvaise source. Ni le compteur d'orphelins ni le typage ne
pouvaient le voir, puisque les deux surfaces existaient — et l'écran
affichait une politique de sécurité **qui ne gouvernait rien**.

#### La suppression, executée en G-38 (HOS-287)

La proposition ci-dessus a été suivie. `backend/policy/` n'existe plus :
9 modules, 1346 lignes, et le `ServiceSpec` qui les construisait.

    routes montées          344 -> 338   exactement -6
    sous-systèmes           23  -> 22    exactement le service retiré
    /policy/rules, /policy/evaluate, /approval,
    /approval/{id}/approve, /approval/{id}/reject, /audit   -> 404
    /security/approvals     200, 212 demandes — identique
    /security/autonomy      200 — identique
    /logs (journal §18)     200, 6 entrées — identique
    aucune autre route perdue

Et à l'exécution, dans le navigateur : **aucune requête** ne part vers
`/approval`, `/audit` ou `/policy/*`.

**Ce que la suppression a révélé.** Deux dépendances que le balayage
initial avait manquées, parce qu'il excluait `tests/` : une classe
`TestApprovalExplainer` de dix tests cachée dans un fichier de
conversation de 99 tests, et `test_policy_routes_are_bound` dans le test
d'assemblage. Un module ne se retire proprement qu'en cherchant aussi là
où on ne s'attend pas à le trouver.

**Et le compte des tests se tient exactement** : 6187 → 6130 collectés,
soit −57. Les trois derniers venaient de
`test_no_route_returns_5xx[...]`, **paramétré sur les routes montées** —
retirer trois routes `GET` retire trois cas. Un écart de tests non
expliqué aurait été le seul vrai risque de cette passe.

**HOS-285 ferme la ligne « approbations » du tableau ci-dessus.** Elle
n'y figurait pas, et c'est précisément ce que G-36 a trouvé : le cockpit
affichait une file d'approbation **qui n'a aucun producteur**, donc vide
par construction, pendant que la file vivante d'Aegis accumulait 206
demandes invisibles. Les trois hooks (`useApprovals`, `useApproveAction`,
`useRejectAction`) lisent désormais `/security/approvals`.

C'est le cas le plus net de la série : non pas une capacité `PRESENT` sans
consommateur, mais un consommateur branché sur la **mauvaise** source —
une classe de défaut que ni le compteur d'orphelins ni le typage ne
voyaient, parce que les deux surfaces existaient.

**HOS-283 ajoute la gouvernance, et corrige la ligne du tableau
ci-dessus.** « Cycle de vie des skills : 9 routes, aucune création, liste
seule » décrivait un `PRESENT`. L'onglet **Gouvernance** sert
`GET /skills/gouvernance` : ce que le hub a posé, avec le verdict du
scanner, le niveau de confiance qui a décidé, et l'état **vérifié à
l'octet** de chaque compétence. La création reste sans surface, et la
raison n'est plus « ça n'écrit pas de façon vérifiable » — c'est vérifiable
depuis G-35 — mais « l'approbateur est injoignable » (G-36).

§15 gagne au passage une dette nommée : le Dashboard affiche une file
d'approbation qui n'est pas celle qui garde les opérations réelles.

Ce que la ligne « Cycle de vie des skills » du tableau ci-dessus devient :
la **création** reste sans surface — G-27 a mesuré qu'`install` rend
`true` après un blocage de sécurité, et un bouton dessus mentirait. Ce qui
change est l'**observation** : ce que l'agent fait de ses Skills se lit
enfin, avec son Run.

### Ce que l'Assistant est aujourd'hui, mesuré

`frontend/src/features/conversation/` — 2 824 lignes, 12 fichiers. Ce qui
est **`ACTUALLY USED`**, vérifié en suivant les appels et non les imports :

- **Chat en flux** — `POST /conversation/stream`, NDJSON, canal de
  raisonnement séparé de la réponse ;
- **Décision de routage affichée** — `RoutingBadge` rend modèle, tier,
  rôle, raisonnement, intention et **la raison** : le « pourquoi ce
  modèle » existe déjà pour le tour de chat ;
- **Fenêtre de contexte** — `used_tokens_estimate` / `window`, affichée ;
- **Appels d'outils réels** — `onToolCall` / `onToolResult` rendus dans
  la transcription. Et il y en a **treize**, pas un : `web_search` en
  permanence, plus les onze opérations de fichiers de
  `workspace_chat_tools` et les deux exécuteurs de
  `verification_chat_tools` **dès qu'un projet validé est lié à la
  session**. L'Assistant sait donc déjà lire, écrire, déplacer et
  supprimer dans un workspace, et y lancer une vérification ;
- **Sessions** — liste, suppression, contexte, via les commandes slash ;
- **Projet lié à la session**, sélecteur de modèle, pièces jointes,
  entrée vocale, aperçu web.

Ce qui **n'existe nulle part dans le frontend** — vérifié par recherche
sur l'arbre entier : `cowork`, `worklog`, `fork`, `artifact` (hors banc de
modèles), invocation `@skill`.

Le plus proche d'un Cowork est le **Centre Autonome** (567 lignes) :
objectifs, statut, chronologie, rapport, actions, démarrage. Les
primitives d'un travail long **existent donc déjà** — elles vivent dans un
Centre d'opérateur, pas dans l'Assistant.

### Ce que §15 consomme, et ne redéfinit pas

```
§15 → consomme §2   Run Ledger        lignée, tentatives, motif de reprise, consommation
§15 → consomme §3   Aegis, reprises   approbations, bac à sable, points de reprise
§15 → consomme §5   RAL               modèle, runtime, fournisseur, décision de routage
§15 → consomme §6   ResourceManager   capacité, admission, portillon, occupation mesurée
§15 → consomme §7   Orchestration     sous-agents, propriété des processus
§15 → consomme §8   Memory            provenance, quarantaine, promotion
§15 → consomme §9   Observabilité     explications, progression, trajectoire
§15 → consomme §10  Skills            découverte, sélection, cycle de vie
§15 → consomme §11  Collaboration     relecteurs, conseil, délégation
§15 → consomme §13  Voice/Multimodal  entrée vocale, documents, images
```

Aucune flèche ne part de §15 vers une décision. L'Assistant **montre** et
**demande** ; il ne décide ni de l'admission, ni du routage, ni de la
mémoire.

---

### Chronologie

L'ordre ci-dessous suit les **dépendances mesurées**, pas la valeur
perçue. Deux sous-chantiers sont réalisables aujourd'hui ; les autres
attendent une section qui les porte.

#### §15.1 — Assistant foundation / product contract — 🟠 réalisable

Écrire le contrat produit : ce qu'est une **session** de Chat, ce qu'est
un **Cowork**, ce que chacun garantit, et lequel des deux possède quoi.
Aucune ligne de produit avant que ce contrat soit tranché — c'est la même
discipline que T-22 impose à §6.

**Question à trancher : Chat et Cowork sont-ils deux surfaces ou deux
modes d'une seule ?** Le dépôt penche pour *deux modes* : la session de
conversation et l'objectif autonome partagent déjà le Run Ledger et le
bus d'événements, et les séparer en deux produits créerait deux histoires
pour une seule exécution. À décider en T-28.

**Critère de passage.** Le contrat nomme, pour chaque surface, l'autorité
consultée et l'identifiant qui corrèle (session, `run_id`, `mission_id`).

#### §15.2 — Chat UX consolidation — 🟠 réalisable

Coquille de l'Assistant, navigation entre sessions, composeur, pièces
jointes, sélection de modèle, flux, rail de contexte responsive.
Consolidation de ce qui existe : aucune dépendance ouverte.

**Critère de passage.** Aucune régression sur le flux NDJSON ni sur
l'affichage du routage ; les sessions restent lisibles après redémarrage.

#### §15.3 — Context & Workspace — 🟡 partiellement bloqué

Contexte de projet, fichiers, artefacts, aperçus, **inspecteur de
contexte** — ce qui a réellement servi ce tour : sources, mémoire,
fichiers, outils.

L'inspecteur est **réalisable** : `/conversation/{id}/context` existe et
n'est consommé que par une commande slash.

Les **artefacts** ne le sont pas — mais pas pour la raison qu'on
attendrait. Les opérations existent : onze outils de fichiers sont déjà
offerts au modèle, sous Aegis, dès qu'un projet validé est lié. Ce qui
manque est double :

- **la surface** — rien ne montre ce qui a été produit, ni ses versions.
  `backend/workspace/*` est une comptabilité en mémoire de créneaux
  d'exécution et ne touche pas le disque : ce n'est pas le magasin
  d'artefacts qu'on pourrait croire d'après son nom ;
- **la garantie** — la portée projet repose sur la bonne foi du modèle
  (**A-4**). Un panneau d'artefacts au-dessus de cela afficherait une
  isolation que personne ne fait respecter.

**Dépend de** : A-4 (habilitation de portée projet, §8/§10).

#### §15.4 — Cowork — 🔴 bloqué sur une dépendance nommée

Objectif, plan, progression, **worklog**, exécution en arrière-plan,
interruption et **reprise**, fork/branche.

Ce qui existe : objectifs, chronologie, rapport, annulation. Ce qui
manque, et c'est structurel :

- ~~**la reprise n'existe pas**~~ — **levé le 2026-09-11 (HOS-291)** :
  `apercu` et `restaurer` sont appelables depuis Supervision, gouvernés
  par Aegis et démontrés. Un Cowork qui propose « reprendre » ne
  mentirait plus — à une réserve près, qu'il devra porter : la
  restauration est en **deux temps** (accord humain obligatoire), donc un
  bouton qui prétendrait reprendre en un clic mentirait à son tour ;
- **fork/branche** n'a pas de primitive. `Registre.reprendre()` donne une
  lignée de tentatives, pas une branche de conversation. Créer l'une à
  partir de l'autre serait reconstruire un objet plausible — la famille de
  défaut que le registre de rejets nomme déjà ;
- **le worklog** est presque là : la chronologie du Centre Autonome et le
  bus d'événements le portent ; il n'est pas dans l'Assistant.

**Et une asymétrie qui décide d'où bâtir Cowork — G-11 en a clarifié la
nature sans la refermer.** Le **chat** dispose de treize outils réels
quand un projet est lié ; une **tâche de mission** n'en appelle aucun de
ce catalogue — `assigned_tools` (la recommandation d'`AgentCoordinator`)
reste un texte indicatif, jamais invoqué. **HOS-294 a fermé G-11** tel que
déposé dans la table des écarts : le rapport de mission ne fait plus
passer cette recommandation pour une mesure (`ExecutionReport.tools_used`
vient désormais de ce qui a réellement tourné). Mesuré en la fermant :
invoquer réellement `assigned_tools` violerait HOS-085 sur le chemin
hermes-agent, ou exigerait un second pont d'outils vers un catalogue que
la boucle locale ne peut de toute façon pas exécuter — donc **l'asymétrie
elle-même reste entière**, et n'était pas ce que G-11 promettait de
résoudre. Bâtir Cowork sur le chemin de mission demande toujours une
route neuve vers ce catalogue de treize outils, pas la fermeture de G-11 ;
le bâtir sur le chemin de conversation hérite d'outils qui marchent déjà.
C'est une question de §15.1, et elle n'est pas tranchée.

**Dépend de** : ~~A-3~~ (fermé HOS-291), §7 (orchestration), ~~G-11~~
(fermé HOS-294 — l'asymétrie qu'il décrivait reste ouverte, voir
ci-dessus), et de la décision T-28.

#### §15.5 — Explainability & resource visibility — 🟠 réalisable, et le meilleur rapport

Le « pourquoi ? » — action, modèle, routage, refus —, le contexte
réellement utilisé, l'état d'exécution, les ressources, le budget, la
provenance.

**C'est le sous-chantier le moins cher et le plus rentable**, et la mesure
le dit : `DecisionExplainer` produit déjà des explications que **personne
ne demande** (A-8), la provenance est exposée et **affichée nulle part**
(G-3), et §6 vient de rendre la ressource honnête — `occupation_mesuree`
distingue « mesuré » de « non mesuré », `runs.vram_machine_*` et
`exclusif` disent ce qu'un run a coûté **et ce qu'on ne sait pas lui
attribuer**.

Aucune dépendance ouverte : tout est monté, testé, et sans consommateur.

**Critère de passage.** Une explication affichée cite la route qui l'a
produite ; une jauge de ressource n'affiche jamais un chiffre quand
`occupation_mesuree` est faux.

#### §15.6 — Skills & Memory UX — 🟡 partiellement bloqué

Invocation `@`, découverte et suggestion de skills, mémoire proposée puis
validée, provenance et contrôle utilisateur.

Le **contrôle mémoire** est bloqué par construction : `promouvoir` existe
à quatre niveaux et est testé, mais `backend/memory/routes.py` n'expose
que `search`, `graph`, `experiences`, `index`, `statistics` — **aucune
route de promotion** (**G-10**). L'utilisateur ne peut pas accepter un
souvenir parce qu'aucune API ne le lui permet.

Les **skills** : 9 routes, dont aucune ne **crée** un skill (G-5).

**Dépend de** : G-10 (§8), G-5 (§10).

#### §15.7 — Research / multimodal / voice — 🟠 dépend de §13

Recherche structurée multi-source, sources et citations, documents,
images, voix.

Aujourd'hui : un seul outil de recherche, `web_search`, un résultat
DuckDuckGo rendu dans la transcription. Il n'y a ni pipeline multi-source,
ni citations, ni synthèse. §13 est ⚪ *observation only*.

**Dépend de** : §13.

#### §15.8 — Collaboration avancée — 🟠 dépend de §7/§11

Sous-agents, relecteurs, multi-agent, conseil, supervision, fork
synchronisé. §11 est 🟡 avec `CollaborationEngine` non intégré (G-4, 10
routes sur 14 jamais appelées) ; §7 est 🟠.

**Ne pas commencer** avant que §7 et §11 aient tranché leur contrat — un
relecteur bâti sur une délégation non décidée hérite de son ambiguïté.

#### §15.9 — Advanced Assistant capabilities — 🟠 à décider au cas par cas

Réservé aux capacités dont l'analyse démontre une valeur **et** une
compatibilité. Le registre ci-dessous en retient quatre et en rejette
trois ; il n'est pas destiné à grossir sans preuve.

---

### Idées retenues — parce que Hermes peut les tenir et pas les autres

| Idée | Pourquoi elle est possible **ici** | Consomme | Où |
|---|---|---|---|
| **Réponse vérifiée** — « j'affirme avoir écrit X ; voici la preuve sur disque » | `mission/verification.py` compare le workspace avant/après et émet `mission.unverified`, et `verification_chat_tools` expose déjà deux exécuteurs au chat. La matière existe ; elle n'est pas à l'écran — ce que `ROADMAP.md` §C notait déjà le 2026-08-13. | §1, §2 | §15.5 |
| **Honnêteté de ressource** — « mesuré » / « non mesuré », jamais une jauge inventée | A-15 a rendu `occupation_mesuree` explicite ; R-6 distingue réservation, occupation machine et attribuabilité | §6 | §15.5 |
| **Lignée d'exécution lisible** — « pourquoi la tentative 1 a échoué » | le Ledger porte `parent`, `tentative`, `motif_de_reprise` depuis HOS-221 ; rien ne les affiche | §2 | §15.4 |
| **Mémoire à provenance visible** — pourquoi ce souvenir est digne de confiance | `Origine` et `ORIGINES_DE_CONFIANCE` existent ; la promotion n'est possible que par l'API locale | §8 | §15.6 |

### Idées rejetées — conservées pour ne pas les reproposer

| Idée | Décision | Raison |
|---|---|---|
| Canvas d'édition collaborative | **REJECT** | pas de CRDT, pas d'identité multi-utilisateur ; exigerait une autorité nouvelle pour un gain d'UX |
| Projets/sessions synchronisés entre appareils | **REJECT** | `utilisateur` vaut `"local"` et **n'est pas une identité vérifiée** — un test le garde. Sans authentification, la synchronisation serait une promesse fausse |
| Relecteur agentique séparé (*Auto Review*) **maintenant** | **DEFER → §15.8** | l'idée est bonne — séparer un jugement déterministe d'un relecteur agentique — mais §7 et §11 n'ont pas tranché leur contrat de délégation |

### Ce que §15 ne fera pas

Créer une `Session`, un `Projet`, un `Artefact` ou un `Worklog` comme
**nouvelle** source de vérité. Chacun de ces objets a déjà un propriétaire :
la session appartient à `conversation`, le projet à `ProjectStore`, la
trace au Run Ledger et au bus d'événements. Une seconde vérité produite
pour l'UX est exactement le défaut que §0 décrit.

---

# KNOWN OPEN GAPS

Chaque écart porte sa classe. **Dette actuelle et capacité future ne se
mélangent pas** : les premières se ferment, les secondes se décident.

| ID | Classe | Gap | Section | Preuve |
|---|---|---|---|---|
| ~~A-1~~ | **security** | ~~Deux chemins envoient un prompt cloud sans pare-feu~~ — **fermé HOS-255** | §4 | garde dans `OpenRouterClient`, liste blanche structurelle, 3 mutations |
| ~~**A-10**~~ | **security** | ~~Le pare-feu ignore `sk-or-v1-…`, le format de clé d'OpenRouter~~ — **fermé HOS-290** | §4 | était : `sk-…` → refusé, `sk-or-v1-…` → autorisé aux 8 placements. Motif élargi dans `audit_log`, prouvé à la socket : 0 requête émise |
| ~~A-2~~ | **security** | ~~HOS-217/218 livrés, testés, 0 appelant~~ — **fermé HOS-256** | §3 | câblés sur les coutures existantes, 6 mutations, garde structurelle des lanceurs |
| ~~A-3~~ | **functional** | ~~Points de reprise pris, jamais restaurables~~ — **fermé HOS-291** | §3 | relevé : `prendre` 1 appelant, `restaurer` 0, aucune route. Fermé par un chemin opérateur réel, gouverné par Aegis |
| A-22 | **security** | `ALLOWED_PATHS` n'est pas consulté pour une restauration | §3 | `data_migration` est `path_based: false` (mesuré HOS-291) ; le seul verrou est la validation humaine. Basculer la catégorie refuserait toute restauration d'instantané (`target_path=None` → `deny`) |
| A-23 | **architectural** | Le couple fichiers + état demande deux accords | §3 | empreintes `{checkpoint}` et `{snapshot}` distinctes ; non atteignable aujourd'hui, le seul producteur prend `avec_etat=False` |
| A-24 | **technical debt** | `prune_snapshots` et `StepCounter` sans appelant | §3 | 26 instantanés pour un `keep` de 20 ; le « tous les N pas » du §19.3 n'a jamais lieu |
| ~~A-19~~ | **test** | ~~`_RegistreMissions` hydrate sur un ordre non garanti~~ — **fermé HOS-262** | §3 | `ORDER BY cree_le DESC, rowid DESC` ; 0/20 → 5/20 avant, 25/25 après |
| ~~A-4~~ | **security** | ~~Portée projet MCP validée, non **autorisée**~~ — **fermé HOS-292** | §8/§10 | relevé : deux projets valides, `project_id=A` sur un chemin de B refusé, `project_id=None` **autorisé et le contenu rendu** ; 60 racines dans l'union sur la base réellement servie. Habilitation rendue **nominative** ; prédicat unique `authorized_root` ; 14 mutations |
| G-43 | **architectural** | Un chat lié à un projet est servi par le harnais : ses lectures passent par la frontière ACP et le hook `pre_tool_call`, **pas** par Aegis | §15/§16 | mesuré HOS-292 : aucun `chat servi en direct` journalisé, tour servi par ACP. HOS-292 décide *quel* workspace est remis à l'agent (`authorized_root`) ; l'intérieur relève de la boucle d'outils de l'agent, par construction |
| G-44 | **observability** | Aucun chip d'outil dans l'Assistant quand un projet est lié | §15 | `_repondre_par_le_harnais` n'émet que `{kind, text}`, jamais `tool_calls`. Rien n'est inventé côté frontend : trou d'observabilité, pas faux succès |
| A-26 | **technical debt** | `ensure_for_path` crée et valide un projet par objectif autonome, sans jamais en retirer | §8 | mesuré HOS-292 sur la base servie : 66 projets, 60 actifs+validés, la plupart vers des dossiers `pytest-of-Emeric` disparus. Sans conséquence d'accès depuis HOS-292 |
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
| G-10 | **architectural** | La promotion d'un souvenir n'a **aucune route HTTP** | §8 | `promouvoir` à 4 niveaux, testé ; `memory/routes.py` n'expose que search/graph/experiences/index/statistics |
| ~~**G-11**~~ | ~~technical debt~~ | ~~`assigned_tools` d'une tâche est planifié et **jamais invoqué**~~ — **fermé HOS-294** | §7 | invoquer réellement la recommandation violerait HOS-085 (agent) ou exigerait un second pont d'outils vers un catalogue disjoint (local) ; le rapport de mission ne la fait plus passer pour une mesure — `TaskExecution.tools_used`/`ExecutionReport.tools_used` viennent désormais de ce que `_run_tool_loop` a réellement invoqué, jamais de `assigned_tools` |
| ~~**G-12**~~ | ~~architectural~~ | ~~Le repli agentique défait **toutes** les décisions du routeur~~ — **fermé HOS-263** | §6/§7 | mesuré : 0 sur 5 avant, **5 sur 5** après ; un repli ne défait plus une décision sans porter une preuve qu'elle n'a pas |
| ~~**G-14**~~ | ~~architectural~~ | ~~La capacité agentique n'est mesurée pour aucun modèle du catalogue~~ — **fermé HOS-264** | §7 | 18 essais réels, 6 modèles, 6/6 prouvés ; chaîne magasin → prédicat → modèle engagé mesurée sur le vrai bootstrap. La sonde mesurait la convention de chemin et non le modèle : corrigée sur la formulation même de la production |
| ~~**G-15**~~ | ~~observability~~ | ~~Un verdict agentique est une mesure datée que rien ne réévalue~~ — **fermé HOS-293** | §6/§7 | même remède que le pont (§16) : le magasin indexe désormais chaque verdict sur l'empreinte (digest `/api/tags` + `num_ctx` du Modelfile) mesurée au moment de la sonde, et `measured_success_for` la revérifie à chaque lecture — un `ollama pull` ou un `num_ctx` édité sous le même tag rend le verdict `None` (non prouvé), jusqu'au prédicat de production et à `_agentic_model` |
| **G-16** | **technical debt** | 120 routes `/api/v1` sur 306 n'ont aucun appelant frontend | §15/§16 | mesuré le 2026-09-07, instrument corrigé deux fois ; gelé comme dette dans `test_pas_de_backend_orphelin.py`, qui interdit désormais d'en ajouter |
| **G-17** | **architectural** | Le pont négocie 12 surfaces qu'aucun service n'expose | §16 | **réduit de 17 à 12 par HOS-266** : sessions, tools, profiles, delegation et cron ont désormais route, client et UI. Restent chat/streaming, steering, approvals, skills, learning, MCP, browser, projects, config, insights |
| ~~**G-18**~~ | ~~architectural~~ | ~~L'autorité sur l'état de l'agent n'est pas tranchée~~ — **fermé HOS-267** | §16 | contrat établi par la mesure : l'agent est seul autorité sur `state.db`, Hermes OS demande et trace sa demande dans son propre bus. Une mutation additive intégrée de bout en bout, deux gardes structurelles, 10 mutations rouges |
| ~~**G-19**~~ | ~~technical debt~~ | ~~Le fork était déclaré absent sur la foi d'un nom~~ — **fermé HOS-268** | §16 | 206 méthodes relevées, matrice reconstruite (19/19), trois gardes interdisent qu'un nom inventé y rentre. Les deux absences restantes sont vérifiées contre le registre entier et portent leur preuve |
| **G-20** | **architectural** | Le pont expose 19 surfaces exactes dont **12** sans consommateur | §16 | **réduit de 14 à 12 par HOS-269** : lecture et renommage d'une session sont intégrés. Deux candidates écartées par la mesure — `delegation.pause` est process-local, le lancement de subagent n'a pas de RPC. `groups` attend un endpoint configuré |
| ~~**G-22**~~ | ~~architectural~~ | ~~Trois capacités attendent le chat~~ — **partiellement fermé HOS-271** | §16 | le chat interactif **existait déjà**, par ACP, et était injoignable : sa sonde de disponibilité bloquait la boucle du serveur qu'elle interrogeait. Corrigé — les permissions d'édition ACP sont désormais un producteur réel, tracé et affiché. Les trois capacités **du gateway** restent hors d'atteinte : le chat passe par ACP, elles vivent dans le gateway |
| ~~**G-24**~~ | ~~functional~~ | ~~Le contrôle natif d'ACP n'est pas émis~~ — **fermé HOS-273** | §16 | `session/cancel` émis et démontré : 50 s/9898 car. sans annulation, 12 s/0 car. avec, 195 s avec un **mauvais** identifiant — réel et corrélé. Deux faux contrôles déjà livrés corrigés au passage : `POST /cancel` ne touchait pas le tour, et le bouton stop n'abandonnait que le `fetch` |
| **G-25** | **functional** | Le steering n'a aucun mécanisme d'injection dans un tour actif | §16 | ACP n'offre que « annuler puis redemander » — le serveur garde `interrupted_prompt_text` et le rattache au tour suivant. C'est un geste produit distinct, à concevoir comme tel plutôt qu'à maquiller en steering. **DEFER** |
| **G-23** | **architectural** | Deux transports agentiques coexistent sans passerelle — **convergence REJECT (HOS-272)** | §16 | les deux **partagent le magasin** : un identifiant ACP est repris par `session.resume`. Mais `resume` matérialise une **seconde session vivante** dans le processus Gateway : mesuré pendant un tour ACP réel, `session.steer` rend `queued` et `session.interrupt` rend `interrupted` **sans toucher le tour**, qui se termine normalement. Convergence rejetée : elle fabrique des succès HTTP confiants qui n'agissent sur rien. Le chemin réel est le contrôle natif d'ACP (`acp_adapter/server.py: cancel`), non émis par notre client |
| **G-21** | **architectural** | La mémoire de l'agent échappe à la provenance Hermes OS | §8/§16 | aucune méthode `memory.*` dans les 206 ; la capacité vit dans `tools/memory_tool.py`, côté agent. Hermes OS ne peut donc lui appliquer ni provenance, ni quarantaine, ni promotion — et fabriquer une API serait ce que G-19 interdit |
| G-13 | **technical debt** | Deux dimensions sur cinq du score modèle sont inertes | §6 | `_get_records_for_task` rend `[]` en dur ; `_compute_speed_score` rend 0,000 pour les six profils |

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

**Prochain identifiant libre : `T-30`.**

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
| **T-27** | — | A-10 — motifs de détection du pare-feu | **tranché ADAPT (HOS-290)** | il ignorait le format de clé de son propre fournisseur | motif élargi **dans le scanner existant**, segments de fournisseur bornés, plancher d'entropie de 16 conservé : 7 textes légitimes vérifiés non bloquants | §4 | 🟢 fermé |
| T-24 | 2026-09-04 | A-2 — contrôles de sécurité non câblés | **ADOPT** | les deux invariants étaient réels *et* non couverts par ailleurs | câblés sur les coutures existantes, aucune politique nouvelle | HOS-256 | 🟢 appliqué |
| **T-25** | 2026-09-11 | A-3 — restauration des points de reprise | **ADOPT (HOS-291)** | on prenait ce qu'on ne savait pas rendre, et le filet était *visible* — donc on comptait dessus | exposer : l'appelant naturel existait déjà (panneau « Points de reprise »), aucune couche nouvelle, Aegis inchangé. Aperçu non destructif, accord humain nommant le point de reprise, restauration prouvée au navigateur puis après redémarrage | §3 | 🟢 appliqué |
| **T-26** | 2026-09-11 | A-4 — habilitation de portée projet | **tranché ADAPT (HOS-292)** | l'isolation reposait sur la bonne foi du modèle *et* sur une union : ne nommer aucun projet donnait accès à tous | habilitation **nominative** — une racine ne s'accorde qu'à l'action qui nomme son projet, et seulement tant qu'il est actif et validé. Liste blanche statique inchangée, aucune autorité nouvelle : le prédicat des trois copies est consolidé dans `authorized_root` | §8 | 🟢 appliqué |
| **T-28** | — | §15.1 — Chat et Cowork : deux surfaces ou deux modes ? | **ouvert** | les deux partagent déjà le Run Ledger et le bus ; les séparer ferait deux histoires pour une exécution | trancher **avant** toute ligne de §15 | §15 | 🟠 à décider |
| T-22 | 2026-09-05 | §6.1 — autorité d'ordonnancement | **ADAPT** | l'architecture existante suffisait : deux routeurs sur deux chemins disjoints, `ResourceManager` fournissant le plafond. Aucun ordonnanceur n'était requis | retirer la troisième estimation de capacité, laisser les autorités en place | HOS-262 | 🟢 appliqué |
| T-29 | 2026-09-06 | G-12 — un modèle non sondé peut-il piloter la boucle ? | **ADAPT** | la question était mal posée : le repli n'est pas mieux prouvé que ce qu'il remplace, donc la substitution n'arbitrait rien. Sonder reste souhaitable (G-14) mais n'était pas requis pour rendre la décision contraignante | un repli ne défait une décision que s'il porte une preuve qu'elle n'a pas ; prédicat tri-état | HOS-263 | 🟢 appliqué |

### Décisions de rejet conservées

| Sujet | Décision | Raison — conservée pour ne pas la reproposer |
|---|---|---|
| Table `run_events` (archive Agent OS) | **REJECT** | Hermes a déjà un bus durable, rejouable, à identifiants idempotents ; en porter un second ferait deux magasins d'événements |
| Couche SQLite propre au Ledger | **REJECT** | `DatabaseManager` et `MigrationManager` existent ; les doubler ferait une troisième couche |
| Fusion `ModelRouter` / `AdaptiveModelRouter` | **REJECT** (T/P-4) | spécialisés sur des chemins de production distincts ; l'arbitrage tranche la précédence |
| `approval_engine` branché en parallèle d'Aegis | **REJECT** | deux portes vivantes valent moins qu'une |
| Reconstruction d'une `Mission` depuis un `Run` | **REJECT** | produirait une mission plausible et fausse — la famille de défaut la plus coûteuse du projet |
| Import de `AgentGateway` (Autonomous OS) | **OBSERVE** | référence architecturale ; rien n'indique que Hermes OS doive reproduire cette structure |
| Canvas d'édition collaborative (§15) | **REJECT** | pas de CRDT ni d'identité multi-utilisateur ; exigerait une autorité nouvelle pour un gain d'UX |
| Projets/sessions synchronisés entre appareils (§15) | **REJECT** | `utilisateur` vaut `"local"` et n'est pas une identité vérifiée — un test le garde |
| Relecteur agentique séparé, *Auto Review* (§15) | **DEFER → §15.8** | l'idée tient ; §7 et §11 n'ont pas tranché leur contrat de délégation |

---

## Journal des mises à jour de cette roadmap

| Date | Baseline | Changement |
|---|---|---|
| 2026-09-04 | `528a0d3` | Création. §3 et §4 rétrogradées 🟡 sur les mesures de l'audit J25, contre le statut 🟢 attendu par le cahier. Registre ouvert à T-22. |
| 2026-09-05 | `04624ae` | §6.1 passée 🟡 sur mesure : le routeur classait juste et n'était jamais écouté. T-22 tranché (ADAPT) — l'architecture suffisait. A-19 fermé en chemin, cette passe le faisant sortir. G-12 et G-13 ouverts. |
| 2026-09-05 | `6dfa78a` | §15 créée — couche produit consommant §1→§13, aucune autorité nouvelle. Deux écarts relevés en la construisant (G-10, G-11), une décision ouverte (T-28), trois idées rejetées avec leur raison. §15 **ne devient pas la section active** : §6.1 et A-10 la précèdent. |
| 2026-09-06 | `0d2b9e1` | §6.1 passée 🟢 : G-12 fermé sur le chemin agentique réel — 0 décision sur 5 survivait, 5 sur 5 survivent. T-29 tranché (ADAPT) : le repli n'était pas mieux prouvé que ce qu'il remplaçait, donc la substitution n'arbitrait rien. G-14 ouvert en chemin — la cause de G-12 était un magasin de sondes écrit dans `%TEMP%` depuis toujours, et effacé. |
| 2026-09-06 | `a102d54` | G-14 fermé : le catalogue est sondé pour de vrai — 18 essais, 6 modèles, 6/6 prouvés capables, chaîne complète mesurée du magasin jusqu'au modèle engagé. La sonde mesurait « ce modèle devine-t-il la convention de chemin » et non sa capacité agentique ; corrigée sur la formulation de la production. G-15 ouvert en chemin. §6.1 reste 🟢, sur une base désormais mesurée plutôt que supposée. |
| 2026-09-07 | `116f603` | §16 créée — le pont Hermes Agent, infrastructure transverse sans autorité nouvelle. Agent migré 0.20.0 → 0.21.0 (31 918 commits, état persistant intact, suite inchangée). Capacités **négociées** contre le gateway et non déclarées : 54 méthodes présentes, 8 absentes, 15 surfaces complètes sur 18. Une seule chaîne complète jusqu'au frontend ; les autres restent PLANNED. Règle anti-orphelin posée : 120 routes sur 306 sans appelant frontend, gelées comme dette. G-16 et G-17 ouverts en chemin. |
| 2026-09-09 | `e2d66f9` | §16 avance : le pont sait **demander** et non plus seulement négocier — une connexion vivante, des réponses corrélées, des événements collectés. Cinq surfaces passent de « négociée » à **démontrée** en lecture : sessions (200), toolsets (62, dont 8 actifs), profils, délégation, routines, servies par une route unique et un Center « Cerveau ». Tout ce qui écrit dans l'état de l'agent reste PLANNED : G-18 ouvert, G-17 réduit de 17 à 12. |
| 2026-09-09 | `e5928f3` | **G-18 fermé.** Contrat d'autorité établi par la mesure : `session.resume` n'écrit rien (activation, handle éphémère), `session.branch` écrit additivement. Hermes OS demande au propriétaire et trace sa demande dans son propre bus — jamais dans `state.db`. Une mutation intégrée de bout en bout, clic réel vérifié. Le fork existait sous le nom `session.branch` : 16 surfaces sur 18. G-19 ouvert. |
| 2026-09-09 | `91c1424` | **G-19 fermé.** Relevé du registre réel : 206 méthodes contre 62 sondées, et les trois surfaces « absentes » l'étaient sur des noms inventés. Matrice reconstruite depuis le runtime — 19 surfaces, 19 complètes — et `SANS_RPC` distingue « le runtime ne sait pas » de « le runtime ne nous laisse pas demander ». Relevé versé au dépôt, daté et empreint ; trois gardes empêchent qu'un nom inventé y rentre. G-20 ouvert : 14 surfaces exactes et sans consommateur. |
| 2026-09-09 | `4afc77c` | **G-20 avancé.** Deux tranches verticales intégrées — lire et renommer une session — et **deux écartées par la mesure** : `delegation.pause` est un global du processus gateway (pause posée dans une connexion, `False` lue dans une autre), et rien ne lance un subagent par RPC. Correction d'une preuve de HOS-267 : le md5 de `state.db` est un signal suffisant mais non nécessaire, l'écriture pouvant vivre dans le WAL — la preuve fiable est la relecture par un processus neuf. G-21 ouvert sur la mémoire. |
| 2026-09-09 | `6f9a363` | **Approbations écartées, toolsets intégrés.** Les trois méthodes d'approbation répondent, mais la file est en mémoire et bloque un fil de l'agent : les missions prennent le mode déterministe (`HERMES_SINGLE_QUERY_SESSION`, posé par le CLI lui-même) et le pont ne lance aucun tour — un panneau serait vide par construction. `tools.configure` en revanche écrit `config.yaml`, que tous les processus agent relisent : bascule intégrée de bout en bout, clic réel vérifié. Une fausse alerte de perte de config corrigée par comparaison de structures, et une course sur la découverte des plugins mesurée puis affichée comme refus. G-22 ouvert. |
| 2026-09-09 | `4b4c022` | **G-22 partiellement fermé.** Le chat interactif existait déjà — session Hermes Agent vivante par ACP — et il était **injoignable depuis l'Assistant** : `harnais.disponible()` sonde le backend par un `requests.get` synchrone sur son propre `/health`, ce qui bloque la boucle d'un uvicorn mono-worker. Le serveur se demandait s'il était vivant pendant qu'il servait la requête qui posait la question. Déportée hors de la boucle, la signature du flux passe de `tool_calls` à `thinking` — le harnais est emprunté. Les permissions d'édition ACP, qui refusaient déjà vraiment (3 refus sur un tour réel) sans aucun témoin, sont tracées et affichées. G-23 ouvert : deux transports agentiques sans passerelle. |
| 2026-09-09 | `d28ccf0` | **G-23 tranché : REJECT.** ACP et Gateway partagent `state.db` — un identifiant ACP est repris par le Gateway — mais la reprise crée une **seconde session vivante** dans son propre processus. Mesuré pendant un tour ACP réel (3242 fragments, fichier écrit) : `session.steer` → `queued`, `session.interrupt` → `interrupted`, et le tour se termine normalement. Une ligne stockée, deux sessions vivantes, deux processus. Convergence rejetée plutôt que différée : elle produit exactement le faux succès que ce dépôt poursuit depuis l'origine. Aucune fonctionnalité livrée — une garde en quatre tests fixe la ligne : le contrat de mutation ne porte que sur de l'état **stocké**, jamais sur un tour vivant. |
| 2026-09-09 | `459b8ea` | **G-24 fermé — interruption ADOPT.** `session/cancel` d'ACP atteint le tour vivant : 50 s/9898 car. sans annulation, 12 s/0 car. avec, et 195 s avec un mauvais identifiant — donc réel *et* corrélé. De bout en bout par HTTP : 217 s → 17 s. Deux faux contrôles **déjà livrés** corrigés : `POST /conversation/{id}/cancel` marquait la conversation sans toucher le tour, et le bouton stop n'abandonnait que le `fetch` pendant que l'agent continuait d'écrire. Steering **DEFER** (aucune injection dans un tour actif), approvals Gateway **REJECT** (G-23), permissions ACP **ADOPT** (HOS-271). G-25 ouvert. |
