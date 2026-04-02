"""Tests for Gmail client."""
import pytest
from unittest.mock import MagicMock, patch


@pytest.fixture
def mock_gmail_service():
    """Mock Gmail service."""
    return MagicMock()


@pytest.fixture
def gmail_client(mock_gmail_service):
    """Create Gmail client with mocked service."""
    with patch("src.gmail_client.build", return_value=mock_gmail_service):
        with patch("src.gmail_client.InstalledAppFlow"):
            from src.gmail_client import GmailClient
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


def test_get_new_emails(gmail_client):
    """Test fetching new emails."""
    # Mock the API responses
    list_response = {
        "messages": [
            {"id": "msg_1"},
            {"id": "msg_2"},
        ]
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
    
    emails = gmail_client.get_new_emails()
    
    assert len(emails) > 0
    assert emails[0]["subject"] == "Test Subject"
    assert emails[0]["sender"] == "sender@example.com"


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
    mock_send.execute.assert_called_once()


def test_mark_as_read(gmail_client):
    """Test marking message as read."""
    mock_modify = gmail_client.service.users().messages().modify()
    mock_modify.execute.return_value = {}
    
    success = gmail_client.mark_as_read("msg_123")
    
    assert success is True
    mock_modify.execute.assert_called_once()
