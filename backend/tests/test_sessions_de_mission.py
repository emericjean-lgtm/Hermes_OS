"""Une mission, une session ; et un repli qui se dit (HOS-138).

Le mode jetable ouvre un processus d'agent **par tâche**. Une mission de
vingt tâches, ce sont vingt agents qui ne se sont jamais rencontrés : rien
de ce que le premier a lu, écrit ou compris du workspace n'atteint le
second. C'est ce qui rendait inatteignables — non pas absentes —
la compression de contexte, la revue de fond, le curator et la mémoire que
Hermes Agent implémente déjà.

Ces tests portent sur la tenue de porte, jamais sur ce qui se passe
derrière : le registre ne raisonne pas, ne choisit pas d'outils et ne
décompose rien. Un client d'agent factice suffit donc, et évite de lancer
un processus réel dans la suite.
"""
from __future__ import annotations

import asyncio

import pytest

from backend.ral.adapters.hermes_agent_acp import Tour
from backend.ral.adapters.sessions_de_mission import SessionsDeMission


class _ClientFactice:
    """Un agent qui note ce qu'on lui envoie, sans rien exécuter."""

    def __init__(self, *, disponible=(True, "")) -> None:
        self.recus: list[str] = []
        self.ouvertures: list[str] = []
        self.reprises: list[str] = []
        self.session_id = ""
        self.reprise = False
        self.fermetures = 0
        self.modeles: list[str] = []
        self._modele = ""
        self._disponible = disponible

    def disponible(self):
        return self._disponible

    async def ouvrir(self, cwd, *, reprendre=""):
        self.ouvertures.append(cwd)
        self.reprises.append(reprendre)
        # Meme contrat que le vrai client : l'identifiant rendu est celui
        # qu'on reprend, ou un neuf. `reprise` dit lequel des deux.
        self.session_id = reprendre or f"s-{len(self.ouvertures)}"
        self.reprise = bool(reprendre)
        return self

    async def tour(self, texte, *, delai=0, au_fil_de_l_eau=None):
        self.recus.append(texte)
        if au_fil_de_l_eau is not None:
            au_fil_de_l_eau("reponse", "fait")
        return Tour(texte="fait", stop="end_turn")

    async def choisir_modele(self, modele):
        # Meme garde que le vrai client : ne rebascule pas sur un modele
        # deja en place.
        if modele and modele != self._modele:
            self._modele = modele
            self.modeles.append(modele)
        return True

    async def fermer(self):
        self.fermetures += 1


def _registre(**kw):
    """Un registre et la liste des agents factices qu'il aura ouverts."""
    clients: list[_ClientFactice] = []

    def fabrique():
        clients.append(_ClientFactice())
        return clients[-1]

    return SessionsDeMission(fabrique=fabrique, **kw), clients


class TestLaContinuite:
    """Ce que le mode jetable ne peut pas offrir."""

    def test_deux_taches_de_la_meme_mission_partagent_un_agent(self):
        registre, clients = _registre()

        async def scenario():
            await registre.tour("m-1", "/ws", "tâche A")
            await registre.tour("m-1", "/ws", "tâche B")

        asyncio.run(scenario())

        assert len(clients) == 1, "un seul agent pour toute la mission"
        assert clients[0].ouvertures == ["/ws"]
        assert registre.tours_de("m-1") == 2

    def test_deux_missions_ne_se_melangent_pas(self):
        registre, clients = _registre()

        async def scenario():
            await registre.tour("m-1", "/a", "x")
            await registre.tour("m-2", "/b", "y")

        asyncio.run(scenario())

        assert len(clients) == 2

    def test_l_amorce_n_est_envoyee_qu_au_premier_tour(self):
        """L'agent tient son propre historique. Lui renvoyer le contexte de
        mission à chaque tour le compterait deux fois et gaspillerait la
        fenêtre qu'on cherche justement à ménager."""
        registre, clients = _registre()

        async def scenario():
            await registre.tour("m-1", "/ws", "A", amorce="CONTEXTE")
            await registre.tour("m-1", "/ws", "B", amorce="CONTEXTE")

        asyncio.run(scenario())

        assert clients[0].recus[0] == "CONTEXTE\n\nA"
        assert clients[0].recus[1] == "B"

    def test_un_workspace_qui_change_rouvre_la_session(self):
        """Une session porte des chemins. Les faire survivre à un changement
        de workspace, c'est les faire mentir."""
        registre, clients = _registre()

        async def scenario():
            await registre.tour("m-1", "/a", "x")
            await registre.tour("m-1", "/b", "y")

        asyncio.run(scenario())

        assert len(clients) == 2
        assert clients[0].fermetures == 1


