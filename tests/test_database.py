"""Tests for database module."""
import pytest


def test_init_db(temp_db):
    """Test database initialization."""
    # Database should be created with tables
    with temp_db.get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
        tables = [row[0] for row in cursor.fetchall()]
    
    assert "emails" in tables
    assert "slack_threads" in tables
    assert "conversations" in tables


def test_insert_email_idempotent(temp_db, sample_email):
    """Test that inserting same email twice is idempotent."""
    email_id_1 = temp_db.insert_email(**sample_email)
    email_id_2 = temp_db.insert_email(**sample_email)
    
    assert email_id_1 == email_id_2


def test_get_pending_emails(temp_db, sample_email):
    """Test retrieving pending emails."""
    temp_db.insert_email(**sample_email)
    
    pending = temp_db.get_pending_emails()
    assert len(pending) == 1
    assert pending[0]["sender"] == "john@example.com"


def test_update_category(temp_db, sample_email):
    """Test updating email category."""
    email_id = temp_db.insert_email(**sample_email)
    
    temp_db.update_email_category(email_id, "Portfolio Updates")
    
    email = temp_db.get_email(email_id)
    assert email["category"] == "Portfolio Updates"


def test_update_suggested_reply(temp_db, sample_email):
    """Test updating suggested reply."""
    email_id = temp_db.insert_email(**sample_email)
    
    reply = "Thank you for your email. I will review this and respond shortly."
    temp_db.update_email_suggested_reply(email_id, reply)
    
    email = temp_db.get_email(email_id)
    assert email["suggested_reply"] == reply


def test_slack_thread_mapping(temp_db, sample_email):
    """Test slack thread to email mapping."""
    email_id = temp_db.insert_email(**sample_email)
    
    thread_id = temp_db.insert_slack_thread(
        email_id, "C123456", "1234567890.123456"
    )
    
    thread_data = temp_db.get_slack_thread_for_email(email_id)
    assert thread_data is not None
    assert thread_data["thread_ts"] == "1234567890.123456"


def test_conversation_history(temp_db):
    """Test conversation history."""
    thread_ts = "1234567890.123456"
    
    temp_db.add_conversation(thread_ts, "user", "Can you modify this?")
    temp_db.add_conversation(thread_ts, "assistant", "Sure, here's the modified version.")
    
    history = temp_db.get_conversation_history(thread_ts)
    
    assert len(history) == 2
    assert history[0]["role"] == "user"
    assert history[1]["role"] == "assistant"


def test_mark_email_ignored(temp_db, sample_email):
    """Test marking email as ignored."""
    email_id = temp_db.insert_email(**sample_email)

    temp_db.mark_email_ignored(email_id)

    email = temp_db.get_email(email_id)
    assert email["status"] == "ignored"


def test_gmail_state_history_id(temp_db):
    """Test history ID storage and retrieval."""
    assert temp_db.get_last_history_id() is None

    temp_db.update_history_id("12345")
    assert temp_db.get_last_history_id() == "12345"

    temp_db.update_history_id("67890")
    assert temp_db.get_last_history_id() == "67890"


def test_insert_email_with_recipients(temp_db, sample_email):
    """Test inserting email with recipients JSON."""
    import json
    recipients = json.dumps({"to": "a@test.com", "cc": "b@test.com", "reply_to": ""})
    email_id = temp_db.insert_email(**sample_email, recipients_json=recipients)

    email = temp_db.get_email(email_id)
    assert email["recipients_json"] == recipients
    parsed = json.loads(email["recipients_json"])
    assert parsed["cc"] == "b@test.com"
