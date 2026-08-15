"""Spike: can Hermes OS drive Hermes Agent over ACP with a live session?

Proves or refutes, before any adapter rewrite:
  1. spawn hermes-acp and complete the ACP handshake
  2. create a session bound to a workspace
  3. send a prompt and receive streamed updates
  4. verify a REAL artifact on disk (never the agent's own account)
  5. reuse the SAME session for a second prompt   <- impossible with the CLI
"""
from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from pathlib import Path

import logging
logging.basicConfig(level=logging.DEBUG, stream=__import__('sys').stderr)
import acp
from acp.schema import (
    ClientCapabilities,
    FileSystemCapabilities,
    Implementation,
    TextContentBlock,
)

HERMES_HOME = r"C:\Users\emeri\AppData\Local\hermes"
ACP_EXE = r"C:\Users\emeri\AppData\Local\hermes\hermes-agent\venv\Scripts\hermes-acp.exe"
#: Le plus petit modele du catalogue qui tient une boucle d'outils
#: (agentique 100/100, HOS-108). Renomme en `-125k` pendant la refonte du
#: catalogue : l'ancien `-128k` reste offert par l'agent mais n'existe plus
#: cote Ollama, et c'est ce fantome qui repondait `HTTP 404`.
MODEL = "lfm2.5-2.6b-125k"

#: Le blocage connu ne rend jamais la main — teste jusqu'a 900 s le
#: 2026-08-13. Une borne courte ne perd donc aucune information et rend le
#: spike rejouable en boucle courte.
PROMPT_TIMEOUT_S = 180.0

#: Le temoin ne demande qu'un mot : s'il n'a pas abouti en une minute, ce
#: n'est deja plus une question de lenteur.
SANS_OUTIL_TIMEOUT_S = 60.0


def _tag_de(model_id: str) -> str:
    """Le tag Ollama derriere un identifiant de modele de l'agent.

    Deux formes coexistent dans la liste que la session renvoie :
        custom:lfm2.5-2.6b-128k
        custom:local-(127.0.0.1:11434):lfm2.5-2.6b-125k:latest

    Decouper naivement sur « : » donne « local-(127.0.0.1 » — l'hote et le
    port en contiennent. On coupe donc apres le dernier « ): », et on
    retire le seul suffixe « :latest » : un tag peut legitimement porter un
    deux-points (`qwen3-embedding:0.6b`).
    """
    reste = model_id.split("):", 1)[-1] if "):" in model_id else model_id.split("custom:", 1)[-1]
    return reste.removesuffix(":latest")


def _tags_ollama() -> set[str]:
    """Les tags qu'Ollama sert reellement, sans le suffixe `:latest`.

    Le spike nommait son modele en dur. Le catalogue a ete refait depuis
    (HOS-104 a HOS-109) et `lfm2.5-2.6b-128k` est devenu
    `lfm2.5-2.6b-125k` : l'agent repondait `HTTP 404 model not found`
    apres trois tentatives, ce que l'ancien handler `session_update`
    jetait sans le lire.
    """
    import json
    import urllib.request

    with urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=10) as r:
        donnees = json.load(r)
    return {m["name"].removesuffix(":latest") for m in donnees.get("models", [])}


def _loud(name):
    """Wrap a handler so its real exception is visible.

    ACP re-raises handler failures as an opaque "Internal error" with the
    original traceback discarded, which says nothing about which method
    failed or why.
    """
    def deco(fn):
        import functools

        @functools.wraps(fn)
        async def wrapper(*a, **kw):
            import time as _t
            depart = _t.monotonic()
            print(f'-> {name}', flush=True)
            try:
                resultat = await fn(*a, **kw)
            except Exception as exc:
                import traceback
                print(f"!! handler {name} a leve: {type(exc).__name__}: {exc}", flush=True)
                traceback.print_exc()
                raise
            # Journaliser la *sortie* autant que l'entree : sans elle on ne
            # distingue pas « le handler n'a jamais rendu la main » de « il a
            # rendu et l'agent n'en a rien fait ». Les deux ressemblent a un
            # silence, et appellent des recherches opposees.
            print(f'<- {name} en {(_t.monotonic() - depart) * 1000:.0f} ms '
                  f'-> {type(resultat).__name__}: {resultat!r}'[:400], flush=True)
            return resultat
        return wrapper
    return deco


