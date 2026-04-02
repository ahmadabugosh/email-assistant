"""Utility functions for email assistant."""
import re
import logging
from typing import List

logger = logging.getLogger(__name__)


def extract_emails(text: str) -> List[str]:
    """Extract email addresses from text."""
    pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
    return re.findall(pattern, text)


def sanitize_for_prompt(text: str, max_length: int = 2000) -> str:
    """Sanitize text for use in LLM prompts."""
    # Remove control characters
    text = ''.join(char for char in text if ord(char) >= 32 or char in '\n\t')
    
    # Limit length
    if len(text) > max_length:
        text = text[:max_length] + "..."
    
    return text.strip()


def format_email_for_display(sender: str, subject: str, body: str) -> str:
    """Format email for Slack display."""
    body_preview = body[:150].replace('\n', ' ').strip()
    if len(body) > 150:
        body_preview += "..."
    
    return f"From: {sender}\nSubject: {subject}\nBody: {body_preview}"


def safe_dict_get(data: dict, *keys, default=None):
    """Safely get nested dictionary value."""
    for key in keys:
        if isinstance(data, dict):
            data = data.get(key)
        else:
            return default
    return data if data is not None else default
