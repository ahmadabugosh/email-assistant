"""Tests for Gmail client."""
import pytest
from unittest.mock import MagicMock, patch, PropertyMock

from src.gmail_client import GmailClient


@pytest.fixture
def mock_gmail_service():
    """Mock Gmail service."""
    return MagicMock()


@pytest.fixture
def gmail_client(mock_gmail_service):
    """Create Gmail client with mocked service."""
    mock_creds = MagicMock()
    mock_creds.valid = True

    with patch("src.gmail_client.Path") as MockPath, \
         patch("src.gmail_client.OAuth2Credentials") as MockOAuth, \
         patch("src.gmail_client.build", return_value=mock_gmail_service):
        MockPath.return_value.exists.return_value = True
        MockOAuth.from_authorized_user_file.return_value = mock_creds

        client = GmailClient("fake_creds.json", "fake_token.json")
        client.service = mock_gmail_service
        return client


def test_extract_body_text_plain(gmail_client):
    """Test extracting plain text body."""
    payload = {
        "parts": [
            {
                "mimeType": "text/plain",
                "body": {"data": "SGVsbG8gV29ybGQ="},  # base64: Hello World
            }
        ]
    }
    body = gmail_client._extract_body(payload)
    assert "Hello World" in body


def test_extract_body_simple(gmail_client):
    """Test extracting simple body without parts."""
    payload = {
        "body": {"data": "VGVzdCBib2R5"}  # base64: Test body
    }
    body = gmail_client._extract_body(payload)
    assert "Test body" in body


def test_extract_body_malformed(gmail_client):
    """Test extracting body with invalid base64 doesn't crash."""
    payload = {
        "body": {"data": "!!!invalid-base64!!!"}
    }
    body = gmail_client._extract_body(payload)
    assert body == ""


def test_get_new_emails(gmail_client):
    """Test full sync fetching emails with pagination."""
    # Mock getProfile for history ID
    gmail_client.service.users().getProfile.return_value.execute.return_value = {
        "historyId": "99999"
    }

    list_response = {
        "messages": [{"id": "msg_1"}, {"id": "msg_2"}]
    }
    message_response = {
        "id": "msg_1",
        "threadId": "thread_1",
        "payload": {
            "headers": [
                {"name": "Subject", "value": "Test Subject"},
                {"name": "From", "value": "sender@example.com"},
            ],
            "body": {"data": "VGVzdCBib2R5"},
        }
    }

    mock_messages = gmail_client.service.users().messages()
    mock_messages.list.return_value.execute.return_value = list_response
    mock_messages.get.return_value.execute.return_value = message_response

    emails, history_id = gmail_client.get_new_emails()

    assert len(emails) > 0
    assert emails[0]["subject"] == "Test Subject"
    assert emails[0]["sender"] == "sender@example.com"
    assert history_id == "99999"


def test_get_message_details_extracts_recipients(gmail_client):
    """Test that _get_message_details extracts To, CC, Reply-To headers."""
    message_response = {
        "id": "msg_1",
        "threadId": "thread_1",
        "payload": {
            "headers": [
                {"name": "Subject", "value": "Test"},
                {"name": "From", "value": "sender@test.com"},
                {"name": "To", "value": "recipient@test.com"},
                {"name": "Cc", "value": "cc1@test.com, cc2@test.com"},
                {"name": "Reply-To", "value": "reply@test.com"},
            ],
            "body": {"data": "VGVzdA=="},
        }
    }

    mock_messages = gmail_client.service.users().messages()
    mock_messages.get.return_value.execute.return_value = message_response

    result = gmail_client._get_message_details("msg_1")

    assert result["to"] == "recipient@test.com"
    assert result["cc"] == "cc1@test.com, cc2@test.com"
    assert result["reply_to"] == "reply@test.com"


def test_send_reply(gmail_client):
    """Test sending email reply."""
    mock_send = gmail_client.service.users().messages().send()
    mock_send.execute.return_value = {"id": "sent_msg_1"}

    success = gmail_client.send_reply(
        "recipient@example.com",
        "Original Subject",
        "My reply",
        "thread_123",
    )

    assert success is True


def test_send_reply_with_cc(gmail_client):
    """Test sending reply with CC."""
    mock_send = gmail_client.service.users().messages().send()
    mock_send.execute.return_value = {"id": "sent_msg_1"}

    success = gmail_client.send_reply(
        "recipient@example.com",
        "Original Subject",
        "My reply",
        "thread_123",
        cc="cc@example.com",
    )

    assert success is True


def test_mark_as_read(gmail_client):
    """Test marking message as read."""
    mock_modify = gmail_client.service.users().messages().modify()
    mock_modify.execute.return_value = {}

    success = gmail_client.mark_as_read("msg_123")

    assert success is True
