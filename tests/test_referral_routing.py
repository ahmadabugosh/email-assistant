"""Tests for referral BCC routing and metadata extraction."""
import json
import pytest
from unittest.mock import MagicMock, patch


# ============ DATABASE TESTS ============


def test_has_sent_reply_in_thread_false(temp_db, sample_email):
    """No sent replies returns False."""
    temp_db.insert_email(**sample_email)
    assert temp_db.has_sent_reply_in_thread("thread_123") is False


def test_has_sent_reply_in_thread_true(temp_db, sample_email):
    """After marking as sent, returns True."""
    email_id = temp_db.insert_email(**sample_email)
    temp_db.update_email_final_reply(email_id, "reply")
    assert temp_db.has_sent_reply_in_thread("thread_123") is True


def test_has_sent_reply_in_thread_different_thread(temp_db, sample_email):
    """Sent reply in a different thread doesn't count."""
    email_id = temp_db.insert_email(**sample_email)
    temp_db.update_email_final_reply(email_id, "reply")
    assert temp_db.has_sent_reply_in_thread("other_thread") is False


def test_update_recipients_json(temp_db, sample_email):
    """Test updating recipients JSON after categorization."""
    email_id = temp_db.insert_email(**sample_email)
    new_recipients = json.dumps({
        "referrer_email": "ahmad@gmail.com",
        "referred": [{"email": "alex@test.com", "name": "Alex"}],
    })
    temp_db.update_recipients_json(email_id, new_recipients)

    email = temp_db.get_email(email_id)
    parsed = json.loads(email["recipients_json"])
    assert parsed["referrer_email"] == "ahmad@gmail.com"
    assert parsed["referred"][0]["email"] == "alex@test.com"


def test_get_latest_slack_thread(temp_db):
    """get_latest_slack_thread returns an email in the Slack thread."""
    id1 = temp_db.insert_email(
        gmail_id="g1", message_id="m1", thread_id="t1",
        sender="a@test.com", subject="Sub", body="Body",
    )
    thread_ts = "1234.5678"
    temp_db.insert_slack_thread(id1, "C1", thread_ts)

    result = temp_db.get_latest_slack_thread(thread_ts)
    assert result is not None
    assert result["email_db_id"] == id1


def test_get_latest_slack_thread_not_found(temp_db):
    """get_latest_slack_thread returns None for unknown thread."""
    assert temp_db.get_latest_slack_thread("nonexistent") is None


def test_get_slack_thread_for_gmail_thread(temp_db):
    """Thread reuse: find existing Slack thread by Gmail thread ID."""
    email_id = temp_db.insert_email(
        gmail_id="g1", message_id="m1", thread_id="gmail_thread_1",
        sender="a@test.com", subject="Sub", body="Body",
    )
    temp_db.insert_slack_thread(email_id, "C1", "slack_ts_1")

    result = temp_db.get_slack_thread_for_gmail_thread("gmail_thread_1")
    assert result is not None
    assert result["thread_ts"] == "slack_ts_1"


def test_get_slack_thread_for_gmail_thread_not_found(temp_db):
    """Returns None when no Slack thread exists for Gmail thread."""
    assert temp_db.get_slack_thread_for_gmail_thread("unknown") is None


def test_email_exists_by_rfc_id(temp_db):
    """Deduplication by RFC Message-ID."""
    temp_db.insert_email(
        gmail_id="g1", message_id="m1", thread_id="t1",
        sender="a@test.com", subject="Sub", body="Body",
        rfc_message_id="<abc123@mail.gmail.com>",
    )
    assert temp_db.email_exists_by_rfc_id("<abc123@mail.gmail.com>") is True
    assert temp_db.email_exists_by_rfc_id("<other@mail.gmail.com>") is False
    assert temp_db.email_exists_by_rfc_id("") is False


def test_slack_thread_no_unique_constraint(temp_db):
    """Multiple emails can share the same Slack thread_ts."""
    id1 = temp_db.insert_email(
        gmail_id="g1", message_id="m1", thread_id="t1",
        sender="a@test.com", subject="Sub", body="Body",
    )
    id2 = temp_db.insert_email(
        gmail_id="g2", message_id="m2", thread_id="t1",
        sender="b@test.com", subject="Re: Sub", body="Reply",
    )
    thread_ts = "shared_ts"
    temp_db.insert_slack_thread(id1, "C1", thread_ts)
    temp_db.insert_slack_thread(id2, "C1", thread_ts)

    # Both should exist
    t1 = temp_db.get_slack_thread_for_email(id1)
    t2 = temp_db.get_slack_thread_for_email(id2)
    assert t1["thread_ts"] == thread_ts
    assert t2["thread_ts"] == thread_ts


