import sqlite3
import os

# On Railway, mount a volume at /data and set DB_PATH=/data/app.db
DB_PATH = os.environ.get("DB_PATH", os.path.join(os.path.dirname(__file__), "app.db"))
SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "schema.sql")


def get_db():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA foreign_keys=ON")
    return con


def init_db():
    with get_db() as con:
        with open(SCHEMA_PATH) as f:
            con.executescript(f.read())
