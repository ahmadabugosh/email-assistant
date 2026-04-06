"""Railway-compatible config storage using SQLite."""
import os
import sqlite3
import logging
from contextlib import contextmanager
from typing import Optional

logger = logging.getLogger(__name__)

# Resolve data directory: Railway volume or local
DATA_DIR = os.getenv("DATA_DIR", ".")


def get_data_path(filename: str) -> str:
    """Get full path for a data file, respecting DATA_DIR."""
    return os.path.join(DATA_DIR, filename)


class ConfigStore:
    """Store wizard config in SQLite (persists on Railway volumes)."""

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or get_data_path("email_assistant.db")
        self._init_table()

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_table(self):
        with self._conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS app_config (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
            """)

    def save(self, key: str, value: str) -> None:
        """Save a config value."""
        with self._conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO app_config (key, value) VALUES (?, ?)",
                (key, value),
            )

    def get(self, key: str, default: str = "") -> str:
        """Get a config value."""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT value FROM app_config WHERE key = ?", (key,)
            ).fetchone()
            return row["value"] if row else default

    def get_all(self) -> dict:
        """Get all config key-value pairs."""
        with self._conn() as conn:
            rows = conn.execute("SELECT key, value FROM app_config").fetchall()
            return {row["key"]: row["value"] for row in rows}

    def delete(self, key: str) -> None:
        """Delete a config value."""
        with self._conn() as conn:
            conn.execute("DELETE FROM app_config WHERE key = ?", (key,))

    def is_configured(self) -> bool:
        """Check if minimum required config is present."""
        required = [
            "SLACK_BOT_TOKEN",
            "SLACK_CHANNEL_ID",
            "OPENAI_API_KEY",
            "GOOGLE_SHEET_ID",
        ]
        config = self.get_all()
        return all(config.get(k) for k in required)

    def gmail_token_exists(self) -> bool:
        """Check if Gmail token file exists."""
        token_path = get_data_path("token.json")
        return os.path.exists(token_path)

    def load_into_env(self) -> None:
        """Load all stored config into environment variables.

        This allows the existing Config class to work unchanged —
        it reads os.getenv() at import time.
        """
        config = self.get_all()
        for key, value in config.items():
            if value and not os.getenv(key):
                os.environ[key] = value
                logger.debug(f"Loaded {key} from config store")

        # Set token path to DATA_DIR location
        token_path = get_data_path("token.json")
        if not os.getenv("GOOGLE_TOKEN_PATH"):
            os.environ["GOOGLE_TOKEN_PATH"] = token_path

        # Set DB path to DATA_DIR location
        db_path = get_data_path("email_assistant.db")
        if not os.getenv("DB_PATH"):
            os.environ["DB_PATH"] = db_path
