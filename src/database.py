"""Database models and queries for email assistant."""
import sqlite3
import json
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any
from contextlib import contextmanager


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
                thread_ts TEXT UNIQUE NOT NULL,
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
            
            # Migration: add recipients_json column if missing
            try:
                cursor.execute("ALTER TABLE emails ADD COLUMN recipients_json TEXT DEFAULT ''")
            except sqlite3.OperationalError:
                pass  # Column already exists

            # Indexes for performance
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_email_gmail_id ON emails(gmail_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_email_status ON emails(status)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_slack_thread ON slack_threads(thread_ts)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_conversation_thread ON conversations(slack_thread_ts)")
    
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
    ) -> int:
        """Insert email (idempotent)."""
        with self.get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            INSERT OR IGNORE INTO emails
            (gmail_id, message_id, thread_id, sender, subject, body, recipients_json)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (gmail_id, message_id, thread_id, sender, subject, body, recipients_json))
            
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
    
    # ============ SLACK THREADS ============
    
    def insert_slack_thread(
        self,
        email_db_id: int,
        channel_id: str,
        thread_ts: str,
    ) -> int:
        """Insert slack thread mapping."""
        with self.get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            INSERT INTO slack_threads (email_db_id, channel_id, thread_ts)
            VALUES (?, ?, ?)
            """, (email_db_id, channel_id, thread_ts))
            return cursor.lastrowid
    
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
