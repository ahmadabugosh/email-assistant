"""Configuration management for the email assistant."""
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


class Config:
    """Configuration from environment variables."""
    
    # OpenAI
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    
    # Slack
    SLACK_BOT_TOKEN: str = os.getenv("SLACK_BOT_TOKEN", "")
    SLACK_SIGNING_SECRET: str = os.getenv("SLACK_SIGNING_SECRET", "")
    SLACK_CHANNEL_ID: str = os.getenv("SLACK_CHANNEL_ID", "")
    SLACK_APP_TOKEN: str = os.getenv("SLACK_APP_TOKEN", "")
    
    # Google
    GOOGLE_CREDENTIALS_PATH: str = os.getenv("GOOGLE_CREDENTIALS_PATH", "./credentials.json")
    GOOGLE_TOKEN_PATH: str = os.getenv("GOOGLE_TOKEN_PATH", "./token.json")
    GOOGLE_SHEET_ID: str = os.getenv("GOOGLE_SHEET_ID", "")
    
    # Tavily (web search)
    TAVILY_API_KEY: str = os.getenv("TAVILY_API_KEY", "")
    
    # Polling
    POLL_INTERVAL: int = int(os.getenv("POLL_INTERVAL", "30"))
    
    # Database — use DATA_DIR volume if available (Railway), else local
    DB_PATH: str = os.getenv(
        "DB_PATH",
        os.path.join(os.getenv("DATA_DIR", "."), "email_assistant.db"),
    )
    
    @classmethod
    def validate(cls) -> bool:
        """Validate required configuration."""
        required = [
            "OPENAI_API_KEY",
            "SLACK_BOT_TOKEN",
            "SLACK_SIGNING_SECRET",
            "SLACK_CHANNEL_ID",
            "GOOGLE_SHEET_ID",
        ]
        
        missing = [key for key in required if not getattr(cls, key)]
        
        if missing:
            raise ValueError(f"Missing required config: {', '.join(missing)}")
        
        if not Path(cls.GOOGLE_CREDENTIALS_PATH).exists():
            raise ValueError(f"Google credentials file not found: {cls.GOOGLE_CREDENTIALS_PATH}")
        
        return True


def get_config() -> Config:
    """Get configuration instance."""
    return Config()
