"""
Create all 6 PostgreSQL databases automatically.
Run this FIRST, before load_6_databases.py and before running any DDL.

Requirements:
    pip install psycopg2-binary

Usage:
    python create_databases.py
"""

import psycopg2
from psycopg2 import sql
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

# ── Config ────────────────────────────────────────────────────
# Change "postgres" below to your Mac username if needed (run `whoami`)
PG_USER = "postgres"
PG_HOST = "localhost"
PG_PORT = "5432"

DATABASES = [
    "loan_users_db",
    "loans_db",
    "payments_db",
    "akb_score_db",
    "akb_history_db",
    "doc_front_db",
]

def main():
    # Connect to the default 'postgres' database to issue CREATE DATABASE commands
    conn = psycopg2.connect(
        host=PG_HOST,
        port=PG_PORT,
        user=PG_USER,
        dbname="postgres"
    )
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    cur = conn.cursor()

    # Get list of existing databases
    cur.execute("SELECT datname FROM pg_database;")
    existing = {row[0] for row in cur.fetchall()}

    for db in DATABASES:
        if db in existing:
            print(f"  ⏭️   {db} already exists, skipping")
        else:
            cur.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(db)))
            print(f"  ✅  Created {db}")

    cur.close()
    conn.close()
    print("\nDone! All databases ready.")

if __name__ == "__main__":
    main()
