# -*- coding: utf-8 -*-
"""G-14 — la chaine de preuve agentique, de la sonde jusqu'au predicat.

L'incident : le catalogue n'avait **aucun** verdict mesure, et deux causes
distinctes s'additionnaient.

1. Le magasin vivait dans `%TEMP%` (T-29, corrige en HOS-263) — tout ce que
   le projet avait mesure a ete efface par le systeme.
2. La sonde elle-meme mesurait autre chose que ce qu'elle annoncait. Sa
   consigne disait « in your working directory » sans jamais nommer ce
   repertoire, alors que le sous-processus le recoit en `cwd` et que la
   **production**, elle, le nomme. Mesure le 2026-09-06 sur
   `lfm2.5-2.6b-125k`, reponse brute conservee : six appels d'outils, le
   bon contenu, le fichier ecrit dans `/c/Users/emeri/` apres un premier
   essai dans `/home/user/`. Verdict enregistre : echec. Meme modele, meme
   verification disque, chemin nomme : succes en 43 s.

Ces tests gardent la chaine entiere : consigne fidele au chemin reel →
resultat persistant → relu apres redemarrage → predicat → decision.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from backend.core import etat
from backend.core.bootstrap import service_registry as sr
from backend.model_intelligence import agentic_probe as ap

RACINE = Path(__file__).resolve().parents[2]


@pytest.fixture
def magasin(tmp_path, monkeypatch):
    """Un magasin a nous : la campagne reelle ne doit jamais etre touchee."""
    chemin = tmp_path / "db" / "agentic_probe_results.json"
    monkeypatch.setattr(ap, "_probe_store_path", lambda: chemin)
    sr._agentic_capable_cached.cache_clear()  # noqa: SLF001
    yield chemin
    sr._agentic_capable_cached.cache_clear()  # noqa: SLF001


def _essai(modele="m", succes=True):
    return ap.AgenticProbeResult(
        model=modele, success=succes, tool_calls=2 if succes else 0,
        duration_s=1.0, artifact_verified=succes)


# ── 1. La consigne mesure le chemin reel, pas une convention devinee ──

def test_la_consigne_depend_du_workspace():
    """La consigne etait une **constante** : elle ne pouvait pas nommer un
    repertoire qu'elle ne connaissait pas, et le modele devait deviner.

    On ne teste pas une forme mais la dependance : deux workspaces, deux
    consignes, chacune portant la sienne et pas celle de l'autre.
    """
    a = Path("C:/un/workspace/precis")
    b = Path("C:/un/autre/tout/different")
    qa, qb = ap._probe_query(a), ap._probe_query(b)  # noqa: SLF001
    assert qa != qb
    assert repr(str(a)) in qa and repr(str(a)) not in qb
    assert repr(str(b)) in qb and repr(str(b)) not in qa


def test_la_consigne_dit_ce_que_la_production_dit(tmp_path):
    """Le point entier de cette sonde est de mesurer le **chemin reel**.

    Une sonde plus severe que la production mesure la sonde. Ce test lie
    les deux formulations : si l'une derive, il rougit.
    """
    from backend.execution.task_executor import RealTaskExecutor

    racine = str(tmp_path)
    executeur = object.__new__(RealTaskExecutor)
    # `_build_messages` n'a besoin que de ces cinq apports, tous optionnels.
    for nom in ("_mission_brief_for", "_livrables_pour", "_journal_pour",
                "_relais_pour", "_upstream_results_for"):
        setattr(executeur, nom, None)
    messages = executeur._build_messages(  # noqa: SLF001
        type("T", (), {"title": "t", "task_id": "t1"})(),
        type("A", (), {"agent_id": "", "skill_ids": [], "tool_ids": []})(),
        ("projet", racine), hermes_agent=True)
    systeme = " ".join(m.get("content", "") for m in messages)

    clause = f"Your working directory is {racine!r}"
    assert clause in systeme, "la production ne nomme plus le workspace ainsi"
    assert clause in ap._probe_query(Path(racine))  # noqa: SLF001


def test_le_verdict_se_lit_sur_le_disque_pas_dans_la_reponse(magasin, monkeypatch,
                                                             tmp_path):
    """Nommer le chemin ne doit pas rendre la sonde credule : un modele qui
    raconte sans ecrire echoue toujours."""
    class _Fini:
        returncode = 0
        stdout = "The file has been created successfully. 4 tool calls"
        stderr = ""

    monkeypatch.setattr(ap.subprocess, "run", lambda *a, **k: _Fini())
    resultat = ap._probe_once("bavard", None)  # noqa: SLF001
    assert resultat.success is False
    assert resultat.artifact_verified is False


# ── 2. Le resultat survit au processus ────────────────────────────────

def test_le_verdict_survit_au_redemarrage_du_processus(tmp_path):
    """La preuve doit vivre sur le disque, pas dans un processus.

    Deux interpreteurs distincts : l'un mesure, l'autre lit. C'est
    exactement ce que la sonde et le backend sont l'un pour l'autre.
    """
    env = {**dict(__import__("os").environ), "HERMES_DATA_DIR": str(tmp_path)}

    ecrire = (
        "import sys; sys.path.insert(0, r'%s')\n"
        "from backend.model_intelligence.agentic_probe import "
        "AgenticProbeResult, save_result\n"
        "for _ in range(3):\n"
        "    save_result(AgenticProbeResult('mdl', True, 2, 1.0, True))\n"
    ) % RACINE
    lire = (
        "import sys; sys.path.insert(0, r'%s')\n"
        "from backend.model_intelligence.agentic_probe import measured_success_for\n"
        "print(measured_success_for('mdl'))\n"
    ) % RACINE

    a = subprocess.run([sys.executable, "-c", ecrire], env=env,
                       capture_output=True, text=True, timeout=120)
    assert a.returncode == 0, a.stderr
    b = subprocess.run([sys.executable, "-c", lire], env=env,
                       capture_output=True, text=True, timeout=120)
    assert b.returncode == 0, b.stderr
    assert b.stdout.strip() == "True", b.stdout


def _script_empreinte(digest, num_ctx):
    """Remplace `current_fingerprint` sans httpx ni pytest, pour un
    sous-processus autonome (`python -c ...`)."""
    return (
        "from backend.model_intelligence import agentic_probe\n"
        "agentic_probe.current_fingerprint = "
        "lambda _m: {'digest': %r, 'num_ctx': %r}\n"
    ) % (digest, num_ctx)


def test_linvalidation_dempreinte_survit_au_redemarrage(tmp_path):
    """G. La persistance ne suffit pas si l'invalidation, elle, ne
    traverse pas le redemarrage : trois interpretes distincts — un qui
    mesure sous une empreinte, un second qui lit apres un changement de
    poids simule, un troisieme qui remesure sous la nouvelle empreinte et
    doit obtenir un verdict frais, pas melange a l'ancien."""
    env = {**dict(__import__("os").environ), "HERMES_DATA_DIR": str(tmp_path)}

    mesurer_v1 = (
        "import sys; sys.path.insert(0, r'%s')\n" % RACINE
        + _script_empreinte("poids-v1", 131072)
        + "from backend.model_intelligence.agentic_probe import "
          "AgenticProbeResult, save_result\n"
          "for _ in range(3):\n"
          "    save_result(AgenticProbeResult('mdl-restart', True, 2, 1.0, True))\n"
    )
    lire_apres_changement = (
        "import sys; sys.path.insert(0, r'%s')\n" % RACINE
        + _script_empreinte("poids-v2", 131072)
        + "from backend.model_intelligence.agentic_probe import measured_success_for\n"
          "print(measured_success_for('mdl-restart'))\n"
    )
    remesurer_v2 = (
        "import sys; sys.path.insert(0, r'%s')\n" % RACINE
        + _script_empreinte("poids-v2", 131072)
        + "from backend.model_intelligence.agentic_probe import "
          "AgenticProbeResult, save_result, measured_success_for\n"
          "save_result(AgenticProbeResult('mdl-restart', False, 0, 1.0, False))\n"
          "save_result(AgenticProbeResult('mdl-restart', False, 0, 1.0, False))\n"
          "print(measured_success_for('mdl-restart'))\n"
    )

    a = subprocess.run([sys.executable, "-c", mesurer_v1], env=env,
                       capture_output=True, text=True, timeout=120)
    assert a.returncode == 0, a.stderr

    b = subprocess.run([sys.executable, "-c", lire_apres_changement], env=env,
                       capture_output=True, text=True, timeout=120)
    assert b.returncode == 0, b.stderr
    assert b.stdout.strip() == "None", b.stdout

    c = subprocess.run([sys.executable, "-c", remesurer_v2], env=env,
                       capture_output=True, text=True, timeout=120)
    assert c.returncode == 0, c.stderr
    assert c.stdout.strip() == "False", c.stdout  # 2/2 sous v2, pas 2/5 melange a v1


