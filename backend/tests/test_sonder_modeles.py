"""Un verdict de sonde doit survivre au processus qui l'obtient (HOS-143).

`agentic_probe.probe()` mesure, mais **ne persiste rien** : jusqu'ici
`save_result()` n'etait appele que par les tests. Aucun code de production
ne l'invoquait, si bien qu'un verdict mourait avec le processus et que le
magasin ne pouvait se remplir que par un script ad hoc que personne n'avait
garde.

Ce que cela a coute, mesure le 2026-08-21 : le magasin ne contenait plus que
des tags morts, la refonte du catalogue ayant renomme les modeles.
`agentic_capable` traitant un modele non mesure comme non prouve — a raison,
deviner s'etait revele faux une fois sur deux — **tous** les modeles du
catalogue etaient juges incapables, et chaque mission retombait sur le repli
de 2,6 Md, note `code 28`.

Ces tests portent sur l'outil, pas sur la sonde : ils n'executent aucun
modele. Ce qui doit etre garanti est qu'il **enregistre**, et qu'il sait
quels modeles comptent.
"""
from __future__ import annotations

import sys
from pathlib import Path

_SCRIPTS = str(Path("scripts").resolve())
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)

import sonder_modeles  # noqa: E402


class TestIlEnregistreCeQuIlMesure:
    """Le point de tout l'exercice. Sans cet appel, l'outil ne serait qu'une
    facon plus lente de ne rien retenir."""

    def test_chaque_essai_est_persiste(self, monkeypatch):
        enregistres = []

        class _Resultat:
            success = True

        monkeypatch.setattr(sonder_modeles, "probe", lambda m: _Resultat())
        monkeypatch.setattr(sonder_modeles, "save_result", enregistres.append)
        monkeypatch.setattr(sonder_modeles, "measured_success_for",
                            lambda m: None)

        succes, essais = sonder_modeles.sonder("un-modele", 3)

        assert (succes, essais) == (3, 3)
        assert len(enregistres) == 3, "chaque essai doit etre enregistre"

    def test_un_echec_est_une_mesure_et_compte(self, monkeypatch):
        """Un modele qui echoue doit le voir inscrit : c'est ainsi qu'il
        cesse d'etre choisi. Ne retenir que les succes rendrait le magasin
        incapable de disqualifier quoi que ce soit."""
        enregistres = []

        class _Echec:
            success = False

        monkeypatch.setattr(sonder_modeles, "probe", lambda m: _Echec())
        monkeypatch.setattr(sonder_modeles, "save_result", enregistres.append)
        monkeypatch.setattr(sonder_modeles, "measured_success_for",
                            lambda m: False)

        succes, essais = sonder_modeles.sonder("un-modele", 2)

        assert (succes, essais) == (0, 2)
        assert len(enregistres) == 2

    def test_une_sonde_impossible_n_enregistre_rien(self, monkeypatch):
        """Une sonde qui n'a pas pu s'executer n'est pas un echec du
        modele — l'inscrire le disqualifierait pour une panne de la
        machine."""
        enregistres = []

        def _leve(_):
            raise RuntimeError("verrou deja pris")

        monkeypatch.setattr(sonder_modeles, "probe", _leve)
        monkeypatch.setattr(sonder_modeles, "save_result", enregistres.append)
        monkeypatch.setattr(sonder_modeles, "measured_success_for",
                            lambda m: None)

        succes, essais = sonder_modeles.sonder("un-modele", 2)

        assert (succes, essais) == (0, 2)
        assert enregistres == []


class TestQuelsModelesComptent:
    def test_ce_sont_ceux_affectes_a_un_role(self):
        """Seuls les modeles qu'un role designe peuvent etre choisis par le
        routeur : sonder les autres coute du temps sans rien changer."""
        import yaml

        catalogue = yaml.safe_load(
            Path("config/models.yaml").read_text(encoding="utf-8"))
        attendus = {spec.get("model") for spec in
                    (catalogue.get("roles") or {}).values() if spec.get("model")}

        assert set(sonder_modeles._modeles_du_catalogue()) == attendus

    def test_sans_doublon(self):
        """`gpt-oss-20b-64k` sert trois roles. Le sonder trois fois
        tripleraient l'attente pour le meme verdict."""
        liste = sonder_modeles._modeles_du_catalogue()

        assert len(liste) == len(set(liste))
