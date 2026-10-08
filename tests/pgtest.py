"""Base PostgreSQL dédiée aux tests (JAMAIS la vraie base du site).

Créer une fois :  CREATE DATABASE livres_test OWNER livres;
Variable optionnelle : TEST_DATABASE_URL=postgresql://livres:motdepasse@localhost:5432/livres_test
"""
import os

TEST_URL = os.environ.get("TEST_DATABASE_URL", "postgresql://livres:livres@localhost:5432/livres_test")
if not TEST_URL.split("?")[0].rstrip("/").endswith("_test"):
    raise SystemExit("Sécurité : le nom de la base de test doit finir par _test (les tests effacent tout).")
os.environ["DATABASE_URL"] = TEST_URL   # doit être défini AVANT d'importer app / config

import psycopg  # noqa: E402


def reset():
    """Vide complètement la base de test."""
    with psycopg.connect(TEST_URL, autocommit=True) as conn:
        conn.execute("DROP SCHEMA public CASCADE")
        conn.execute("CREATE SCHEMA public")