class TestLeRepliQuiSeDit:
    """Un repli silencieux vers un agent amnésique est indiscernable d'un
    succès — c'est ce qui a laissé des missions contourner l'agent."""

    def test_sans_identifiant_de_mission_il_n_y_a_rien_a_faire_durer(self):
        registre, _ = _registre()

        ok, raison = asyncio.run(registre.disponible_pour(""))

        assert ok is False
        assert "mission" in raison

    def test_le_plafond_est_dit_avec_son_chiffre(self):
        registre, _ = _registre(plafond=1)

        async def scenario():
            await registre.tour("m-1", "/ws", "x")
            return await registre.disponible_pour("m-2")

        ok, raison = asyncio.run(scenario())

        assert ok is False
        assert "plafond 1" in raison

    def test_une_mission_deja_ouverte_passe_malgre_le_plafond(self):
        """Sinon une mission longue perdrait sa session dès qu'une autre
        remplit le plafond — soit exactement l'amnésie qu'on corrige."""
        registre, _ = _registre(plafond=1)

        async def scenario():
            await registre.tour("m-1", "/ws", "x")
            return await registre.disponible_pour("m-1")

        ok, _ = asyncio.run(scenario())

        assert ok is True

    def test_le_plafond_leve_plutot_que_d_ouvrir_en_trop(self):
        registre, _ = _registre(plafond=1)

        async def scenario():
            await registre.tour("m-1", "/ws", "x")
            await registre.tour("m-2", "/ws", "y")

        with pytest.raises(RuntimeError, match="plafond"):
            asyncio.run(scenario())


class TestLeMenage:
    def test_une_mission_active_n_est_pas_purgee(self):
        """Le pendant du test suivant : purger une mission vivante lui
        coûterait tout son contexte, sans rien dire."""
        temps = [1000.0]
        registre, clients = _registre(ttl_s=60.0, horloge=lambda: temps[0])

        async def scenario():
            await registre.tour("m-1", "/ws", "a")
            temps[0] += 30.0
            await registre.tour("m-1", "/ws", "b")
            temps[0] += 30.0          # 30 s depuis le dernier tour, pas 60
            await registre.disponible_pour("m-2")

        asyncio.run(scenario())

        assert registre.sessions_ouvertes() == 1
        assert clients[0].fermetures == 0

    def test_une_mission_inactive_est_purgee(self):
        """Sans cela, le processus agent d'une mission morte survit au
        serveur qui l'a lancée.

        L'horloge est pilotée, pas attendue. Une première version dormait
        10 ms avec un TTL nul : elle passait seule et échouait dans la
        suite complète, parce que `time.monotonic` a une résolution
        d'environ 15 ms sous Windows et que le delta pouvait valoir
        exactement zéro. Le test mesurait le tick du système."""
        temps = [1000.0]
        registre, clients = _registre(ttl_s=60.0, horloge=lambda: temps[0])

        async def scenario():
            await registre.tour("m-1", "/ws", "x")
            temps[0] += 61.0          # une minute et une seconde plus tard
            await registre.disponible_pour("m-2")

        asyncio.run(scenario())

        assert clients[0].fermetures == 1
        assert registre.sessions_ouvertes() == 0

    def test_fermer_tout_ne_laisse_rien(self):
        registre, clients = _registre()

        async def scenario():
            await registre.tour("m-1", "/a", "x")
            await registre.tour("m-2", "/b", "y")
            await registre.fermer_tout()

        asyncio.run(scenario())

        assert registre.sessions_ouvertes() == 0
        assert all(c.fermetures == 1 for c in clients)

    def test_fermer_une_mission_inconnue_ne_leve_pas(self):
        """La fermeture est appelée sur toutes les issues d'une mission, y
        compris celles où aucune session n'a jamais été ouverte."""
        registre, _ = _registre()

        asyncio.run(registre.fermer("jamais-vue"))


class TestLeModeleSuitLeRouteur:
    """Le routeur de Hermes OS choisit un modèle par tâche. Une session
    ouverte au premier modèle et jamais informée ensuite ferait de ce choix
    une décoration — et le mode jetable, lui, appliquait bien le modèle
    puisqu'il relançait tout à chaque fois. Le harnais ne doit pas régresser
    sur ce point en gagnant la continuité."""

    def test_le_modele_est_transmis_a_la_session(self):
        registre, clients = _registre()

        asyncio.run(registre.tour("m-1", "/ws", "x", modele="qwen3.5:9b-128k"))

        assert clients[0].modeles == ["qwen3.5:9b-128k"]

    def test_un_modele_inchange_ne_rebascule_pas(self):
        """Chaque bascule reconstruit l'agent côté Hermes Agent : la
        répéter à chaque tour coûterait sans rien apporter."""
        registre, clients = _registre()

        async def scenario():
            await registre.tour("m-1", "/ws", "a", modele="m")
            await registre.tour("m-1", "/ws", "b", modele="m")

        asyncio.run(scenario())

        assert clients[0].modeles == ["m"]

    def test_un_changement_de_modele_est_applique(self):
        registre, clients = _registre()

        async def scenario():
            await registre.tour("m-1", "/ws", "a", modele="petit")
            await registre.tour("m-1", "/ws", "b", modele="grand")

        asyncio.run(scenario())

        assert clients[0].modeles == ["petit", "grand"]

    def test_sans_modele_la_session_garde_le_sien(self):
        registre, clients = _registre()

        asyncio.run(registre.tour("m-1", "/ws", "x"))

        assert clients[0].modeles == []


