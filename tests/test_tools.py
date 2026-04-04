"""Tests for tools module."""
import pytest
from unittest.mock import MagicMock, patch

from src.tools import ToolKit


def test_web_search_not_configured():
    """Test web search returns message when API key not set."""
    toolkit = ToolKit("", MagicMock())
    result = toolkit.web_search("test query")
    assert "not available" in result.lower()


def test_web_search_returns_results():
    """Test web search with mocked Tavily client."""
    toolkit = ToolKit("fake-key", MagicMock())
    with patch("tavily.Client") as MockClient:
        mock_client = MockClient.return_value
        mock_client.search.return_value = {
            "results": [
                {"title": "Test Result", "url": "http://test.com", "content": "snippet"}
            ]
        }
        result = toolkit.web_search("test")
        assert "Test Result" in result
        assert "http://test.com" in result


def test_web_search_no_results():
    """Test web search with no results."""
    toolkit = ToolKit("fake-key", MagicMock())
    with patch("tavily.Client") as MockClient:
        mock_client = MockClient.return_value
        mock_client.search.return_value = {"results": []}
        result = toolkit.web_search("test")
        assert "No search results" in result


def test_web_search_error():
    """Test web search handles errors gracefully."""
    toolkit = ToolKit("fake-key", MagicMock())
    with patch("tavily.Client") as MockClient:
        mock_client = MockClient.return_value
        mock_client.search.side_effect = Exception("API error")
        result = toolkit.web_search("test")
        assert "failed" in result.lower()


def test_lookup_portfolio_found():
    """Test portfolio lookup when client is found."""
    mock_sheets = MagicMock()
    mock_sheets.get_portfolio.return_value = {"client name": "John Doe"}
    mock_sheets.format_portfolio_context.return_value = "Portfolio for: John Doe"
    toolkit = ToolKit("", mock_sheets)
    result = toolkit.lookup_portfolio("John Doe")
    assert "John Doe" in result


def test_lookup_portfolio_not_found():
    """Test portfolio lookup when client is not found."""
    mock_sheets = MagicMock()
    mock_sheets.get_portfolio.return_value = None
    toolkit = ToolKit("", mock_sheets)
    result = toolkit.lookup_portfolio("Unknown Client")
    assert "No portfolio found" in result


def test_extract_recipients():
    """Test email recipient extraction from body."""
    toolkit = ToolKit("", MagicMock())
    recipients = toolkit.extract_recipients(
        "Please contact john@test.com and jane@test.com for details.",
        "sender@example.com",
    )
    assert "sender@example.com" in recipients
    assert "john@test.com" in recipients
    assert "jane@test.com" in recipients


def test_extract_recipients_no_emails_in_body():
    """Test recipient extraction with no emails in body."""
    toolkit = ToolKit("", MagicMock())
    recipients = toolkit.extract_recipients(
        "No email addresses here.",
        "sender@example.com",
    )
    assert recipients == ["sender@example.com"]
