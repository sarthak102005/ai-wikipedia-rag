"""
Persistent SQLite-backed cache.

Replaces the previous `cache = {}` dict which was wiped on every restart.
Exposes the same interface (__contains__, __getitem__, __setitem__) so
rag.py requires zero changes in how it reads/writes the cache.

Storage: backend/data/cache.db
"""

import sqlite3
import json
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

CACHE_DB = DATA_DIR / "cache.db"


class PersistentCache:
    """SQLite-backed cache with a dict-like interface."""

    def __init__(self, db_path: Path):
        self.db_path = str(db_path)
        self._init_db()

    def _connect(self):
        return sqlite3.connect(self.db_path, check_same_thread=False)

    def _init_db(self):
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS cache (
                    key   TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
                """
            )
            conn.commit()

    # ---- dict-like interface ----

    def __contains__(self, key: str) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM cache WHERE key = ?", (key,)
            ).fetchone()
        return row is not None

    def __getitem__(self, key: str):
        with self._connect() as conn:
            row = conn.execute(
                "SELECT value FROM cache WHERE key = ?", (key,)
            ).fetchone()
        if row is None:
            raise KeyError(key)
        return json.loads(row[0])

    def __setitem__(self, key: str, value):
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO cache (key, value) VALUES (?, ?)",
                (key, json.dumps(value, ensure_ascii=False)),
            )
            conn.commit()

    def get(self, key: str, default=None):
        try:
            return self[key]
        except KeyError:
            return default


# Module-level singleton — imported by rag.py as `from app.cache import cache`
cache = PersistentCache(CACHE_DB)