class SpikeClient(acp.Client):
    """Minimal client: record what streams back, auto-approve permissions."""

    def __init__(self) -> None:
        self.updates: list[str] = []
        self.permission_requests = 0

    @_loud('session_update')
    async def session_update(self, session_id: str, update=None, **kwargs) -> None:
        """Journaliser le *contenu*, pas seulement le nom de type.

        La version precedente ne gardait que `type(update).__name__`. C'est
        l'angle mort qui a fait durer le blocage : apres la permission
        accordee, l'agent continue peut-etre d'emettre — un message
        d'erreur, une relance, un abandon — et on jetait precisement ce
        qu'il fallait lire.
        """
        kind = type(update).__name__ if update is not None else "?"
        self.updates.append(kind)

        detail = ""
        if update is not None:
            dump = getattr(update, "model_dump", None)
            try:
                brut = dump(exclude_none=True) if callable(dump) else vars(update)
            except Exception:  # pragma: no cover - diagnostic, jamais bloquant
                brut = {"<illisible>": repr(update)[:200]}
            detail = repr(brut)
            if len(detail) > 600:
                detail = detail[:600] + f"… (+{len(detail) - 600} car.)"
        print(f"   [{len(self.updates):3d}] {kind}: {detail}", flush=True)

    @_loud('request_permission')
    async def request_permission(self, options, session_id: str, tool_call=None, **kwargs):
        self.permission_requests += 1
        options = options or []
        print(f'   options recues: {[(getattr(o,"option_id",None), getattr(o,"kind",None), getattr(o,"name",None)) for o in options]}', flush=True)
        # ACP_SPIKE_DENY=1 refuse au lieu d'autoriser. Ce n'est pas une
        # option de confort : autoriser laisse l'agent fige sans rien
        # emettre, et on ne peut pas distinguer « notre reponse ne lui
        # parvient pas » de « seul le chemin autorise se bloque ». Refuser
        # emprunte le meme aller-retour et repond a la question.
        if os.environ.get("ACP_SPIKE_DENY") == "1":
            from acp.schema import DeniedOutcome, RequestPermissionResponse
            print("   (refus force par ACP_SPIKE_DENY)", flush=True)
            return RequestPermissionResponse(outcome=DeniedOutcome(outcome='cancelled'))

        # Pick the first allow-shaped option so the spike is non-interactive.
        for opt in options:
            kind = str(getattr(opt, "kind", "")).lower()
            if "allow" in kind:
                from acp.schema import AllowedOutcome, RequestPermissionResponse
                return RequestPermissionResponse(
                    outcome=AllowedOutcome(outcome='selected', option_id=opt.option_id))
        from acp.schema import DeniedOutcome, RequestPermissionResponse
        return RequestPermissionResponse(outcome=DeniedOutcome(outcome='cancelled'))

    @_loud('write_text_file')
    async def write_text_file(self, content: str, path: str, session_id: str, **kwargs):
        from acp.schema import WriteTextFileResponse
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(content, encoding="utf-8")
        return WriteTextFileResponse()

    @_loud('read_text_file')
    async def read_text_file(self, path: str, session_id: str, **kwargs):
        from acp.schema import ReadTextFileResponse
        try:
            return ReadTextFileResponse(content=Path(path).read_text(encoding="utf-8"))
        except OSError:
            return ReadTextFileResponse(content="")

    # Terminal methods: declared unsupported in capabilities, but implemented
    # defensively — an unimplemented handler surfaces as an opaque
    # "Internal error" that says nothing about which method was missing.
    @_loud('create_terminal')
    async def create_terminal(self, command: str, session_id: str, **kwargs):
        from acp.schema import CreateTerminalResponse
        self.updates.append("create_terminal(REFUSED)")
        return CreateTerminalResponse(terminal_id="unsupported")

    async def terminal_output(self, session_id: str, terminal_id: str, **kwargs):
        from acp.schema import TerminalOutputResponse
        return TerminalOutputResponse(output="", truncated=False)

    async def wait_for_terminal_exit(self, session_id: str, terminal_id: str, **kwargs):
        from acp.schema import TerminalExitStatus, WaitForTerminalExitResponse
        return WaitForTerminalExitResponse(exit_status=TerminalExitStatus(exit_code=1))

    async def kill_terminal(self, session_id: str, terminal_id: str, **kwargs):
        from acp.schema import KillTerminalResponse
        return KillTerminalResponse()

    async def release_terminal(self, session_id: str, terminal_id: str, **kwargs):
        from acp.schema import ReleaseTerminalResponse
        return ReleaseTerminalResponse()


