# Observateur de cycle de vie des Skills — contrat mesuré (G-28, HOS-276)

**Ce plugin est installé et actif** depuis G-33 (2026-09-10), sous
`%LOCALAPPDATA%\hermes\plugins\hermes-os-observateur-skills`, activé par
`plugins.enabled`. Ce répertoire en reste la source : l'installation en est
une copie, et une correction se fait ici puis se réinstalle.

Les deux préalables que G-28 avait posés sont levés — G-32 a établi la
relation `turnId → run_id`, et `backend/skills/observations.py` la lit.

---

## La décision

| objet | verdict |
|---|---|
| le point d'observation `on_skill_lifecycle` et son propriétaire | **ADOPT** (G-28) |
| l'installation du plugin dans l'agent réel | **ADOPT** (G-33) |

La règle du brief était : *ne pas construire le lifecycle avant d'avoir
prouvé que son point d'observation et son propriétaire sont
architecturalement légitimes.* La preuve est faite. L'installation attend
deux choses que la preuve ne donne pas.

### Pourquoi ADOPT sur la légitimité

L'observateur ne peut pas devenir une autorité — **par construction du
hook, pas par discipline**. `_emit_skill_lifecycle` ignore la valeur de
retour, et chaque callback est isolée. Mesuré sur un `HERMES_HOME` de
substitution :

    plugin absent      non chargé   has_hook=False   mutation OK, enregistrement natif écrit
    plugin désactivé   chargé       has_hook=False   mutation OK, enregistrement natif écrit
    callback qui lève  chargé       has_hook=True    mutation OK, enregistrement natif écrit

L'agent reste propriétaire du contenu et du cycle natif dans les trois cas.

### Pourquoi DEFER sur l'installation

**Il n'y a pas de consommateur.** G-27 a livré la lecture de provenance ;
rien dans Hermes OS ne montre encore une relation Run ↔ Skill. Installer
l'observateur aujourd'hui produirait un fichier d'état qui grossit et que
personne ne lit — un producteur sans lecteur, exactement le défaut que ce
dépôt passe son temps à défaire.

**Les internes de l'agent changent dans quatre jours.**
`plugin_compat.COMPAT_REMOVAL_DATE = 2026-09-14` : à cette date, tout
plugin externe important un module interne est *désactivé*. Ce plugin-ci
n'en importe aucun — `scan_plugin()` rend « aucun » — donc il survit. Mais
la mise à jour qui accompagne ce retrait n'a pas été mesurée, et installer
la veille d'un changement structurel, c'est se donner un premier suspect
au prochain incident.

**Préalables, dans cet ordre :**

1. une surface produit Hermes OS qui *lit* la relation Run ↔ Skill ;
2. le runtime post-2026-09-14 mesuré, et `scan_plugin()` rejoué dessus.

---

## Le contrat, mesuré sur v0.21.0 le 2026-09-10

### Ce que l'agent livre à chaque événement

    action                    created | edited | patched | installed | loaded
    skill_name                le nom local, NON anonymisé
    provenance                installed | agent_created | external | local | unknown
    task_id                   str, parfois ""
    session_id                str, parfois ""
    use_count                 int | None
    reused                    bool | None
    reuse_after_patch         bool | None
    telemetry_schema_version  "hermes.observer.v1"

Relevé réel de la démonstration — trois mutations, trois faits reçus :

    created  g28-premier-plan   task='tache-77'  session='sess-xyz'  provenance='local'
    created  g28-revue-de-fond  task='tache-77'  session='sess-xyz'  provenance='agent_created'
    patched  g28-premier-plan   task='tache-88'  session='sess-xyz'  provenance='local'

`task_id` **diffère d'une mutation à l'autre**. C'est précisément la clef
de jointure qui manquait à G-27, et qu'aucun magasin natif ne persiste.

### L'identité est parfois partielle

`agent/skill_commands.py` appelle `bump_use(skill_name, task_id=task_id)`
**sans** `session_id`, et `_emit_skill_lifecycle` le rend alors `""`. Un
fait peut donc arriver sans session. Le plugin le note tel quel : compléter
serait fabriquer la corrélation que G-27 a refusé d'inventer.

### Fréquence

`loaded` part à **chaque invocation de Skill** — `skill_commands`,
`skills_tool`, `cron/scheduler_prompt`. Les quatre autres sont des
mutations, donc rares. Le plugin ne retient que les mutations : `PluginState`
est plafonné à 10 Mio, et un observateur qui remplirait son quota cesserait
d'observer sans le dire.

### Où l'état vit

`ctx.state` écrit
`HERMES_HOME/plugin-data/agent-plugin-<nom>-<empreinte>/state.json` —
atomique, sous verrou inter-processus, plafonné. Mesuré : trois faits
relus intégralement par un **nouveau processus**.

Hermes OS lirait ce fichier comme il lit déjà `.usage.json` et
`.bundled_manifest` (HOS-274, HOS-275) : en lecture, sans en être
propriétaire, et sans que le backend ait besoin de tourner au moment de
l'événement.

### Installation, si le jour vient

    HERMES_HOME/plugins/hermes-os-observateur-skills/{plugin.yaml,__init__.py}
    config.yaml:  plugins.enabled += hermes-os-observateur-skills

Puis `discover_plugins(force=True)`, ou un redémarrage de l'agent.

---

## Ce que ce contrat ne permet toujours pas

Rattacher une Skill à une **Mission** ou à un **Run** de Hermes OS. Le
`task_id` que l'agent livre est celui de *sa* tâche, pas d'un Run du Ledger.
Les relier demanderait que Hermes OS sache quel `task_id` d'agent
correspond à quel Run — une correspondance qui n'existe nulle part
aujourd'hui, et qui est le sujet suivant, pas celui-ci.
