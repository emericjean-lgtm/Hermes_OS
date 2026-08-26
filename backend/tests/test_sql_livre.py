"""Deux migrations sur six ne s'executaient pas (HOS-170).

Projet livre par la campagne Skill360, migrations executees pour de bon
contre une base en memoire :

    0002_create_audit_log.py              AUTOINCREMENT is only allowed on
                                          an INTEGER PRIMARY KEY
    20230901_create_position_training.py  unrecognized token: "#"

Et aucun des 74 tests verts du projet ne lance une migration : la section a
ete declaree verifiee au-dessus d'un schema qui ne se cree pas.

La moitie de ces tests porte sur ce qui ne doit **pas** etre signale. Un
projet qui vise PostgreSQL produirait des erreurs SQLite qui ne sont pas
des fautes, et bloquer une section pour cela serait le faux echec type.
"""
from __future__ import annotations

from backend.mission import programme, sql_livre as sql


# -- ce qui doit etre signale -----------------------------------------

def test_un_commentaire_mysql_est_refuse_partout() -> None:
    assert sql.faute_du_sql("CREATE TABLE t (a TEXT); # oups")


def test_autoincrement_mal_employe_est_refuse() -> None:
    """Le mot-cle n'existe qu'en SQLite, et il y est mal employe."""
    assert sql.faute_du_sql("CREATE TABLE t (id TEXT PRIMARY KEY AUTOINCREMENT);")


def test_une_instruction_tronquee_est_refusee() -> None:
    assert sql.faute_du_sql("CREATE TABLE t (a TEXT")


# -- ce qui ne doit **pas** l'etre ------------------------------------

def test_du_postgres_valide_n_est_pas_une_faute() -> None:
    """`SERIAL` et `JSONB` n'existent pas en SQLite et ne sont pas fautifs."""
    assert not sql.faute_du_sql("CREATE TABLE t (id SERIAL PRIMARY KEY, d JSONB);")


def test_une_fonction_d_un_autre_dialecte_n_est_pas_une_faute() -> None:
    """`DEFAULT NOW()` est du PostgreSQL valide.

    SQLite le refuse par « near "(" : syntax error » — c'est pourquoi
    `syntax error` est deliberement absent de la liste des fautes.
    """
    assert not sql.faute_du_sql("CREATE TABLE t (a TEXT DEFAULT NOW());")


def test_une_table_absente_n_est_pas_une_faute_de_syntaxe() -> None:
    assert not sql.faute_du_sql("INSERT INTO absente VALUES (1);")


def test_un_fichier_sans_sql_est_ignore() -> None:
    assert sql.faute_du_sql("") == ""
    assert sql.faute_du_sql("   \n  ") == ""


# -- l'extraction ------------------------------------------------------

def test_le_sql_d_une_migration_python_est_extrait(tmp_path) -> None:
    f = tmp_path / "0001_x.py"
    f.write_text('"""Doc."""\n\nsql = """\nCREATE TABLE t (a TEXT);\n"""\n',
                 encoding="utf-8")

    assert "CREATE TABLE" in sql.sql_du_fichier(f)


def test_un_fichier_sql_est_lu_entierement(tmp_path) -> None:
    f = tmp_path / "schema.sql"
    f.write_text("CREATE TABLE t (a TEXT);\n", encoding="utf-8")

    assert "CREATE TABLE" in sql.sql_du_fichier(f)


def test_chaque_migration_part_d_une_base_neuve(tmp_path) -> None:
    """L'ordre des migrations n'est pas ce qu'on verifie ici.

    Une migration qui reference une table creee par la precedente
    echouerait sinon, et ce serait un faux echec.
    """
    assert not sql.faute_du_sql("ALTER TABLE inexistante ADD COLUMN x TEXT;")


# -- l'incident, de bout en bout --------------------------------------

def test_le_verdict_nomme_le_fichier_et_le_motif(tmp_path) -> None:
    (tmp_path / "migrations").mkdir()
    (tmp_path / "migrations" / "0002_audit.py").write_text(
        'sql = """\nCREATE TABLE audit (id TEXT PRIMARY KEY AUTOINCREMENT);\n"""\n',
        encoding="utf-8")

    faute = sql.verdict(str(tmp_path))

    assert faute is not None
    assert faute["fichier"].endswith("0002_audit.py")
    assert "AUTOINCREMENT" in faute["motif"]


def test_la_portee_se_limite_aux_fichiers_de_la_mission(tmp_path) -> None:
    """Reprocher a une section le SQL d'une autre serait un faux echec."""
    (tmp_path / "migrations").mkdir()
    (tmp_path / "migrations" / "voisine.py").write_text(
        'sql = """CREATE TABLE t (id TEXT PRIMARY KEY AUTOINCREMENT);"""\n',
        encoding="utf-8")
    (tmp_path / "migrations" / "mienne.py").write_text(
        'sql = """CREATE TABLE u (a TEXT);"""\n', encoding="utf-8")

    assert sql.verdict(str(tmp_path),
                       touches=["migrations/mienne.py"]) is None


def test_une_section_livrant_du_sql_casse_est_bloquante() -> None:
    bloque, raison = programme.bloquant({
        "created": ["migrations/0002.py"],
        "tests": {"ran": True, "passed": True},
        "sql_casse": {"fichier": "migrations/0002.py",
                      "motif": "AUTOINCREMENT is only allowed"},
    })

    assert bloque
    assert "migrations/0002.py" in raison


def test_le_brief_dit_que_les_tests_ne_couvrent_pas_les_migrations() -> None:
    """Sans cela, l'agent repondrait « mes tests passent »."""
    brief = programme.diagnostic({
        "sql_casse": {"fichier": "m.py", "motif": "unrecognized token"},
    }, "peu importe")

    assert "m.py" in brief
    assert "migrations" in brief


def test_le_depot_lui_meme_ne_declenche_rien() -> None:
    assert sql.verdict(".") is None
