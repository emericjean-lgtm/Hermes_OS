"""Une section n'invente pas une pile que le projet a déjà choisie (HOS-134).

Mesuré sur la septième file : 26 sections lancées, six exécutées, et
**trois piles dans le même projet** — 14 fichiers `.ts`, 7 `.sql`, 6 `.py`.
Le même concept écrit deux fois, dans deux langages :

    db/migrations/20240920_create_workshops.ts
    db/migrations/20240920_create_employee_table.sql
    src/models/employee.ts        ← TypeScript
    src/models/position.py        ← Python

Le §5 du cahier dit « ne pas supposer une stack, déterminer l'architecture
par inspection ». Personne ne le faisait.

C'est aussi ce qui a bloqué §11 : un `PositionAuthorization` écrit en
Python, testé comme s'il suivait les conventions du modèle TypeScript
produit trois sections plus tôt.

**La mémoire des fichiers ne suffisait pas.** Le journal (HOS-123)
transmettait ce qui avait été produit — une section suivante savait donc
qu'`employee.ts` existait, et écrivait quand même `position.py`. Ce qui
manquait n'était pas la liste des fichiers, c'était la décision qu'ils
incarnent.
"""
from __future__ import annotations

from backend.mission.pile import MINIMUM_FICHIERS, compter, contrainte, dominante
from backend.mission.programme import Section, brief_de_section


def _projet(tmp_path, *fichiers: str):
    for nom in fichiers:
        chemin = tmp_path / nom
        chemin.parent.mkdir(parents=True, exist_ok=True)
        chemin.write_text("x", encoding="utf-8")
    return str(tmp_path)


class TestLaDetectionEstMecanique:
    def test_elle_compte_ce_qui_est_sur_le_disque(self, tmp_path):
        """Aucun appel modèle : demander à un modèle quelle pile il « voit »
        rouvrirait la porte à l'invention que ce module ferme."""
        racine = _projet(tmp_path, "a.ts", "b.ts", "c.ts", "d.py")

        assert compter(racine) == {"TypeScript": 3, "Python": 1}
        assert dominante(compter(racine)) == "TypeScript"

    def test_le_sql_et_la_doc_ne_sont_pas_des_piles(self, tmp_path):
        """`.sql` accompagne n'importe quelle pile ; le compter en ferait
        une concurrente. C'est ce qui faisait apparaître « trois piles » là
        où il y en avait deux."""
        racine = _projet(tmp_path, "a.sql", "b.sql", "c.md", "d.json")

        assert compter(racine) == {}
        assert dominante(compter(racine)) is None

    def test_les_repertoires_de_travail_sont_ignores(self, tmp_path):
        racine = _projet(tmp_path, "a.ts", "node_modules/x.ts",
                         "__pycache__/y.py", ".hermes/z.py")

        assert compter(racine) == {"TypeScript": 1}


class TestOnNImposeRienSansPreuve:
    """Imposer une pile que personne n'a choisie serait exactement la
    supposition que le §5 interdit."""

    def test_un_projet_vide_ne_contraint_rien(self, tmp_path):
        assert contrainte(str(tmp_path)) == ""

    def test_un_seul_fichier_ne_fait_pas_une_architecture(self, tmp_path):
        """Une section peut légitimement écrire un script isolé sans que le
        projet ait « choisi »."""
        racine = _projet(tmp_path, "script.py")

        assert dominante(compter(racine)) is None
        assert contrainte(racine) == ""

    def test_le_seuil_est_atteint_a_trois(self, tmp_path):
        racine = _projet(tmp_path, *[f"m{i}.py" for i in range(MINIMUM_FICHIERS)])

        assert dominante(compter(racine)) == "Python"

    def test_sans_workspace_rien_n_est_dit(self):
        assert contrainte(None) == ""
        assert compter(None) == {}


class TestCeQueLaSectionLit:
    def test_la_pile_est_nommee_avec_la_mesure_qui_la_fonde(self, tmp_path):
        """« Mesuré sur le disque » plutôt qu'une préférence : la pile n'a
        pas été choisie par l'outil, elle y est."""
        racine = _projet(tmp_path, "a.ts", "b.ts", "c.ts")

        texte = contrainte(racine)

        assert "TypeScript" in texte
        assert "mesuré sur le disque" in texte
        assert "3 fichier(s) TypeScript" in texte

    def test_le_melange_est_nomme_comme_un_defaut(self, tmp_path):
        """Le cas mesuré. Sans ça, une section voyant deux langages peut
        conclure que le projet en accepte plusieurs."""
        racine = _projet(tmp_path, "a.ts", "b.ts", "c.ts", "d.py", "e.py")

        texte = contrainte(racine)

        assert "défaut de ce projet" in texte
        assert "n'en ajoute pas un troisième" in texte

    def test_changer_de_pile_reste_possible_mais_doit_se_dire(self, tmp_path):
        """Interdire fabriquerait de faux échecs : une étape peut avoir une
        vraie raison. Elle doit l'écrire, pas le faire en silence."""
        racine = _projet(tmp_path, "a.ts", "b.ts", "c.ts")

        assert "explicitement dans ton document de décisions" in contrainte(racine)

    def test_la_contrainte_atteint_le_brief(self, tmp_path):
        racine = _projet(tmp_path, "a.ts", "b.ts", "c.ts")

        brief = brief_de_section(Section(11, "POSITIONS", "corps"),
                                 nom_du_cahier="SPEC.md",
                                 pile=contrainte(racine))

        assert "TypeScript" in brief

    def test_sans_pile_le_brief_ne_change_pas(self, tmp_path):
        """Un brief qui annoncerait une pile vide serait pire que muet."""
        brief = brief_de_section(Section(11, "T", "corps"),
                                 nom_du_cahier="SPEC.md", pile="")

        assert "déjà écrit en" not in brief
