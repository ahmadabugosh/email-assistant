"""Pytest configuration and fixtures."""
import pytest
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.database import Database
from src.sheets_client import SheetsClient
from src.tools import ToolKit
from src.email_processor import EmailProcessor


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    
    db = Database(db_path)
    yield db
    
    # Cleanup
    Path(db_path).unlink()


@pytest.fixture
def mock_toolkit():
    """Create a mock toolkit."""
    toolkit = MagicMock(spec=ToolKit)
    toolkit.web_search.return_value = "Mock search results"
    toolkit.lookup_portfolio.return_value = "Mock portfolio data"
    return toolkit


@pytest.fixture
def email_processor(mock_toolkit):
    """Create email processor with mocked API."""
    with patch("openai.OpenAI"):
        processor = EmailProcessor("fake-key", mock_toolkit)
        processor.client = MagicMock()
        return processor


@pytest.fixture
def sample_email():
    """Sample email for testing."""
    return {
        "gmail_id": "test_123",
        "message_id": "msg_123",
        "thread_id": "thread_123",
        "sender": "john@example.com",
        "subject": "Portfolio Update - Q1 2025",
        "body": "Hi, here's the update on your portfolio for Q1...",
    }


@pytest.fixture
def sample_portfolio_email():
    """Sample portfolio update email."""
    return {
        "gmail_id": "port_123",
        "message_id": "msg_port_123",
        "thread_id": "thread_port_123",
        "sender": "advisor@bank.com",
        "subject": "Your Q1 Portfolio Performance",
        "body": "Dear client, your portfolio has grown by 5% this quarter.",
    }


@pytest.fixture
def sample_investment_email():
    """Sample investment advice email."""
    return {
        "gmail_id": "inv_123",
        "message_id": "msg_inv_123",
        "thread_id": "thread_inv_123",
        "sender": "client@email.com",
        "subject": "Should I invest in XYZ fund?",
        "body": "I'm considering investing in the Vanguard XYZ fund. What do you think?",
    }


@pytest.fixture
def sample_referral_email():
    """Sample referral email."""
    return {
        "gmail_id": "ref_123",
        "message_id": "msg_ref_123",
        "thread_id": "thread_ref_123",
        "sender": "existing_client@email.com",
        "subject": "Introduction to John and Sarah",
        "body": "Hi, I'd like to introduce you to John and Sarah who are looking for investment advice.",
    }