# ============ REFERRAL BCC ROUTING (SLACK BOT) ============


@pytest.fixture
def mock_slack_app():
    with patch("src.slack_bot.App") as MockApp:
        mock_app = MagicMock()
        MockApp.return_value = mock_app
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


def _setup_referral_email(temp_db, is_sent=False):
    """Helper: insert a referral email with recipients JSON."""
    recipients = json.dumps({
        "to": "advisor@company.com",
        "cc": "Alex <alex@newclient.com>",
        "reply_to": "",
        "referrer_email": "ahmad@gmail.com",
        "referrer_name": "Ahmad",
        "referred": [{"email": "alex@newclient.com", "name": "Alex"}],
    })
    email_id = temp_db.insert_email(
        gmail_id="ref_1", message_id="m_ref_1", thread_id="thread_ref_1",
        sender="Ahmad <ahmad@gmail.com>",
        subject="Referral - Alex",
        body="I'd like to introduce my friend Alex.",
        recipients_json=recipients,
    )
    temp_db.update_email_category(email_id, "Referrals")
    temp_db.update_email_suggested_reply(email_id, "Thank you for the referral.")
    thread_ts = "1111.2222"
    temp_db.insert_slack_thread(email_id, "C_TEST", thread_ts)
    if is_sent:
        temp_db.update_email_final_reply(email_id, "Sent reply")
    return email_id, thread_ts


def test_referral_first_reply_bcc_routing(slack_bot, temp_db):
    """First referral reply: to=referred, bcc=referrer, cc=empty."""
    email_id, thread_ts = _setup_referral_email(temp_db)
    slack_bot.gmail_client.send_reply.return_value = True

    body = {"actions": [{"value": str(email_id)}]}
    slack_bot._on_send_email(body)

    call_kwargs = slack_bot.gmail_client.send_reply.call_args.kwargs
    assert call_kwargs["to"] == "alex@newclient.com"
    assert call_kwargs["bcc"] == "ahmad@gmail.com"
    assert call_kwargs["cc"] == ""


def test_referral_followup_no_bcc(slack_bot, temp_db):
    """Follow-up referral reply: to=referred, bcc=empty (referrer dropped)."""
    # First email already sent
    email_id_1, thread_ts = _setup_referral_email(temp_db, is_sent=True)

    # Second email in same thread
    recipients = json.dumps({
        "to": "advisor@company.com",
        "cc": "",
        "reply_to": "",
        "referrer_email": "ahmad@gmail.com",
        "referrer_name": "Ahmad",
        "referred": [{"email": "alex@newclient.com", "name": "Alex"}],
    })
    email_id_2 = temp_db.insert_email(
        gmail_id="ref_2", message_id="m_ref_2", thread_id="thread_ref_1",
        sender="Alex <alex@newclient.com>",
        subject="Re: Referral - Alex",
        body="Thanks! I'd love to schedule a call.",
        recipients_json=recipients,
    )
    temp_db.update_email_category(email_id_2, "Referrals")
    temp_db.update_email_suggested_reply(email_id_2, "Great, let's schedule.")
    temp_db.insert_slack_thread(email_id_2, "C_TEST", thread_ts)

    slack_bot.gmail_client.send_reply.return_value = True
    body = {"actions": [{"value": str(email_id_2)}]}
    slack_bot._on_send_email(body)

    call_kwargs = slack_bot.gmail_client.send_reply.call_args.kwargs
    assert call_kwargs["to"] == "alex@newclient.com"
    assert call_kwargs["bcc"] == ""


