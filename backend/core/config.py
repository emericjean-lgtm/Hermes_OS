"""Central configuration loading: .env via pydantic-settings, plus the
models.yaml / agents.yaml catalogues. Nothing else in the codebase should
read os.environ or parse these YAML files directly.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/core/config.py -> backend/core -> backend -> repo root.
_PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Deliberately NOT named OLLAMA_HOST: that name is Ollama's own env var
    # for the *server's* bind address (format "host:port", no scheme — e.g.
    # set by the Windows installer or by anyone exposing Ollama on the
    # LAN). If both this app and Ollama read OLLAMA_HOST, whichever the OS
    # environment has set for Ollama silently wins over .env (env vars
    # outrank .env files in pydantic-settings), and the app tries to
    # connect to a schemeless address. OLLAMA_API_URL avoids the collision.
    ollama_api_url: str = "http://127.0.0.1:11434"

    @field_validator("ollama_api_url")
    @classmethod
    def _ollama_api_url_must_have_scheme(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError(
                "OLLAMA_API_URL is empty. Check your .env file — this "
                "usually means the OLLAMA_API_URL=http://127.0.0.1:11434 "
                "line got lost or corrupted while editing (e.g. saved with "
                "the wrong encoding). Compare against .env.example."
            )
        if not (value.startswith("http://") or value.startswith("https://")):
            raise ValueError(
                f"OLLAMA_API_URL={value!r} is missing 'http://' or "
                "'https://'. It should look like "
                "OLLAMA_API_URL=http://127.0.0.1:11434"
            )
        return value

    # ── OPENROUTER (HOS-066C) ───────────────────────────────────────
    # Empty (the default) keeps Hermes 100% local — cloud escalation is only
    # wired at bootstrap when this is set (see service_registry.py's
    # _wire_cloud_escalation). Only OpenRouter's free (":free", zero-priced)
    # models are ever used — see backend/model_intelligence/cloud_catalog.py.
    openrouter_api_key: str = ""
    # Requests held back from the automatic escalation path, out of
    # OpenRouter's shared daily free-tier quota (50, or 1000 with >=$10
    # lifetime account credit) — a safety margin so a burst of low-value
    # tasks can't silently exhaust the day's budget. 0 uses the full quota.
    openrouter_daily_reserve: int = 5

    ollama_keep_alive: str = "10m"
    # Floor applied whenever a caller doesn't pass num_ctx explicitly (see
    # backend/connectors/ollama_client.py DEFAULT_NUM_CTX). Ollama's own
    # default (4096, sometimes 2048 per-Modelfile) silently truncates
    # longer prompts from the front — confirmed via scripts/validation/
    # bench_context.py's needle-in-a-haystack probe.
    ollama_num_ctx: int = 8192

    backend_host: str = "0.0.0.0"
    backend_port: int = 8000
    secret_key: str = "change_me_with_a_random_256bit_key"

    chroma_path: str = "./data/db/chroma"
    sqlite_path: str = "./data/db/hermes.db"
    workflows_dir: str = "./data/workflows"
    # Snapshots (§19.3). snapshot_every_steps <= 0 disables automatic
    # ones; snapshot_keep bounds the directory, since §3.7 budgets only
    # ~2-5 GB for logs and snapshots together.
    logs_dir: str = "./data/logs"
    snapshot_dir: str = "./data/snapshots"
    snapshot_every_steps: int = 10
    snapshot_keep: int = 20
    # Max workflow nodes executed concurrently (§6: parallélisation).
    # Bounded, and deliberately small: workflow nodes call LLM-backed
    # tools, so an unbounded fan-out would ask Ollama to hold several
    # models at once and thrash a 16 GB VRAM budget — turning a
    # parallelism win into a swapping loss. Set to 1 for the previous
    # strictly-sequential behaviour.
    workflow_max_parallel: int = 4
    # Same VRAM concern as workflow_max_parallel above, but deliberately
    # its own, smaller setting (HOS-068) rather than reusing that one:
    # mission DAG nodes can each recommend a *different* full-size role
    # model (config/models.yaml — several already measured at 12-15GB on
    # this ~17.16GB card, see HOS-065C's real benchmark data), which is a
    # heavier VRAM footprint per concurrent task than a workflow's
    # lighter-weight tool calls. 2 is the conservative default; raise it
    # only on a card with real headroom to spare.
    mission_max_parallel_tasks: int = 2

    # Tours d'inférence-plus-outils qu'un *nœud de mission* peut consommer
    # avant qu'on force une réponse finale sans outils (HOS-118).
    #
    # Valait 3, en dur, aligné sur `agents/base_agent.py`. Ce chiffre est
    # juste pour un tour de conversation : il empêche un modèle qui redemande
    # des outils sans jamais répondre de bloquer le chat.
    #
    # Il est faux pour une tâche de mission. Lire quatre fichiers, en écrire
    # deux, lancer les tests et corriger, c'est déjà six ou sept tours : au
    # quatrième, l'exécuteur coupait et forçait une réponse sans outils. La
    # tâche ne pouvait donc pas *finir* — elle rapportait ce qu'elle avait pu.
    #
    # 12 n'est pas une mesure, c'est une marge : assez pour un aller-retour
    # écriture/vérification/correction, assez bas pour qu'une boucle folle
    # coûte des minutes et non des heures. À corriger dès qu'on aura mesuré
    # combien de tours une vraie tâche consomme.
    mission_max_tool_rounds: int = 12

    # Hard whitelist Aegis enforces for every file_read/file_write/git_*
    # action (§17.1) — AegisEngine._is_within_whitelist() denies everything
    # when this is empty, which is the *safe* failure mode for an unknown
    # deployment but a silent trap for this one: with no ALLOWED_PATHS in
    # .env, /files and /git/* 403 even against Hermes's own repository,
    # breaking the KlaatCode/OhMyPi pipelines that operate on it. Defaulting
    # to the project's own root fixes that self-hosted case out of the box;
    # anyone who sets ALLOWED_PATHS in .env still fully overrides this
    # (pydantic-settings: env var beats class default), so a deployment
    # that intentionally wants a narrower or different whitelist is
    # unaffected.
    allowed_paths: str = str(_PROJECT_ROOT)
    max_file_size_mb: int = 50

    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    gpu_vram_total_gb: float = 16.0
    gpu_alert_temp_c: float = 85.0
    gpu_critical_temp_c: float = 90.0
    gpu_vram_warning_pct: float = 85.0

    skill_auto_validate_threshold: float = 0.95
    skill_min_confidence: float = 0.30
    reflection_enabled: bool = False
    ebbinghaus_decay_enabled: bool = False

    models_config_path: str = "./config/models.yaml"
    agents_config_path: str = "./config/agents.yaml"
    security_config_path: str = "./config/security.yaml"

    @property
    def allowed_paths_list(self) -> list[str]:
        return [p.strip() for p in self.allowed_paths.split(",") if p.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


def _load_yaml(path: str) -> dict[str, Any]:
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(
            f"Config file not found: {file_path}. "
            "Check MODELS_CONFIG_PATH / AGENTS_CONFIG_PATH in your .env."
        )
    with file_path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


@lru_cache
def load_models_config() -> dict[str, Any]:
    return _load_yaml(get_settings().models_config_path)


@lru_cache
def load_agents_config() -> dict[str, Any]:
    return _load_yaml(get_settings().agents_config_path)


@lru_cache
def load_security_config() -> dict[str, Any]:
    return _load_yaml(get_settings().security_config_path)