class TestLeFluxAuFilDeLEau:
    """Une conversation ne peut pas attendre la fin du tour.

    Une tache de mission tolere qu'un tour rende tout d'un coup ; une
    conversation non — une minute d'attente muette est indiscernable d'une
    panne, et c'est ce que le chat de l'Assistant montrerait si le harnais
    ne savait qu'assembler.
    """

    def test_les_morceaux_traversent_le_registre(self):
        registre, _ = _registre()
        vus: list[tuple[str, str]] = []

        asyncio.run(registre.tour("m-1", "/ws", "x",
                                  au_fil_de_l_eau=lambda g, f: vus.append((g, f))))

        assert vus == [("reponse", "fait")]

    def test_sans_observateur_rien_ne_change(self):
        """Le chemin des missions ne doit pas payer pour celui du chat."""
        registre, clients = _registre()

        tour = asyncio.run(registre.tour("m-1", "/ws", "x"))

        assert tour.abouti and clients[0].recus == ["x"]


class _ClientQuiMeurt(_ClientFactice):
    """Un agent dont le processus meurt **une fois**, puis repart.

    C'est le scenario reel : le tube se ferme, `_echanger` leve « flux ferme
    par l'agent », et tout le contexte de la campagne part avec lui si rien
    ne le reprend.

    Le compteur est partage entre les instances, et c'est le point : une
    premiere version le portait sur chaque client, si bien que le client
    ouvert **pour la reprise** remourait aussitot. Le test echouait alors sur
    un defaut de son propre echafaudage, pas sur le code mesure.
    """

    def __init__(self, morts: list):
        super().__init__()
        self._morts = morts

    async def tour(self, texte, *, delai=0, au_fil_de_l_eau=None):
        if not self._morts:
            self._morts.append(1)
            raise RuntimeError("flux ferme par l'agent")
        return await super().tour(texte, delai=delai,
                                  au_fil_de_l_eau=au_fil_de_l_eau)


class TestLaRepriseApresIncident:
    """Un agent qui meurt a la section 18 d'un cahier ne doit pas emporter
    la campagne. L'agent persiste ses sessions : l'identifiant retenu permet
    de reprendre le contexte plutot que de repartir de rien.
    """

    def test_l_identifiant_est_retenu_et_repropose(self):
        registre, clients = _registre()

        async def scenario():
            await registre.tour("m-1", "/ws", "a")
            await registre.fermer("m-1")
            await registre.tour("m-1", "/ws", "b")

        asyncio.run(scenario())

        assert len(clients) == 2, "un nouveau processus, donc un nouveau client"
        # Le premier ouvre a neuf, le second reprend ce que le premier a rendu.
        assert clients[0].reprises == [""]
        assert clients[1].reprises == [clients[0].session_id]

    def test_un_tour_perdu_est_rejoue_une_fois(self):
        clients: list[_ClientQuiMeurt] = []
        morts: list = []

        def fabrique():
            clients.append(_ClientQuiMeurt(morts))
            return clients[-1]

        registre = SessionsDeMission(fabrique=fabrique)

        tour = asyncio.run(registre.tour("m-1", "/ws", "travail"))

        assert tour.abouti, "le tour doit aboutir apres reprise"
        assert len(clients) == 2, "la session morte doit etre rouverte"
        assert clients[1].recus == ["travail"], "le tour est rejoue tel quel"

    def test_une_panne_persistante_reste_une_panne(self):
        """Une seule reprise, et c'est delibere : reessayer en boucle sur
        une panne durable transformerait un echec lisible en attente muette
        — ce qui a deja coute une seance entiere a ce projet."""
        class _ToujoursMort(_ClientFactice):
            async def tour(self, texte, *, delai=0, au_fil_de_l_eau=None):
                raise RuntimeError("flux ferme par l'agent")

        registre = SessionsDeMission(fabrique=_ToujoursMort)

        with pytest.raises(RuntimeError, match="flux ferme"):
            asyncio.run(registre.tour("m-1", "/ws", "travail"))