def test_le_magasin_vit_sous_un_dossier_preserve(monkeypatch, tmp_path):
    """`preserve_set()` enumere des **dossiers**. Un magasin pose ailleurs
    serait efface par la premiere mise a jour — la perte que T-29 corrigeait
    se refabriquerait un cran plus loin."""
    monkeypatch.setenv("HERMES_DATA_DIR", str(tmp_path))
    preserves = {p.resolve() for p in etat.preserve_set()}
    assert ap._probe_store_path().parent.resolve() in preserves  # noqa: SLF001


# ── 3. Isolation, faux positifs, absence de preuve ────────────────────

def test_sonder_un_modele_ne_donne_pas_de_verdict_a_un_autre(magasin):
    for _ in range(3):
        ap.save_result(_essai("prouve", succes=True))
    assert ap.measured_success_for("prouve") is True
    assert ap.measured_success_for("jamais-sonde") is None


def test_une_sonde_qui_echoue_ne_promeut_personne(magasin):
    """Un echec est une mesure ; il ne doit jamais devenir un `True`."""
    for _ in range(3):
        ap.save_result(_essai("rate", succes=False))
    assert ap.measured_success_for("rate") is False


def test_un_seul_essai_ne_fait_pas_une_preuve(magasin):
    """Le succes agentique n'est pas deterministe sur ce materiel : un
    echantillon promeut un narrateur."""
    ap.save_result(_essai("un-seul", succes=True))
    assert ap.measured_success_for("un-seul") is None


