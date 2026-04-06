"""Gmail OAuth web flow (browser redirect instead of local server)."""
import json
import logging
import os

from google_auth_oauthlib.flow import Flow

from src.web.config_store import get_data_path

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]


def _get_client_config() -> dict:
    """Build Google OAuth client config from env vars or file.

    Prefers env vars (GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET) so we
    don't need a file on Railway.  Falls back to web_credentials.json
    for local dev.
    """
    client_id = os.getenv("GOOGLE_CLIENT_ID", "")
    client_secret = os.getenv("GOOGLE_CLIENT_SECRET", "")

    if client_id and client_secret:
        return {
            "web": {
                "client_id": client_id,
                "client_secret": client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
            }
        }

    # Fall back to file
    for path in ("web_credentials.json", "credentials.json"):
        if os.path.exists(path):
            with open(path) as f:
                return json.load(f)

    raise FileNotFoundError(
        "Set GOOGLE_CLIENT_ID + GOOGLE_CLIENT_SECRET env vars, "
        "or place web_credentials.json in the project root."
    )


def get_authorization_url(app_url: str) -> tuple:
    """Return (authorization_url, state) for the Gmail consent screen."""
    redirect_uri = f"{app_url}/setup/gmail/callback"
    client_config = _get_client_config()

    flow = Flow.from_client_config(client_config, scopes=SCOPES, redirect_uri=redirect_uri)
    authorization_url, state = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
    )
    return authorization_url, state


def handle_callback(callback_url: str, state: str, app_url: str) -> str:
    """Exchange the authorization code for credentials and save token.

    Returns the path to the saved token file.
    """
    redirect_uri = f"{app_url}/setup/gmail/callback"
    client_config = _get_client_config()

    # Behind a reverse proxy (Railway, ngrok) Flask sees http:// but
    # the actual public URL is https://.  Google's oauthlib rejects
    # http callback URLs, so rewrite to match the real scheme.
    if app_url.startswith("https://") and callback_url.startswith("http://"):
        callback_url = "https://" + callback_url[len("http://"):]

    flow = Flow.from_client_config(
        client_config, scopes=SCOPES, redirect_uri=redirect_uri, state=state,
    )
    flow.fetch_token(authorization_response=callback_url)

    creds = flow.credentials
    token_path = get_data_path("token.json")

    with open(token_path, "w") as f:
        f.write(creds.to_json())
    os.chmod(token_path, 0o600)

    logger.info(f"Gmail token saved to {token_path}")
    return token_path
