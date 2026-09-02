"""« Flux ferme par l'agent » ne disait pas comment il etait mort (HOS-172).

Mesure du 2026-08-25 : trois tours perdus sur quarante taches, toujours la
meme signature. Le journal de l'agent montrait un tour termine proprement —

    Turn ended: reason=text_response(finish_reason=stop) api_calls=12/90

— puis plus rien, dans la meme seconde. Hermes OS constatait « flux ferme »
et n'en savait pas davantage : impossible de distinguer un processus tue
faute de memoire, un plantage, ou une sortie volontaire. Trois causes,
trois remedes, aucun moyen de trancher.

Le journal de l'agent (HOS-157) dit ce qu'il a **dit** ; il ne dit pas
comment il est **mort**.
"""
from __future__ import annotations

import asyncio
import sys

import backend.ral.adapters.hermes_agent_acp as acp


class _Session:
    def __init__(self, proc) -> None:
        self.proc = proc


#: Attendre la **fin du processus**, pas un delai fixe (HOS-213).
#:
#: La version precedente dormait 0,3 s puis diagnostiquait. Sur une
#: machine chargee, le demarrage de l'interpreteur depasse ce delai : le
#: processus n'etait pas encore mort, et `_pourquoi_ferme` repondait
#: — a juste titre — « le processus vit encore ». Le test echouait sur la
#: vitesse de la machine, pas sur le code.
#:
#: Trois secondes couvrent tres largement un `python -c "sys.exit(0)"`,
#: et le cas « vit encore » les epuise volontairement puisqu'il dort 30 s.
DELAI_DE_MORT_S = 3.0


async def _diagnostic(code_python: str) -> str:
    proc = await asyncio.create_subprocess_exec(
        sys.executable, "-c", code_python,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    try:
        limite = asyncio.get_running_loop().time() + DELAI_DE_MORT_S
        while proc.returncode is None and asyncio.get_running_loop().time() < limite:
            await asyncio.sleep(0.02)
        return await acp._pourquoi_ferme(_Session(proc))
    finally:
        if proc.returncode is None:
            proc.kill()
        await proc.wait()


def test_une_sortie_volontaire_est_nommee_comme_telle() -> None:
    """Code 0 : l'agent a decide de partir sans rendre son resultat.

    C'est alors un defaut de protocole, pas une panne — et le remede n'est
    pas le meme.
    """
    motif = asyncio.run(_diagnostic("import sys; sys.exit(0)"))

    assert "code 0" in motif
    assert "volontaire" in motif


def test_une_erreur_non_rattrapee_est_distinguee() -> None:
    motif = asyncio.run(_diagnostic("raise SystemExit(1)"))

    assert "code 1" in motif


def test_un_processus_vivant_est_distingue_d_un_processus_mort() -> None:
    """Fermer sa sortie sans mourir est un troisieme cas, et un autre bug."""
    motif = asyncio.run(_diagnostic("import time; time.sleep(30)"))

    assert "vit encore" in motif


def test_le_diagnostic_ne_fait_jamais_echouer_le_tour() -> None:
    """Le tour est deja perdu : le diagnostic ne doit rien coûter de plus."""
    class _Casse:
        proc = object()

    assert asyncio.run(acp._pourquoi_ferme(_Casse())) == ""