def test_un_modele_jamais_sonde_reste_sans_preuve(magasin):
    assert ap.measured_success_for("inconnu") is None
    magasin.parent.mkdir(parents=True, exist_ok=True)
    magasin.write_text(json.dumps({"autre": {"trials": 3, "successes": 3}}),
                       encoding="utf-8")
    assert ap.measured_success_for("inconnu") is None


# ── 4. Du magasin jusqu'a la decision ─────────────────────────────────

def _ollama_bouchonne(monkeypatch, capabilities=("tools", "completion"),
                      params="9.0B", *, model=None, digest="digest-1",
                      num_ctx=131072):
    """Repond a `/api/show` et `/api/tags` sans Ollama, et sans modele resident.

    `model`/`digest`/`num_ctx` pilotent l'empreinte que `current_fingerprint`
    (G-15) lira sur `/api/tags` + `/api/show`. Par defaut `model=None` : la
    liste de `/api/tags` ne nomme aucun modele, donc aucune requete ne
    trouve de correspondance et `current_fingerprint` rend toujours `None`
    — l'empreinte est alors invisible, comme avant G-15, pour les tests qui
    ne s'y interessent pas. La passer explicitement est ce qui active le
    controle de fraicheur dans les tests qui le ciblent.
    """
    import httpx

    class _Reponse:
        def __init__(self, payload):
            self._payload = payload

        def raise_for_status(self):
            pass

        def json(self):
            return self._payload

    class _Client:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def get(self, url, *a, **k):
            assert url.endswith("/api/tags")
            entries = [{"name": model, "model": model, "digest": digest}] if model else []
            return _Reponse({"models": entries})

        def post(self, url, *a, **k):
            assert url.endswith("/api/show")
            return _Reponse({
                "capabilities": list(capabilities),
                "details": {"parameter_size": params},
                "model_info": {"x.context_length": 131072},
                "parameters": f"num_ctx {num_ctx}\ntemperature 1",
            })

    monkeypatch.setattr(httpx, "Client", _Client)
    monkeypatch.setattr(sr, "_runtime_footprint_for", lambda _m: (None, None))


