"""Slack OAuth V2 helpers."""
import logging
import os
from urllib.parse import urlencode

import requests

logger = logging.getLogger(__name__)

# Scopes needed by the bot
BOT_SCOPES = [
    "channels:read",
    "channels:history",
    "chat:write",
    "groups:read",
    "groups:history",
]


def get_authorization_url(app_url: str) -> str:
    """Return the Slack OAuth V2 authorization URL."""
    client_id = os.getenv("SLACK_CLIENT_ID", "")
    if not client_id:
        raise ValueError("SLACK_CLIENT_ID env var not set")

    redirect_uri = f"{app_url}/setup/slack/callback"
    params = {
        "client_id": client_id,
        "scope": ",".join(BOT_SCOPES),
        "redirect_uri": redirect_uri,
    }
    return f"https://slack.com/oauth/v2/authorize?{urlencode(params)}"


def handle_callback(code: str, app_url: str) -> dict:
    """Exchange OAuth code for bot token.

    Returns dict with keys: bot_token, team_id, team_name.
    """
    client_id = os.getenv("SLACK_CLIENT_ID", "")
    client_secret = os.getenv("SLACK_CLIENT_SECRET", "")
    redirect_uri = f"{app_url}/setup/slack/callback"

    resp = requests.post(
        "https://slack.com/api/oauth.v2.access",
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "code": code,
            "redirect_uri": redirect_uri,
        },
    )
    data = resp.json()

    if not data.get("ok"):
        error = data.get("error", "unknown")
        raise ValueError(f"Slack OAuth failed: {error}")

    return {
        "bot_token": data["access_token"],
        "team_id": data.get("team", {}).get("id", ""),
        "team_name": data.get("team", {}).get("name", ""),
    }
