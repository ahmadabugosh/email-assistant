"""Database models and queries for email assistant."""
import logging
import sqlite3
import json
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any
from contextlib import contextmanager

logger = logging.getLogger(__name__)


class Database:
    """SQLite database manager."""
    
    def __init__(self, db_path: str = "email_assistant.db"):
        """Initialize database."""
        self.db_path = db_path
        self.init_db()
    
    def _get_connection(self) -> sqlite3.Connection:
        """Get database connection."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn
    
    @contextmanager
    def get_db(self):
        """Context manager for database connections."""
        conn = self._get_connection()
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()
    
    def init_db(self) -> None:
        """Initialize database tables."""
        with self.get_db() as conn:
            cursor = conn.cursor()
            
            # Emails table
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS emails (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                gmail_id TEXT UNIQUE NOT NULL,
                message_id TEXT NOT NULL,
                thread_id TEXT NOT NULL,
                sender TEXT NOT NULL,
                subject TEXT NOT NULL,
                body TEXT NOT NULL,
                category TEXT,
                suggested_reply TEXT,
                final_reply TEXT,
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """)
            
            # Slack threads table
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS slack_threads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email_db_id INTEGER UNIQUE NOT NULL,
                channel_id TEXT NOT NULL,
                thread_ts TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(email_db_id) REFERENCES emails(id)
            )
            """)
            
            # Conversations table (for chat history in threads)
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                slack_thread_ts TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """)
            
            # Gmail history tracking
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS gmail_state (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                last_history_id TEXT,
                last_check TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """)
            
            # Migrations: add columns if missing
            for migration in [
                "ALTER TABLE emails ADD COLUMN recipients_json TEXT DEFAULT ''",
                "ALTER TABLE emails ADD COLUMN rfc_message_id TEXT DEFAULT ''",
                "ALTER TABLE slack_threads ADD COLUMN detail_message_ts TEXT DEFAULT ''",
            ]:
                try:
                    cursor.execute(migration)
                except sqlite3.OperationalError:
                    pass  # Column already exists

            # Migration: drop UNIQUE constraint on slack_threads.thread_ts
            # (CREATE TABLE IF NOT EXISTS won't alter an existing table's schema)
            try:
                cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='slack_threads'")
                row = cursor.fetchone()
                if row and "UNIQUE" in (row[0] or "").upper() and "thread_ts" in (row[0] or "").lower():
                    cursor.execute("""
                    CREATE TABLE slack_threads_new (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        email_db_id INTEGER UNIQUE NOT NULL,
                        channel_id TEXT NOT NULL,
                        thread_ts TEXT NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        detail_message_ts TEXT DEFAULT '',
                        FOREIGN KEY(email_db_id) REFERENCES emails(id)
                    )
                    """)
                    cursor.execute("""
                    INSERT INTO slack_threads_new (id, email_db_id, channel_id, thread_ts, created_at, detail_message_ts)
                    SELECT id, email_db_id, channel_id, thread_ts, created_at, detail_message_ts
                    FROM slack_threads
                    """)
                    cursor.execute("DROP TABLE slack_threads")
                    cursor.execute("ALTER TABLE slack_threads_new RENAME TO slack_threads")
                    logger.info("Migrated slack_threads: removed UNIQUE constraint on thread_ts")
            except sqlite3.OperationalError as e:
                logger.warning(f"slack_threads migration check: {e}")

            # Indexes for performance
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_email_gmail_id ON emails(gmail_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_email_status ON emails(status)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_email_thread_id ON emails(thread_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_slack_thread ON slack_threads(thread_ts)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_conversation_thread ON conversations(slack_thread_ts)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_email_rfc_message_id ON emails(rfc_message_id)")
    
    # ============ EMAILS ============
    
    def insert_email(
        self,
        gmail_id: str,
        message_id: str,
        thread_id: str,
        sender: str,
        subject: str,
        body: str,
        recipients_json: str = "",
        rfc_message_id: str = "",
    ) -> int:
        """Insert email (idempotent)."""
        with self.get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            INSERT OR IGNORE INTO emails
            (gmail_id, message_id, thread_id, sender, subject, body, recipients_json, rfc_message_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (gmail_id, message_id, thread_id, sender, subject, body, recipients_json, rfc_message_id))

            # Get the ID (either newly inserted or existing)
            cursor.execute("SELECT id FROM emails WHERE gmail_id = ?", (gmail_id,))
            row = cursor.fetchone()
            return row["id"] if row else -1
    
    def get_pending_emails(self) -> List[Dict[str, Any]]:
        """Get all pending emails."""
        with self.get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            SELECT * FROM emails
            WHERE status = 'pending' AND category IS NULL
            ORDER BY created_at ASC
            """)
            return [dict(row) for row in cursor.fetchall()]
    
    def update_email_category(self, email_id: int, category: str) -> None:
        """Update email category."""
        with self.get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            UPDATE emails
            SET category = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """, (category, email_id))
    
    def update_email_suggested_reply(self, email_id: int, reply: str) -> None:
        """Update suggested reply."""
        with self.get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            UPDATE emails
            SET suggested_reply = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """, (reply, email_id))
    
    def update_email_final_reply(self, email_id: int, reply: str) -> None:
        """Update final reply."""
        with self.get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            UPDATE emails
            SET final_reply = ?, status = 'sent', updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """, (reply, email_id))
    
    def mark_email_ignored(self, email_id: int) -> None:
        """Mark email as ignored."""
        with self.get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            UPDATE emails
            SET status = 'ignored', updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """, (email_id,))
    
    def get_email(self, email_id: int) -> Optional[Dict[str, Any]]:
        """Get email by ID."""
        with self.get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM emails WHERE id = ?", (email_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def email_exists_by_rfc_id(self, rfc_message_id: str) -> bool:
        """Check if an email with this RFC Message-ID already exists."""
        if not rfc_message_id:
            return False
        with self.get_db() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT 1 FROM emails WHERE rfc_message_id = ? LIMIT 1",
                (rfc_message_id,),
            )
            return cursor.fetchone() is not None
    
    def has_sent_reply_in_thread(self, thread_id: str) -> bool:
        """Check if any email in a Gmail thread has status='sent'."""
        with self.get_db() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT 1 FROM emails WHERE thread_id = ? AND status = 'sent' LIMIT 1",
                (thread_id,),
            )
            return cursor.fetchone() is not None

    def update_recipients_json(self, email_id: int, recipients_json: str) -> None:
        """Update the recipients JSON blob for an email."""
        with self.get_db() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE emails SET recipients_json = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (recipients_json, email_id),
            )

    # ============ SLACK THREADS ============
    
    def insert_slack_thread(
        self,
        email_db_id: int,
        channel_id: str,
        thread_ts: str,
        detail_message_ts: str = "",
    ) -> int:
        """Insert slack thread mapping."""
        with self.get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            INSERT INTO slack_threads (email_db_id, channel_id, thread_ts, detail_message_ts)
            VALUES (?, ?, ?, ?)
            """, (email_db_id, channel_id, thread_ts, detail_message_ts))
            return cursor.lastrowid
    
    def update_detail_message_ts(self, email_db_id: int, detail_message_ts: str) -> None:
        """Update the detail message timestamp for an email's Slack thread."""
        with self.get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            UPDATE slack_threads
            SET detail_message_ts = ?
            WHERE email_db_id = ?
            """, (detail_message_ts, email_db_id))

    def get_slack_thread(self, thread_ts: str) -> Optional[Dict[str, Any]]:
        """Get slack thread by thread_ts."""
        with self.get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            SELECT st.*, e.* FROM slack_threads st
            JOIN emails e ON st.email_db_id = e.id
            WHERE st.thread_ts = ?
            """, (thread_ts,))
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def get_slack_thread_for_gmail_thread(self, gmail_thread_id: str) -> Optional[Dict[str, Any]]:
        """Get Slack thread for a Gmail thread ID (for conversation continuity)."""
        with self.get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            SELECT st.* FROM slack_threads st
            JOIN emails e ON st.email_db_id = e.id
            WHERE e.thread_id = ?
            ORDER BY st.created_at ASC
            LIMIT 1
            """, (gmail_thread_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_slack_thread_for_email(self, email_id: int) -> Optional[Dict[str, Any]]:
        """Get slack thread for an email."""
        with self.get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            SELECT * FROM slack_threads WHERE email_db_id = ?
            """, (email_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
    
    # ============ CONVERSATIONS ============
    
    def add_conversation(
        self,
        slack_thread_ts: str,
        role: str,
        content: str,
    ) -> int:
        """Add message to conversation thread."""
        with self.get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            INSERT INTO conversations (slack_thread_ts, role, content)
            VALUES (?, ?, ?)
            """, (slack_thread_ts, role, content))
            return cursor.lastrowid
    
    def get_conversation_history(self, slack_thread_ts: str) -> List[Dict[str, str]]:
        """Get all messages in a thread."""
        with self.get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            SELECT role, content, created_at FROM conversations
            WHERE slack_thread_ts = ?
            ORDER BY created_at ASC
            """, (slack_thread_ts,))
            return [dict(row) for row in cursor.fetchall()]
    
    # ============ GMAIL STATE ============
    
    def get_last_history_id(self) -> Optional[str]:
        """Get last Gmail history ID."""
        with self.get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT last_history_id FROM gmail_state ORDER BY id DESC LIMIT 1")
            row = cursor.fetchone()
            return row["last_history_id"] if row else None
    
    def update_history_id(self, history_id: str) -> None:
        """Update Gmail history ID."""
        with self.get_db() as conn:
            cursor = conn.cursor()
            # Always insert a new record
            cursor.execute("""
            INSERT INTO gmail_state (last_history_id, last_check)
            VALUES (?, CURRENT_TIMESTAMP)
            """, (history_id,))
