"""GET /system/status — hardware/process telemetry (cahier des charges
§21): which agents/models are configured, plus real GPU/CPU/RAM/disk
readings and currently-loaded Ollama models via monitoring/gpu_monitor.py.

GPU telemetry degrades to `"gpu": null` when `rocm-smi` isn't available
(no ROCm/AMD GPU on this machine — including this sandbox, see README's
"Important" note) rather than failing the whole endpoint; same for
loaded-model info if Ollama itself is unreachable (see GpuMonitor.snapshot).
"""
from __future__ import annotations

from fastapi import APIRouter

from backend.core.agent_registry import get_agent_registry
from backend.core.config import load_models_config
from backend.monitoring.gpu_monitor import get_gpu_monitor

router = APIRouter()


@router.get("/system/status")
async def system_status() -> dict:
    registry = get_agent_registry()
    models_config = load_models_config()
    snapshot = await get_gpu_monitor().snapshot()
    return {
        "enabled_agents": registry.list_enabled(),
        "configured_roles": sorted(models_config["roles"]),
        **snapshot.to_dict(),
    }


@router.get("/system/harnais")
def system_harnais() -> dict:  # noqa: ASYNC - voir la note ci-dessous
    """L'état du harnais Hermes Agent (HOS-138).

    Le harnais est le mode normal : une session d'agent tenue ouverte pour
    toute la durée d'une mission. Quand ses prérequis manquent, chaque tâche
    retombe sur un agent jeté après usage — donc amnésique.

    D'où cette route. La dégradation est réelle et **invisible dans le
    résultat d'une mission**, qui a exactement la même forme dans les deux
    modes : rien, dans un rapport, ne dit si l'agent gardait le contexte de
    la tâche précédente ou le découvrait. L'opérateur doit pouvoir le voir
    sans lire les journaux, et savoir **lequel** des prérequis manque.

    Le cas le plus fréquent, mesuré, est un backend éteint : l'agent
    rappelle Hermes OS par MCP pour obtenir ses outils, et démarre sans
    aucun outil quand il ne le trouve pas.

    **Déclarée `def` et non `async def`, et c'est indispensable.** La
    vérification sonde le backend en HTTP, de façon bloquante. Dans un
    handler `async`, cet appel gèle la boucle même qui devrait répondre à
    la sous-requête : mesuré, la route rendait
    `backend_joignable: false (ReadTimeout)` — le backend se déclarait
    éteint dans une réponse qu'il venait lui-même de produire. En `def`,
    FastAPI exécute le handler dans un threadpool et la boucle reste libre.
    """
    from backend.execution.task_executor import _harnais_par_defaut
    from backend.ral.adapters.prerequis_harnais import verifier
    from backend.ral.adapters.sessions_de_mission import registre

    etat = verifier()
    sessions = registre()
    return {
        "actif": _harnais_par_defaut(),
        "pret": etat.pret,
        "explication": etat.explication(),
        "prerequis": {
            "agent_installe": etat.agent_installe,
            "backend_joignable": etat.backend_joignable,
            "mcp_declare": etat.mcp_declare,
        },
        "sessions_ouvertes": sessions.sessions_ouvertes(),
    }


@router.get("/system/models")
async def system_models() -> dict:
    """The role → model table (§21) crossed with what Ollama is actually
    holding right now (§22).

    /system/status already reports `configured_roles`, but only as bare
    role *names* — which cannot answer the two questions that matter when
    a 16 GB budget is the constraint: which model does this role use, and
    is it resident? This joins config/models.yaml against Ollama's live
    list so `always_loaded` can be seen to be working (or not) rather
    than taken on trust.

    `loaded` et `installe` sont deux questions distinctes, et les confondre
    coûte cher (HOS-139). Un rôle dont le modèle a été supprimé d'Ollama
    affichait `loaded: false` — indiscernable d'un modèle simplement non
    résident, ce qui est le cas **normal** ici : `OLLAMA_MAX_LOADED_MODELS`
    vaut 1 sur cette machine, donc tous les rôles sauf un sont
    légitimement `loaded: false`. Le rôle `standard` est ainsi resté cassé
    sans que rien ne le signale, jusqu'à ce qu'une mission le sollicite et
    reçoive un 404.
    """
    config = load_models_config()
    # snapshot() is the monitor's public API; _read_loaded_models is
    # private and would couple this route to its internals.
    snapshot = await get_gpu_monitor().snapshot()
    loaded = {m.get("name", "") for m in snapshot.loaded_models}
    installes = await _modeles_installes()

    def _is_loaded(tag: str) -> bool:
        # Ollama reports "qwen3:1.7b" as "qwen3:1.7b" but a tagless
        # reference as "<name>:latest", so compare both ways rather than
        # reporting a resident model as absent on a naming technicality.
        return tag in loaded or f"{tag}:latest" in loaded

    roles = []
    for name, spec in (config.get("roles") or {}).items():
        tag = spec.get("model", "")
        roles.append(
            {
                "role": name,
                "model": tag,
                "tier": spec.get("tier", ""),
                "vram_gb": spec.get("vram_gb"),
                "always_loaded": bool(spec.get("always_loaded")),
                "loaded": _is_loaded(tag),
                # `None` quand Ollama est injoignable : « on ne sait pas »
                # n'est pas « absent », et afficher un rôle comme cassé
                # parce qu'on n'a pas pu demander serait un faux négatif.
                "installe": (None if installes is None
                             else _est_installe(tag, installes)),
                # HOS-075: the Assistant's manual model picker shows this
                # verbatim rather than inventing its own blurb per role.
                "description": (spec.get("description") or "").strip(),
            }
        )

    roles.sort(key=lambda r: (not r["always_loaded"], not r["loaded"], r["role"]))
    return {
        "roles": roles,
        "loaded_count": len(loaded),
        "always_loaded_count": sum(1 for r in roles if r["always_loaded"]),
        # Le chiffre qu'un opérateur doit voir en premier : un rôle sans
        # modèle installé échouera à la première mission qui l'emploie.
        "roles_sans_modele": sorted(r["role"] for r in roles
                                    if r["installe"] is False),
    }


def _est_installe(tag: str, installes: set) -> bool:
    """Même tolérance de nommage que `_is_loaded` : Ollama rend
    `<nom>:latest` pour une référence sans tag."""
    return tag in installes or f"{tag}:latest" in installes


async def _modeles_installes():
    """Ce qu'Ollama détient sur le disque, ou `None` s'il est injoignable."""
    from backend.connectors.ollama_client import OllamaClient
    from backend.core.config import get_settings

    client = OllamaClient(get_settings().ollama_api_url, timeout=10.0)
    try:
        return {m.get("name", "") for m in await client.list_local_models()}
    except Exception:  # noqa: BLE001 - ne pas faire echouer toute la route
        return None
    finally:
        try:
            await client.aclose()
        except Exception:  # pragma: no cover - fermeture au mieux
            pass