def test_un_verdict_mesure_atteint_le_predicat(magasin, monkeypatch):
    """Le maillon que G-14 devait fermer : ce que la sonde ecrit, le
    bootstrap le lit — ici apres redemarrage, cache vide."""
    _ollama_bouchonne(monkeypatch)
    for _ in range(3):
        ap.save_result(_essai("mdl-a", succes=True))
    sr._agentic_capable_cached.cache_clear()  # noqa: SLF001 - un redemarrage
    assert sr._agentic_capable_for("mdl-a") is True  # noqa: SLF001


def test_une_mesure_fraiche_invalide_le_cache(magasin, monkeypatch):
    """Le cache disait « the answer only changes when the model itself is
    replaced ». Faux des qu'une sonde peut ecrire : un backend deja lance
    servait `None` jusqu'a son redemarrage, et la preuve persistante
    n'atteignait jamais le predicat.

    On ne vide aucun cache ici : c'est tout l'objet du test.
    """
    _ollama_bouchonne(monkeypatch)
    assert sr._agentic_capable_for("mdl-b") is None  # noqa: SLF001
    for _ in range(3):
        ap.save_result(_essai("mdl-b", succes=True))
    assert sr._agentic_capable_for("mdl-b") is True  # noqa: SLF001


def test_un_disqualifieur_structurel_prime_sur_une_mesure_positive(magasin,
                                                                   monkeypatch):
    """Une mesure passee ne rend pas utilisable un modele qui, maintenant,
    ne peut pas travailler — un modele d'embedding annonce `tools`, et un
    modele qui deborde sur le CPU repond dix fois plus lentement.

    Les deux signaux restent distincts : `agentic_disqualifie` porte la
    preuve negative structurelle, `measured_agentic_success` le verdict
    mesure. C'est le premier qui tranche.
    """
    _ollama_bouchonne(monkeypatch, capabilities=("tools", "embedding"))
    for _ in range(3):
        ap.save_result(_essai("mdl-c", succes=True))
    assert ap.measured_success_for("mdl-c") is True
    assert sr._agentic_capable_for("mdl-c") is False  # noqa: SLF001


def test_la_decision_du_routeur_survit_a_un_modele_prouve(magasin, monkeypatch):
    """Le bout de la chaine : preuve → predicat → `_agentic_model`."""
    from backend.execution.task_executor import RealTaskExecutor

    _ollama_bouchonne(monkeypatch)
    for _ in range(3):
        ap.save_result(_essai("choisi-par-le-routeur", succes=True))

    executeur = object.__new__(RealTaskExecutor)
    executeur._fallback_model = "le-repli"  # noqa: SLF001
    executeur._agentic_capable_for = sr._agentic_capable_for  # noqa: SLF001
    assert executeur._agentic_model(  # noqa: SLF001
        "choisi-par-le-routeur", "code_generation") == "choisi-par-le-routeur"


# ── 5. G-15 : un verdict est une mesure datee, jusqu'au predicat ──────
#
# La chaine que 1-4 gardent (sonde -> magasin -> predicat -> decision)
# supposait que la sonde repondait toujours pour le meme modele. Mesure le
# 2026-09-06 en fermant G-14 : ce n'est pas garanti — `ollama pull` sous le
# meme tag change les poids, un Modelfile edite change `num_ctx`, et rien
# dans le magasin ne le disait. Ces tests repetent 1-4 avec un changement
# d'empreinte entre la mesure et la lecture : le predicat doit refuser de
# statuer plutot que de rendre un verdict perime.

def test_un_verdict_valide_le_reste_sans_changement(magasin, monkeypatch):
    """A. Rien ne bouge : le verdict mesure reste utilisable, empreinte
    verifiee a chaque lecture."""
    _ollama_bouchonne(monkeypatch, model="stable", digest="d1", num_ctx=131072)
    for _ in range(3):
        ap.save_result(_essai("stable", succes=True))
    assert ap.measured_success_for("stable") is True
    assert sr._agentic_capable_for("stable") is True  # noqa: SLF001


