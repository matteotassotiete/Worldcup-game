import os

DATABASE_URL = os.environ.get("DATABASE_URL")
_BASE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get("DB_PATH", os.path.join(_BASE, "app.db"))
SCHEMA_PATH = os.path.join(_BASE, "schema.sql")
SCHEMA_PG_PATH = os.path.join(_BASE, "schema_pg.sql")


if DATABASE_URL:
    import psycopg2
    import psycopg2.extras

    class _Row(dict):
        pass

    class _PgCursor:
        def __init__(self, cur):
            self._cur = cur
            self.rowcount = cur.rowcount
            self.lastrowid = None

        def fetchone(self):
            r = self._cur.fetchone()
            return _Row(r) if r else None

        def fetchall(self):
            return [_Row(r) for r in self._cur.fetchall()]

    class _PgConn:
        def __init__(self, conn):
            self._conn = conn

        def execute(self, sql, params=()):
            cur = self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute(sql, params or None)
            return _PgCursor(cur)

        def insert_returning_id(self, sql, params=()):
            """INSERT ... RETURNING id — returns the new row id."""
            cur = self._conn.cursor()
            cur.execute(sql, params or None)
            row = cur.fetchone()
            return row[0] if row else None

        def commit(self):
            self._conn.commit()

        def close(self):
            self._conn.close()

    def get_db():
        conn = psycopg2.connect(DATABASE_URL)
        conn.autocommit = False
        return _PgConn(conn)

    def init_db():
        conn = psycopg2.connect(DATABASE_URL)
        with conn.cursor() as cur:
            with open(SCHEMA_PG_PATH) as f:
                cur.execute(f.read())
        conn.commit()
        conn.close()

else:
    import sqlite3

    class _SqliteConn:
        def __init__(self, conn):
            self._conn = conn

        def execute(self, sql, params=()):
            # Convert %s placeholders to ? for SQLite
            sql = sql.replace('%s', '?')
            return self._conn.execute(sql, params)

        def insert_returning_id(self, sql, params=()):
            # Strip RETURNING clause — SQLite uses lastrowid instead
            sql = sql[:sql.upper().rfind(' RETURNING ')].rstrip()
            sql = sql.replace('%s', '?')
            cur = self._conn.execute(sql, params)
            return cur.lastrowid

        def commit(self):
            self._conn.commit()

        def close(self):
            self._conn.close()

    def get_db():
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return _SqliteConn(conn)

    def init_db():
        conn = sqlite3.connect(DB_PATH)
        with conn:
            with open(SCHEMA_PATH) as f:
                conn.executescript(f.read())
        conn.close()
