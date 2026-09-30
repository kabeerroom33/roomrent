"""
Database abstraction layer — works with both SQLite (local) and PostgreSQL (Supabase/Render).
Set DATABASE_URL env var to a postgres:// URL to use PostgreSQL.
"""
import os
import sqlite3

DATABASE_URL = os.environ.get('DATABASE_URL', '')

# ─── detect backend ────────────────────────────────────────────────────────────
def _use_postgres():
    return bool(DATABASE_URL and DATABASE_URL.startswith(('postgres://', 'postgresql://')))


# ─── PostgreSQL helpers ─────────────────────────────────────────────────────────
def _pg_conn():
    import psycopg2
    import psycopg2.extras
    url = DATABASE_URL.replace('postgres://', 'postgresql://', 1)
    conn = psycopg2.connect(url, cursor_factory=psycopg2.extras.RealDictCursor)
    return conn


class _PgRow(dict):
    """dict wrapper that also supports attribute access like sqlite3.Row."""
    def __getitem__(self, key):
        return super().__getitem__(str(key))
    def keys(self):
        return super().keys()


# ─── Unified connection wrapper ─────────────────────────────────────────────────
class Connection:
    """
    Thin wrapper so app code stays identical regardless of backend.
    Provides .execute(), .executemany(), .fetchone(), .fetchall(), .commit(), .close().
    SQLite placeholders (?) are auto-converted to %s for postgres.
    """

    def __init__(self):
        if _use_postgres():
            self._pg = _pg_conn()
            self._cur = self._pg.cursor()
            self._backend = 'pg'
        else:
            from app_config import DB_PATH
            self._sq = sqlite3.connect(DB_PATH)
            self._sq.row_factory = sqlite3.Row
            self._backend = 'sq'

    def _fix(self, sql):
        if self._backend == 'pg':
            return sql.replace('?', '%s').replace('INTEGER PRIMARY KEY AUTOINCREMENT',
                                                   'SERIAL PRIMARY KEY')
        return sql

    def execute(self, sql, params=()):
        if self._backend == 'pg':
            self._cur.execute(self._fix(sql), params)
            return self
        else:
            self._result = self._sq.execute(self._fix(sql), params)
            return self._result

    def executemany(self, sql, seq):
        if self._backend == 'pg':
            import psycopg2.extras
            psycopg2.extras.execute_batch(self._cur, self._fix(sql), seq)
        else:
            self._sq.executemany(self._fix(sql), seq)

    def executescript(self, script):
        if self._backend == 'pg':
            # Split by ; and run each statement
            for stmt in script.split(';'):
                stmt = stmt.strip()
                if stmt:
                    self._cur.execute(stmt)
        else:
            self._sq.executescript(script)

    def fetchone(self):
        if self._backend == 'pg':
            row = self._cur.fetchone()
            return _PgRow(row) if row else None
        else:
            return self._result.fetchone()

    def fetchall(self):
        if self._backend == 'pg':
            return [_PgRow(r) for r in self._cur.fetchall()]
        else:
            return self._result.fetchall()

    def lastrowid(self):
        if self._backend == 'pg':
            self._cur.execute("SELECT lastval()")
            return self._cur.fetchone()[0]
        else:
            return self._result.lastrowid

    def commit(self):
        if self._backend == 'pg':
            self._pg.commit()
        else:
            self._sq.commit()

    def rollback(self):
        if self._backend == 'pg':
            self._pg.rollback()
        else:
            self._sq.rollback()

    def close(self):
        if self._backend == 'pg':
            self._cur.close()
            self._pg.close()
        else:
            self._sq.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, *_):
        if exc_type:
            self.rollback()
        else:
            self.commit()
        self.close()


def get_db():
    return Connection()


# ─── Schema creation ────────────────────────────────────────────────────────────
SCHEMA_PG = """
CREATE TABLE IF NOT EXISTS clients (
    id            SERIAL PRIMARY KEY,
    name          TEXT NOT NULL,
    mobile        TEXT DEFAULT '',
    room_no       TEXT DEFAULT 'Room 33',
    monthly_rent  NUMERIC(10,2) DEFAULT 525,
    active        INTEGER DEFAULT 1,
    is_hidden     INTEGER DEFAULT 0,
    notes         TEXT DEFAULT '',
    created_at    TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS payments (
    id              SERIAL PRIMARY KEY,
    client_id       INTEGER NOT NULL REFERENCES clients(id),
    year            INTEGER NOT NULL,
    month           TEXT NOT NULL,
    amount_due      NUMERIC(10,2) DEFAULT 0,
    amount_paid     NUMERIC(10,2) DEFAULT 0,
    balance         NUMERIC(10,2) DEFAULT 0,
    paid_date       TEXT,
    payment_method  TEXT DEFAULT 'cash',
    receipt_no      TEXT,
    notes           TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS old_balances (
    client_id  INTEGER PRIMARY KEY REFERENCES clients(id),
    year       INTEGER NOT NULL,
    amount     NUMERIC(10,2) DEFAULT 0
);
"""

SCHEMA_SQLITE = """
CREATE TABLE IF NOT EXISTS clients (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT NOT NULL,
    mobile        TEXT DEFAULT '',
    room_no       TEXT DEFAULT 'Room 33',
    monthly_rent  REAL DEFAULT 525,
    active        INTEGER DEFAULT 1,
    is_hidden     INTEGER DEFAULT 0,
    notes         TEXT DEFAULT '',
    created_at    TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS payments (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id       INTEGER NOT NULL,
    year            INTEGER NOT NULL,
    month           TEXT NOT NULL,
    amount_due      REAL DEFAULT 0,
    amount_paid     REAL DEFAULT 0,
    balance         REAL DEFAULT 0,
    paid_date       TEXT,
    payment_method  TEXT DEFAULT 'cash',
    receipt_no      TEXT,
    notes           TEXT DEFAULT '',
    FOREIGN KEY(client_id) REFERENCES clients(id)
);

CREATE TABLE IF NOT EXISTS old_balances (
    client_id  INTEGER NOT NULL,
    year       INTEGER NOT NULL,
    amount     REAL DEFAULT 0,
    PRIMARY KEY(client_id, year),
    FOREIGN KEY(client_id) REFERENCES clients(id)
);
"""


def init_schema():
    with get_db() as conn:
        if _use_postgres():
            conn.executescript(SCHEMA_PG)
        else:
            conn.executescript(SCHEMA_SQLITE)
        # Migrations — safe to run repeatedly
        if _use_postgres():
            conn.execute("""
                ALTER TABLE payments ADD COLUMN IF NOT EXISTS payment_method TEXT DEFAULT 'cash'
            """)
            conn.execute("""
                ALTER TABLE clients ADD COLUMN IF NOT EXISTS is_hidden INTEGER DEFAULT 0
            """)
        else:
            import sqlite3 as _sq3
            from app_config import DB_PATH
            raw = _sq3.connect(DB_PATH)
            cols_c = {r[1] for r in raw.execute('PRAGMA table_info(clients)')}
            cols_p = {r[1] for r in raw.execute('PRAGMA table_info(payments)')}
            raw.close()
            with get_db() as c2:
                if 'is_hidden' not in cols_c:
                    c2.execute('ALTER TABLE clients ADD COLUMN is_hidden INTEGER DEFAULT 0')
                if 'payment_method' not in cols_p:
                    c2.execute("ALTER TABLE payments ADD COLUMN payment_method TEXT DEFAULT 'cash'")