def test_un_changement_de_poids_perime_le_verdict_jusquau_predicat(magasin, monkeypatch):
    """B. `ollama pull` remplace les poids sous le meme tag : le verdict
    mesure avant ne repond plus pour ce qui tourne maintenant, et le
    predicat de production doit le refleter — pas seulement la fonction
    interne du module."""
    _ollama_bouchonne(monkeypatch, model="repave", digest="poids-v1", num_ctx=131072)
    for _ in range(3):
        ap.save_result(_essai("repave", succes=True))
    assert ap.measured_success_for("repave") is True
    assert sr._agentic_capable_for("repave") is True  # noqa: SLF001

    sr._agentic_capable_cached.cache_clear()  # noqa: SLF001 - un redemarrage
    _ollama_bouchonne(monkeypatch, model="repave", digest="poids-v2", num_ctx=131072)

    # None, pas False : ce n'est pas une preuve negative, c'est l'absence
    # de preuve pour le modele qui repond desormais a ce tag (T-29).
    assert ap.measured_success_for("repave") is None
    assert sr._agentic_capable_for("repave") is None  # noqa: SLF001


def test_un_changement_de_num_ctx_perime_le_verdict(magasin, monkeypatch):
    """B (variante). Un Modelfile edite pour servir un autre `num_ctx` est
    l'autre condition que le roadmap nomme explicitement pour G-15 — memes
    poids, portee agentique differente."""
    _ollama_bouchonne(monkeypatch, model="ctx-modifie", digest="meme-poids", num_ctx=131072)
    for _ in range(3):
        ap.save_result(_essai("ctx-modifie", succes=True))
    assert ap.measured_success_for("ctx-modifie") is True

    _ollama_bouchonne(monkeypatch, model="ctx-modifie", digest="meme-poids", num_ctx=8192)
    assert ap.measured_success_for("ctx-modifie") is None


def test_un_retour_a_une_empreinte_identique_ne_perd_pas_la_preuve(magasin, monkeypatch):
    """C. Un etat different revenu a une apparence identique : si aucune
    sonde n'a ete enregistree pendant l'ecart, l'empreinte redevient
    exactement celle qui a ete mesuree, et rien ne distingue ce cas d'un
    etat qui n'a jamais bouge — le contrat porte sur les poids et le
    num_ctx, pas sur un compteur de generations qui n'existe pas ici."""
    _ollama_bouchonne(monkeypatch, model="va-et-vient", digest="d1", num_ctx=131072)
    for _ in range(3):
        ap.save_result(_essai("va-et-vient", succes=True))
    assert ap.measured_success_for("va-et-vient") is True

    _ollama_bouchonne(monkeypatch, model="va-et-vient", digest="d2", num_ctx=131072)
    assert ap.measured_success_for("va-et-vient") is None  # perime pendant l'ecart

    _ollama_bouchonne(monkeypatch, model="va-et-vient", digest="d1", num_ctx=131072)
    assert ap.measured_success_for("va-et-vient") is True  # redevenu identique


def test_une_preuve_perimee_ne_se_reutilise_pas_pour_une_nouvelle_serie(magasin,
                                                                        monkeypatch):
    """D. Une sonde qui ecrit apres le changement ne doit pas mélanger ses
    essais a ceux d'un autre modele : 3 succes sous l'ancienne empreinte
    plus 1 echec sous la nouvelle ne doivent jamais donner 3/4 (75 %,
    au-dessus du seuil) — l'ancienne serie repond pour un modele qui n'est
    plus celui qu'on sonde."""
    _ollama_bouchonne(monkeypatch, model="serie", digest="d1", num_ctx=131072)
    for _ in range(3):
        ap.save_result(_essai("serie", succes=True))

    _ollama_bouchonne(monkeypatch, model="serie", digest="d2", num_ctx=131072)
    ap.save_result(_essai("serie", succes=False))

    entree = json.loads(magasin.read_text(encoding="utf-8"))["serie"]
    assert entree["trials"] == 1, "l'ancienne serie (3 essais) doit avoir ete purgee"
    assert entree["successes"] == 0
    assert entree["fingerprint"] == {"digest": "d2", "num_ctx": 131072}


