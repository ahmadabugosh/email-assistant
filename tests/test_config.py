"""Tests for config module."""
import pytest
from unittest.mock import patch

from src.config import Config


def test_validate_missing_keys():
    """Test that validation raises error for missing required keys."""
    with patch.object(Config, "OPENAI_API_KEY", ""):
        with pytest.raises(ValueError, match="OPENAI_API_KEY"):
            Config.validate()


def test_validate_missing_multiple_keys():
    """Test that validation reports all missing keys."""
    with patch.object(Config, "OPENAI_API_KEY", ""), \
         patch.object(Config, "SLACK_BOT_TOKEN", ""):
        with pytest.raises(ValueError, match="OPENAI_API_KEY") as exc_info:
            Config.validate()
        assert "SLACK_BOT_TOKEN" in str(exc_info.value)


def test_validate_all_present(tmp_path):
    """Test that validation passes with all keys set."""
    creds_file = tmp_path / "credentials.json"
    creds_file.write_text("{}")

    with patch.object(Config, "OPENAI_API_KEY", "sk-test"), \
         patch.object(Config, "SLACK_BOT_TOKEN", "xoxb-test"), \
         patch.object(Config, "SLACK_SIGNING_SECRET", "secret"), \
         patch.object(Config, "SLACK_CHANNEL_ID", "C123"), \
         patch.object(Config, "GOOGLE_SHEET_ID", "sheet-id"), \
         patch.object(Config, "GOOGLE_CREDENTIALS_PATH", str(creds_file)):
        assert Config.validate() is True


def test_validate_missing_credentials_file(tmp_path):
    """Test that validation fails when credentials file doesn't exist."""
    with patch.object(Config, "OPENAI_API_KEY", "sk-test"), \
         patch.object(Config, "SLACK_BOT_TOKEN", "xoxb-test"), \
         patch.object(Config, "SLACK_SIGNING_SECRET", "secret"), \
         patch.object(Config, "SLACK_CHANNEL_ID", "C123"), \
         patch.object(Config, "GOOGLE_SHEET_ID", "sheet-id"), \
         patch.object(Config, "GOOGLE_CREDENTIALS_PATH", "/nonexistent/path.json"):
        with pytest.raises(ValueError, match="credentials file not found"):
            Config.validate()
