"""Copie les données de l'ancienne base SQLite (boutique.db) vers PostgreSQL.

Usage :
    python migrate_sqlite_to_postgres.py boutique.db "postgresql://livres:MOT_DE_PASSE@localhost:5432/livres"

- Sans danger : il ne modifie JAMAIS le fichier SQLite (lecture seule).
- Refuse de s'exécuter si la base PostgreSQL contient déjà des livres ou des commandes.
- Les identifiants (id) sont conservés, puis les compteurs PostgreSQL sont recalés.
"""
import sqlite3
import sys

import psycopg

# Ordre important : les tables « parents » d'abord (clés étrangères).
TABLES = ["users", "categories", "books", "book_images", "reviews", "orders",
          "order_items", "stock_movements", "subscribers", "settings"]
HAS_ID = {t: True for t in TABLES}
HAS_ID["settings"] = False


def main(sqlite_path, pg_url):
    src = sqlite3.connect(f"file:{sqlite_path}?mode=ro", uri=True)
    src.row_factory = sqlite3.Row
    sys.path.insert(0, ".")
    import os
    os.environ["DATABASE_URL"] = pg_url
    import db  # noqa: E402  (crée aussi le schéma si besoin)

    with psycopg.connect(pg_url, autocommit=False) as pg:
        pg.execute("SELECT pg_advisory_lock(2800)")
        pg.execute(db.SCHEMA)
        pg.commit()
        for t in ("books", "orders", "users"):
            if pg.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]:
                sys.exit(f"STOP : la table « {t} » de PostgreSQL n'est pas vide. Rien n'a été copié.")

        for t in TABLES:
            rows = src.execute(f"SELECT * FROM {t}").fetchall()
            if not rows:
                print(f"{t:18} 0 ligne")
                continue
            cols = rows[0].keys()
            sql = f"INSERT INTO {t} ({', '.join(cols)}) VALUES ({', '.join(['%s'] * len(cols))})"
            with pg.cursor() as cur:
                cur.executemany(sql, [tuple(r) for r in rows])
            print(f"{t:18} {len(rows)} ligne(s) copiée(s)")
            if HAS_ID[t]:
                pg.execute(
                    f"SELECT setval(pg_get_serial_sequence('{t}', 'id'), (SELECT MAX(id) FROM {t}))")
        pg.commit()

        print("\nVérification (SQLite -> PostgreSQL) :")
        ok = True
        for t in TABLES:
            a = src.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            b = pg.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            flag = "OK " if a == b else "ERREUR"
            ok &= a == b
            print(f"  {flag} {t:18} {a} -> {b}")
        sys.exit(0 if ok else 1)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2])