def test_une_empreinte_illisible_ne_perime_pas_par_defaut(magasin, monkeypatch):
    """L'absence de mesure de fraicheur (Ollama injoignable, tag disparu de
    son catalogue) n'est pas un changement : le predicat continue de servir
    le dernier verdict connu plutot que de fabriquer un faux echec a partir
    d'une panne reseau — le seul appelant de production
    (`_agentic_capable_cached`) a deja garanti un `/api/show` reussi pour
    exactement ce modele avant de demander un verdict."""
    _ollama_bouchonne(monkeypatch, model="mesure", digest="d1", num_ctx=131072)
    for _ in range(3):
        ap.save_result(_essai("mesure", succes=True))

    monkeypatch.setattr(ap, "current_fingerprint", lambda _m: None)
    assert ap.measured_success_for("mesure") is True


def test_le_repli_ne_defait_plus_une_decision_sur_une_preuve_perimee(magasin, monkeypatch):
    """Chemin reel complet : `_agentic_model` choisissait `primaire` parce
    qu'il etait prouve capable. Ses poids changent sous le meme tag ; le
    repli, lui, vient d'etre prouve capable pour de bon. Avant G-15, le
    verdict perime de `primaire` restait `True` et la decision ne bougeait
    jamais. Apres, `primaire` redevient non-prouve et la regle T-29 (« on
    ne defait une decision que si le repli porte une preuve que le choix
    n'a pas ») joue enfin : le repli, mieux prouve, l'emporte.
    """
    import httpx

    from backend.execution.task_executor import RealTaskExecutor

    empreintes = {"primaire": {"digest": "vieux-poids", "num_ctx": 131072},
                  "repli-prouve": {"digest": "d-repli", "num_ctx": 131072}}

    class _Reponse:
        def __init__(self, payload):
            self._payload = payload

        def raise_for_status(self):
            pass

        def json(self):
            return self._payload

    class _Client:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def get(self, url, *a, **k):
            return _Reponse({"models": [
                {"name": nom, "model": nom, "digest": fp["digest"]}
                for nom, fp in empreintes.items()
            ]})

        def post(self, url, *a, json=None, **k):
            modele = (json or {}).get("model")
            num_ctx = empreintes.get(modele, {}).get("num_ctx", 131072)
            return _Reponse({
                "capabilities": ["tools", "completion"],
                "details": {"parameter_size": "9.0B"},
                "model_info": {"x.context_length": 131072},
                "parameters": f"num_ctx {num_ctx}",
            })

    monkeypatch.setattr(httpx, "Client", _Client)
    monkeypatch.setattr(sr, "_runtime_footprint_for", lambda _m: (None, None))

    for _ in range(3):
        ap.save_result(_essai("primaire", succes=True))
    sr._agentic_capable_cached.cache_clear()  # noqa: SLF001
    assert sr._agentic_capable_for("primaire") is True  # noqa: SLF001

    # Les poids de `primaire` changent sous le meme tag ; `repli-prouve`
    # vient d'etre mesure capable, pour de bon, sous sa propre empreinte.
    empreintes["primaire"] = {"digest": "nouveaux-poids", "num_ctx": 131072}
    sr._agentic_capable_cached.cache_clear()  # noqa: SLF001
    for _ in range(3):
        ap.save_result(_essai("repli-prouve", succes=True))
    sr._agentic_capable_cached.cache_clear()  # noqa: SLF001

    assert sr._agentic_capable_for("primaire") is None  # noqa: SLF001 - plus une preuve
    assert sr._agentic_capable_for("repli-prouve") is True  # noqa: SLF001

    executeur = object.__new__(RealTaskExecutor)
    executeur._fallback_model = "repli-prouve"  # noqa: SLF001
    executeur._agentic_capable_for = sr._agentic_capable_for  # noqa: SLF001
    assert executeur._agentic_model(  # noqa: SLF001
        "primaire", "code_generation") == "repli-prouve"
