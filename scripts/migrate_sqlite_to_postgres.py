#!/usr/bin/env python3
"""Migrate the local SQLite data into a PostgreSQL database.

Usage:
    DATABASE_URL="postgresql://user:pass@host:5432/dbname" python scripts/migrate_sqlite_to_postgres.py
    python scripts/migrate_sqlite_to_postgres.py --database-url "postgresql://..."
"""

import argparse
import os
import sqlite3
import sys
from pathlib import Path

import psycopg2
from psycopg2.extras import RealDictCursor

ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / 'rent-app'
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

SQLITE_DB = APP_DIR / 'data' / 'rent.db'


def get_db_url(cli_value: str | None) -> str:
    value = cli_value or os.environ.get('DATABASE_URL')
    if not value:
        raise SystemExit('DATABASE_URL is missing. Example: postgresql://user:pass@host:5432/dbname')
    return value.replace('postgres://', 'postgresql://', 1)


def ensure_postgres_schema(db_url: str) -> None:
    os.environ['DATABASE_URL'] = db_url
    import db
    db.init_schema()


def get_sqlite_tables(conn: sqlite3.Connection):
    return [
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )
    ]


def get_table_columns(conn: sqlite3.Connection, table: str):
    cols = conn.execute(f'PRAGMA table_info({table})').fetchall()
    return [col[1] for col in cols]


def migrate_table(sqlite_conn: sqlite3.Connection, pg_conn, table: str, pk_columns=None, replace: bool = False):
    columns = get_table_columns(sqlite_conn, table)
    if not columns:
        return

    if replace:
        with pg_conn.cursor() as cur:
            cur.execute(f'DELETE FROM {table}')

    rows = sqlite_conn.execute(f'SELECT * FROM {table} ORDER BY 1').fetchall()
    if not rows:
        print(f'No rows to migrate for {table}.')
        return

    column_sql = ', '.join(columns)
    placeholders = ', '.join(['%s'] * len(columns))
    assignments = ', '.join(f'{c} = EXCLUDED.{c}' for c in columns)

    if pk_columns:
        conflict_sql = f'ON CONFLICT ({", ".join(pk_columns)}) DO UPDATE SET {assignments}'
    else:
        conflict_sql = f'ON CONFLICT (id) DO UPDATE SET {assignments}'

    insert_sql = f'INSERT INTO {table} ({column_sql}) VALUES ({placeholders}) {conflict_sql}'

    with pg_conn.cursor() as cur:
        for row in rows:
            cur.execute(insert_sql, tuple(row))

    pg_conn.commit()
    print(f'Migrated {len(rows)} rows into {table}')


def main():
    parser = argparse.ArgumentParser(description='Copy SQLite data into Supabase/PostgreSQL.')
    parser.add_argument('--database-url', help='PostgreSQL URL like postgresql://user:pass@host:5432/dbname')
    parser.add_argument('--reset', action='store_true', help='Clear target tables before importing.')
    args = parser.parse_args()

    db_url = get_db_url(args.database_url)

    if not SQLITE_DB.exists():
        raise SystemExit(f'SQLite database not found: {SQLITE_DB}')

    sqlite_conn = sqlite3.connect(str(SQLITE_DB))
    sqlite_conn.row_factory = sqlite3.Row

    try:
        pg_conn = psycopg2.connect(db_url, cursor_factory=RealDictCursor)

        ensure_postgres_schema(db_url)

        tables = get_sqlite_tables(sqlite_conn)
        for table in tables:
            if table in {'clients', 'payments', 'old_balances'}:
                if table == 'clients':
                    migrate_table(sqlite_conn, pg_conn, table, pk_columns=['id'], replace=args.reset)
                elif table == 'payments':
                    migrate_table(sqlite_conn, pg_conn, table, pk_columns=['id'], replace=args.reset)
                elif table == 'old_balances':
                    migrate_table(sqlite_conn, pg_conn, table, pk_columns=['client_id', 'year'], replace=args.reset)

        print('\nMigration complete.')
        print(f'Local SQLite DB: {SQLITE_DB}')
        print(f'Supabase/Postgres: {db_url.split("@", 1)[1] if "@" in db_url else "configured"}')

    finally:
        sqlite_conn.close()
        pg_conn.close()


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print('\nInterrupted by user.')
        sys.exit(130)
