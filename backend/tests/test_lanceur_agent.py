"""Un sous-processus de l'agent n'hérite jamais du canal ACP (HOS-138).

L'incident, mesuré le 2026-08-21. Chaque mission bloquait sur son **premier
outil fichier**, sans erreur, sans fin. Le journal de l'agent s'arrêtait
sur ::

    tools.file_tools: Creating new local environment for task default...

Trois dumps de pile à 45 s d'intervalle ont montré le même point :
`tools/environments/local.py:911`, la sonde qui vérifie que Git Bash
démarre, bloquée dans `subprocess.communicate`. Hors ACP, cette sonde rend
en **0,1 s**.

Quatre variantes lancées *dans le processus ACP lui-même*, cinq fois de
suite, identiques à chaque fois :

* référence, stdin hérité — bloque > 20 s ;
* ``stdin=DEVNULL`` — code 0 en 0,1 s ;
* sans ``creationflags``, stdin hérité — bloque > 20 s ;
* tout en ``DEVNULL`` — code 0 en 0,1 s.

`creationflags` était donc hors de cause : **c'est l'héritage de stdin**. Et
dès que la sonde a cessé de bloquer, `note.txt` est apparu dans le
workspace : l'écriture n'échouait pas, elle n'avait jamais lieu.

Le blocage est définitif bien que la sonde se donne `timeout=15`, parce que
sur Windows `subprocess.run` rattrape son propre délai puis rappelle
`communicate()` **sans délai** — et ce second appel joint des threads
lecteurs qui n'atteindront jamais EOF.

Ces tests protègent la règle, pas le symptôme : ce qu'un appelant demande
est respecté, ce qu'il n'a pas exprimé est muselé.
"""
from __future__ import annotations

import subprocess

from backend.ral.adapters.lanceur_agent import RANGS, museler


class TestCeQuiEstMusele:
    def test_le_cas_mesure_stdin_non_precise(self):
        """`subprocess.run(capture_output=True)` — la forme exacte qu'emploie
        la sonde bash — ne précise pas `stdin`. C'est ce trou qui bloquait."""
        complete = museler((), {"stdout": subprocess.PIPE,
                                "stderr": subprocess.PIPE})

        assert complete["stdin"] is subprocess.DEVNULL

    def test_stdout_non_precise_est_musele_aussi(self):
        """Un enfant qui hérite de stdout écrit dans le flux JSON-RPC que le
        client analyse — il corromprait le protocole, pas seulement le
        journal."""
        assert museler((), {})["stdout"] is subprocess.DEVNULL

    def test_un_none_explicite_compte_comme_non_precise(self):
        """`Popen(cmd, stdin=None)` est le défaut écrit à la main : il
        signifie « hérite », donc il doit être muselé comme l'absence."""
        assert museler((), {"stdin": None})["stdin"] is subprocess.DEVNULL


class TestCeQuiEstRespecte:
    """Museler ce qu'un appelant a demandé casserait l'agent — et le ferait
    en silence, ce qui est pire que le blocage qu'on corrige."""

    def test_un_pipe_demande_est_garde(self):
        complete = museler((), {"stdin": subprocess.PIPE})

        assert complete["stdin"] is subprocess.PIPE

    def test_un_descripteur_est_garde(self):
        assert museler((), {"stdout": 7})["stdout"] == 7

    def test_le_positionnel_est_un_choix(self):
        """`Popen(args, bufsize, executable, stdin, stdout)` : au-delà du
        rang, l'appelant a bien exprimé son canal. Ne regarder que `kwargs`
        l'écraserait sans rien dire."""
        args = ("cmd", -1, None, subprocess.PIPE, subprocess.PIPE)

        complete = museler(args, {})

        assert "stdin" not in complete
        assert "stdout" not in complete

    def test_stderr_n_est_jamais_musele(self):
        """Le journal de l'agent est la seule source qui explique un
        blocage. Le jeter est précisément ce qui a coûté la séance."""
        assert "stderr" not in RANGS
        assert "stderr" not in museler((), {})


class TestLaSignatureSurLaquelleOnSAppuie:
    def test_les_rangs_correspondent_a_popen(self):
        """`museler` lit des rangs positionnels : si CPython réordonnait la
        signature de `Popen`, la règle protégerait le mauvais canal sans que
        rien ne le signale."""
        import inspect

        parametres = list(inspect.signature(subprocess.Popen).parameters)

        for canal, rang in RANGS.items():
            assert parametres[rang] == canal