async def main() -> int:
    workspace = Path(tempfile.mkdtemp(prefix="acp_spike_"))
    env = os.environ.copy()
    env.update({
        "HERMES_HOME": HERMES_HOME,
        "OPENAI_API_KEY": "hermes_ollama_projets",
        "PYTHONUTF8": "1",
    })

    client = SpikeClient()
    print(f"workspace: {workspace}")

    async with acp.spawn_agent_process(
        client, ACP_EXE, env=env, cwd=str(workspace),
    ) as (conn, process):
        # ACP_SPIKE_SANS_FS=1 declare un client sans capacite fichier.
        #
        # L'agent ne peut alors plus deleguer l'ecriture : il doit ecrire
        # lui-meme, ce qu'il fait tous les jours par le CLI. Si le blocage
        # disparait, la panne est dans la negociation `fs` ; s'il persiste,
        # elle est dans l'execution d'outil elle-meme. Les deux menent a des
        # recherches opposees, et rien d'autre ne les separe.
        sans_fs = os.environ.get("ACP_SPIKE_SANS_FS") == "1"
        fs = FileSystemCapabilities(
            read_text_file=not sans_fs, write_text_file=not sans_fs,
        )
        init = await conn.initialize(
            protocol_version=acp.PROTOCOL_VERSION,
            client_capabilities=ClientCapabilities(fs=fs, terminal=True),
            client_info=Implementation(name="hermes-os", version="1.0.0"),
        )
        print(f"1. handshake OK — capabilities={bool(getattr(init, 'agent_capabilities', None))}"
              f"{'  [client SANS capacite fichier]' if sans_fs else ''}")

        session = await conn.new_session(cwd=str(workspace), mcp_servers=[])
        sid = session.session_id
        print(f"2. session creee: {sid}")

        # Which model is this session about to use? Never specified in the
        # first attempt, so it fell back to the configured default — which
        # may be a remote provider that simply hangs without credentials.
        models = getattr(session, "models", None)
        available = getattr(models, "available_models", None) or []
        current = getattr(models, "current_model_id", None)
        ids = [str(getattr(m, "model_id", m)) for m in available]
        print(f"2b. modele courant: {current}")

        # La liste entiere, et non ses huit premiers. Tronquee, elle ne
        # montrait que des modeles distants et laissait croire qu'aucun
        # modele local n'etait offert — alors que le probleme etait tout
        # autre : les entrees `custom:` de l'agent nomment des tags que
        # Ollama ne sert plus (HOS-113).
        locaux = [i for i in ids if i.startswith("custom:")]
        print(f"2c. {len(ids)} modeles offerts, dont {len(locaux)} locaux")
        for i in locaux:
            print(f"      {i}")

        # Choisir un modele que le serveur sert vraiment, plutot qu'un nom
        # ecrit en dur : c'est la derive entre les deux qui a coute la
        # session precedente.
        # La preference ne court-circuite jamais le controle de presence.
        # La premiere version le faisait, et retenait donc le fantome
        # `-128k` puisque `MODEL` etait lui aussi perime : exactement
        # l'erreur que ce spike sert a debusquer, reproduite dans son
        # propre code.
        servis = _tags_ollama()
        candidats = [i for i in locaux if _tag_de(i) in servis]
        utilisable = next((i for i in candidats if _tag_de(i) == MODEL), None) \
            or next(iter(candidats), None)
        if utilisable is not None:
            await conn.set_session_model(session_id=sid, model_id=utilisable)
            print(f"2d. modele choisi (present cote Ollama): {utilisable}")
        else:
            print("2d. AUCUN modele `custom:` de l'agent ne correspond a un tag servi")
            print(f"    Ollama sert: {sorted(servis)}")
            return 2

        # ── Mesure de reference : un tour sans aucun outil ──────────────
        #
        # Sans elle on ne sait pas ce qu'on mesure. Le blocage observe suit
        # toujours un `ToolCallStart` ; reste a savoir si un tour qui n'en
        # emet aucun aboutit. Si oui, la panne est l'execution d'outil et
        # rien d'autre. Si non, elle est plus profonde et toute enquete sur
        # les outils serait perdue.
        avant = len(client.updates)
        try:
            temoin = await asyncio.wait_for(
                conn.prompt(
                    session_id=sid,
                    prompt=[TextContentBlock(
                        type="text",
                        text="Reply with exactly one word: pong. "
                             "Do not use any tool.",
                    )],
                ),
                timeout=SANS_OUTIL_TIMEOUT_S,
            )
        except asyncio.TimeoutError:
            print(f"2e. TEMOIN SANS OUTIL: bloque apres {SANS_OUTIL_TIMEOUT_S:.0f}s "
                  f"({len(client.updates) - avant} updates) — la panne n'est PAS "
                  f"specifique aux outils")
            return 3
        outils = [u for u in client.updates[avant:] if "ToolCall" in u]
        print(f"2e. TEMOIN SANS OUTIL: abouti, stop_reason="
              f"{getattr(temoin, 'stop_reason', '?')}, "
              f"{len(client.updates) - avant} updates, {len(outils)} appel(s) d'outil")

        # Borne explicite : le blocage connu ne rend jamais la main, et un
        # spike qui pend n'apprend rien de plus a 900 s qu'a 180 s. La
        # difference est qu'on peut lire ce qui a ete emis avant l'arret.
        try:
            result = await asyncio.wait_for(
                conn.prompt(
                    session_id=sid,
                    prompt=[TextContentBlock(
                        type="text",
                        text="Create a file named ACP_SPIKE.md containing exactly one "
                             "line: 'acp ok'.",
                    )],
                ),
                timeout=PROMPT_TIMEOUT_S,
            )
        except asyncio.TimeoutError:
            print(f"3. prompt#1 BLOQUE apres {PROMPT_TIMEOUT_S:.0f}s — "
                  f"updates={len(client.updates)} permissions={client.permission_requests}")
            print(f"   derniers updates: {client.updates[-12:]}")
            artifact = workspace / "ACP_SPIKE.md"
            print(f"   artefact sur disque: {'OUI' if artifact.is_file() else 'NON'}")
            return 1
        print(f"3. prompt#1 stop_reason={getattr(result, 'stop_reason', '?')} "
              f"updates={len(client.updates)} permissions={client.permission_requests}")

        artifact = workspace / "ACP_SPIKE.md"
        ok1 = artifact.is_file() and "acp ok" in artifact.read_text(encoding="utf-8")
        print(f"4. artefact reel sur disque: {'OUI' if ok1 else 'NON'}")

        before = len(client.updates)
        result2 = await conn.prompt(
            session_id=sid,
            prompt=[TextContentBlock(
                type="text",
                text="Now append a second line 'second turn' to that same file.",
            )],
        )
        print(f"5. prompt#2 MEME session stop_reason={getattr(result2, 'stop_reason', '?')} "
              f"nouveaux_updates={len(client.updates) - before}")

        ok2 = artifact.is_file() and "second turn" in artifact.read_text(encoding="utf-8")
        print(f"6. session reutilisable (2 tours): {'OUI' if ok2 else 'NON'}")
        print()
        print("CONTENU FINAL:")
        print(artifact.read_text(encoding="utf-8") if artifact.is_file() else "(aucun fichier)")
        return 0 if ok1 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