def test_non_referral_uses_sender(slack_bot, temp_db):
    """Non-referral emails: reply to sender, preserve CC."""
    recipients = json.dumps({
        "to": "advisor@company.com",
        "cc": "manager@company.com",
        "reply_to": "",
    })
    email_id = temp_db.insert_email(
        gmail_id="gen_1", message_id="m_gen_1", thread_id="thread_gen_1",
        sender="client@example.com",
        subject="Question",
        body="I have a question.",
        recipients_json=recipients,
    )
    temp_db.update_email_category(email_id, "Other")
    temp_db.update_email_suggested_reply(email_id, "Sure, happy to help.")
    temp_db.insert_slack_thread(email_id, "C_TEST", "3333.4444")

    slack_bot.gmail_client.send_reply.return_value = True
    body = {"actions": [{"value": str(email_id)}]}
    slack_bot._on_send_email(body)

    call_kwargs = slack_bot.gmail_client.send_reply.call_args.kwargs
    assert call_kwargs["to"] == "client@example.com"
    assert call_kwargs["cc"] == "manager@company.com"
    assert call_kwargs["bcc"] == ""


def test_non_referral_uses_reply_to(slack_bot, temp_db):
    """When reply_to is set, use it instead of sender."""
    recipients = json.dumps({
        "to": "advisor@company.com",
        "cc": "",
        "reply_to": "replybox@example.com",
    })
    email_id = temp_db.insert_email(
        gmail_id="gen_2", message_id="m_gen_2", thread_id="thread_gen_2",
        sender="noreply@example.com",
        subject="Via form",
        body="Contact form submission.",
        recipients_json=recipients,
    )
    temp_db.update_email_category(email_id, "Other")
    temp_db.update_email_suggested_reply(email_id, "Thanks for reaching out.")
    temp_db.insert_slack_thread(email_id, "C_TEST", "5555.6666")

    slack_bot.gmail_client.send_reply.return_value = True
    body = {"actions": [{"value": str(email_id)}]}
    slack_bot._on_send_email(body)

    call_kwargs = slack_bot.gmail_client.send_reply.call_args.kwargs
    assert call_kwargs["to"] == "replybox@example.com"


def test_referral_multiple_referred(slack_bot, temp_db):
    """Multiple referred people: all in To field."""
    recipients = json.dumps({
        "to": "advisor@company.com",
        "cc": "Alex <alex@test.com>, Bob <bob@test.com>",
        "reply_to": "",
        "referrer_email": "ahmad@gmail.com",
        "referrer_name": "Ahmad",
        "referred": [
            {"email": "alex@test.com", "name": "Alex"},
            {"email": "bob@test.com", "name": "Bob"},
        ],
    })
    email_id = temp_db.insert_email(
        gmail_id="ref_multi", message_id="m_ref_multi", thread_id="thread_ref_multi",
        sender="Ahmad <ahmad@gmail.com>",
        subject="Referral - Alex and Bob",
        body="Meet Alex and Bob.",
        recipients_json=recipients,
    )
    temp_db.update_email_category(email_id, "Referrals")
    temp_db.update_email_suggested_reply(email_id, "Welcome!")
    temp_db.insert_slack_thread(email_id, "C_TEST", "7777.8888")

    slack_bot.gmail_client.send_reply.return_value = True
    body = {"actions": [{"value": str(email_id)}]}
    slack_bot._on_send_email(body)

    call_kwargs = slack_bot.gmail_client.send_reply.call_args.kwargs
    assert "alex@test.com" in call_kwargs["to"]
    assert "bob@test.com" in call_kwargs["to"]
    assert call_kwargs["bcc"] == "ahmad@gmail.com"


# ============ GMAIL BCC SUPPORT ============


def test_send_reply_with_bcc(gmail_client):
    """Test sending reply with BCC parameter."""
    mock_send = gmail_client.service.users().messages().send()
    mock_send.execute.return_value = {"id": "sent_1"}

    success = gmail_client.send_reply(
        to="alex@test.com",
        subject="Referral",
        body="Welcome!",
        thread_id="thread_1",
        bcc="ahmad@gmail.com",
    )

    assert success is True


@pytest.fixture
def gmail_client():
    """Create Gmail client with mocked service."""
    from src.gmail_client import GmailClient

    mock_creds = MagicMock()
    mock_creds.valid = True

    with patch("src.gmail_client.Path") as MockPath, \
         patch("src.gmail_client.OAuth2Credentials") as MockOAuth, \
         patch("src.gmail_client.build", return_value=MagicMock()):
        MockPath.return_value.exists.return_value = True
        MockOAuth.from_authorized_user_file.return_value = mock_creds
        client = GmailClient("fake_creds.json", "fake_token.json")
        client.service = MagicMock()
        return client
