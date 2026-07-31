"""
Local Cache Manager - SQLite-based caching for offline functionality
"""

import sqlite3
import json
import time
from pathlib import Path
from typing import Dict, Optional, Any
from datetime import datetime, timedelta

DB_PATH = Path(__file__).parent.parent / "cache.db"


class CacheManager:
    """Manage local SQLite cache for search results"""

    def __init__(self, ttl_hours: int = 24):
        self.ttl_seconds = ttl_hours * 3600
        self._init_db()

    def _init_db(self):
        """Initialize SQLite database"""
        try:
            conn = sqlite3.connect(str(DB_PATH))
            cursor = conn.cursor()

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS cache (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    query_type TEXT NOT NULL,
                    query_value TEXT NOT NULL,
                    data TEXT NOT NULL,
                    timestamp REAL NOT NULL,
                    UNIQUE(query_type, query_value)
                )
            """)

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_query
                ON cache(query_type, query_value)
            """)

            conn.commit()
            conn.close()
        except Exception as e:
            print(f"Cache DB init error: {e}")

    def get(self, query_type: str, query_value: str) -> Optional[Dict]:
        """Get cached result if exists and not expired"""
        try:
            conn = sqlite3.connect(str(DB_PATH))
            cursor = conn.cursor()

            cursor.execute(
                "SELECT data, timestamp FROM cache WHERE query_type = ? AND query_value = ?",
                (query_type, query_value)
            )

            result = cursor.fetchone()
            conn.close()

            if not result:
                return None

            data, timestamp = result

            # Check if expired
            if time.time() - timestamp > self.ttl_seconds:
                self.delete(query_type, query_value)
                return None

            return json.loads(data)

        except Exception as e:
            print(f"Cache get error: {e}")
            return None

    def set(self, query_type: str, query_value: str, data: Dict):
        """Cache a search result"""
        try:
            conn = sqlite3.connect(str(DB_PATH))
            cursor = conn.cursor()

            cursor.execute(
                """
                INSERT OR REPLACE INTO cache
                (query_type, query_value, data, timestamp)
                VALUES (?, ?, ?, ?)
                """,
                (query_type, query_value, json.dumps(data), time.time())
            )

            conn.commit()
            conn.close()
        except Exception as e:
            print(f"Cache set error: {e}")

    def delete(self, query_type: str, query_value: str):
        """Delete cached result"""
        try:
            conn = sqlite3.connect(str(DB_PATH))
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM cache WHERE query_type = ? AND query_value = ?",
                (query_type, query_value)
            )
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"Cache delete error: {e}")

    def clear_expired(self):
        """Clear all expired cache entries"""
        try:
            conn = sqlite3.connect(str(DB_PATH))
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM cache WHERE ? - timestamp > ?",
                (time.time(), self.ttl_seconds)
            )
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"Cache clear error: {e}")

    def get_stats(self) -> Dict:
        """Get cache statistics"""
        try:
            conn = sqlite3.connect(str(DB_PATH))
            cursor = conn.cursor()

            cursor.execute("SELECT COUNT(*) FROM cache")
            total = cursor.fetchone()[0]

            cursor.execute("SELECT query_type, COUNT(*) FROM cache GROUP BY query_type")
            by_type = dict(cursor.fetchall())

            conn.close()

            return {"total_entries": total, "by_type": by_type}
        except Exception as e:
            print(f"Cache stats error: {e}")
            return {}
