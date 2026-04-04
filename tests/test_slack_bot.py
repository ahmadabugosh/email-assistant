"""Tests for Slack bot module."""
import pytest
from unittest.mock import MagicMock, patch


@pytest.fixture
def mock_slack_app():
    with patch("src.slack_bot.App") as MockApp:
        mock_app = MagicMock()
        MockApp.return_value = mock_app
        # Make action/message decorators return passthrough
        mock_app.action.return_value = lambda f: f
        mock_app.message.return_value = lambda f: f
        yield mock_app


@pytest.fixture
def slack_bot(mock_slack_app, temp_db):
    from src.slack_bot import SlackBot

    with patch("src.slack_bot.App", return_value=mock_slack_app):
        bot = SlackBot(
            bot_token="xoxb-test",
            signing_secret="test-secret",
            channel_id="C_TEST",
            database=temp_db,
            email_processor=MagicMock(),
            gmail_client=MagicMock(),
        )
    return bot


def _setup_email_and_thread(temp_db, sample_email):
    """Helper: insert email and slack thread, return (email_id, thread_ts)."""
    email_id = temp_db.insert_email(**sample_email)
    temp_db.update_email_suggested_reply(email_id, "Test reply")
    thread_ts = "1234567890.000001"
    temp_db.insert_slack_thread(email_id, "C_TEST", thread_ts)
    return email_id, thread_ts


def test_get_thread_ts_for_action(slack_bot, temp_db, sample_email):
    """Test helper extracts correct thread_ts from database."""
    email_id, thread_ts = _setup_email_and_thread(temp_db, sample_email)

    body = {"actions": [{"value": str(email_id)}]}
    db_id, ts = slack_bot._get_thread_ts_for_action(body)
    assert db_id == email_id
    assert ts == thread_ts


def test_get_thread_ts_for_action_missing(slack_bot, temp_db, sample_email):
    """Test helper returns None when no thread exists."""
    email_id = temp_db.insert_email(**sample_email)
    body = {"actions": [{"value": str(email_id)}]}
    db_id, ts = slack_bot._get_thread_ts_for_action(body)
    assert db_id == email_id
    assert ts is None


def test_on_send_email_uses_thread_ts_not_trigger_id(slack_bot, temp_db, sample_email):
    """Verify send handler uses database thread_ts, not trigger_id."""
    email_id, thread_ts = _setup_email_and_thread(temp_db, sample_email)

    body = {
        "actions": [{"value": str(email_id)}],
        "trigger_id": "9999.8888.xxxx",  # Should NOT be used
    }
    slack_bot._on_send_email(body)

    call_args = slack_bot.app.client.chat_postMessage.call_args
    assert call_args.kwargs["thread_ts"] == thread_ts


def test_on_send_email_calls_gmail(slack_bot, temp_db, sample_email):
    """Verify send handler actually sends via Gmail."""
    email_id, thread_ts = _setup_email_and_thread(temp_db, sample_email)
    slack_bot.gmail_client.send_reply.return_value = True

    body = {"actions": [{"value": str(email_id)}], "trigger_id": "x"}
    slack_bot._on_send_email(body)

    slack_bot.gmail_client.send_reply.assert_called_once()


def test_on_edit_email_posts_to_correct_thread(slack_bot, temp_db, sample_email):
    """Verify edit handler posts to correct thread."""
    email_id, thread_ts = _setup_email_and_thread(temp_db, sample_email)

    body = {
        "actions": [{"value": str(email_id)}],
        "trigger_id": "9999.8888.xxxx",
    }
    slack_bot._on_edit_email(body)

    call_args = slack_bot.app.client.chat_postMessage.call_args
    assert call_args.kwargs["thread_ts"] == thread_ts


def test_on_ignore_marks_email_and_posts(slack_bot, temp_db, sample_email):
    """Verify ignore handler marks email and posts to correct thread."""
    email_id, thread_ts = _setup_email_and_thread(temp_db, sample_email)

    body = {"actions": [{"value": str(email_id)}], "trigger_id": "x"}
    slack_bot._on_ignore_email(body)

    email = temp_db.get_email(email_id)
    assert email["status"] == "ignored"

    call_args = slack_bot.app.client.chat_postMessage.call_args
    assert call_args.kwargs["thread_ts"] == thread_ts


def test_on_thread_message_refines_reply(slack_bot, temp_db, sample_email):
    """Test that thread messages trigger reply refinement."""
    email_id, thread_ts = _setup_email_and_thread(temp_db, sample_email)
    temp_db.update_email_category(email_id, "Other")

    slack_bot.email_processor.refine_reply.return_value = "Refined reply"

    message = {"thread_ts": thread_ts, "text": "Make it shorter"}
    say = MagicMock()
    slack_bot._on_thread_message(message, say)

    slack_bot.email_processor.refine_reply.assert_called_once()
    email = temp_db.get_email(email_id)
    assert email["suggested_reply"] == "Refined reply"


def test_on_thread_message_passes_conversation_history(slack_bot, temp_db, sample_email):
    """Test that conversation history is passed to refine_reply."""
    email_id, thread_ts = _setup_email_and_thread(temp_db, sample_email)
    temp_db.update_email_category(email_id, "Other")
    temp_db.add_conversation(thread_ts, "user", "First feedback")
    temp_db.add_conversation(thread_ts, "assistant", "First refinement")

    slack_bot.email_processor.refine_reply.return_value = "Second refinement"

    message = {"thread_ts": thread_ts, "text": "Second feedback"}
    say = MagicMock()
    slack_bot._on_thread_message(message, say)

    call_kwargs = slack_bot.email_processor.refine_reply.call_args.kwargs
    assert "conversation_history" in call_kwargs
    # Should have previous 2 messages + the new user message
    assert len(call_kwargs["conversation_history"]) >= 2


def test_send_email_notification(slack_bot, temp_db, sample_email):
    """Test sending email notification to Slack (summary + thread detail)."""
    email_id = temp_db.insert_email(**sample_email)
    slack_bot.app.client.chat_postMessage.return_value = {"ts": "1234567890.000001"}

    thread_ts = slack_bot.send_email_notification(
        sample_email, "Other", "Test reply", email_id
    )

    assert thread_ts == "1234567890.000001"
    # Should be called twice: once for summary, once for thread detail
    assert slack_bot.app.client.chat_postMessage.call_count == 2
    # Second call should be in the thread
    second_call = slack_bot.app.client.chat_postMessage.call_args_list[1]
    assert second_call.kwargs["thread_ts"] == "1234567890.000001"
