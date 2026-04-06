"""Entry point for the web-based email assistant.

Usage:
    Local:   python run_web.py
    Railway: gunicorn -w 1 --bind 0.0.0.0:$PORT run_web:app
"""
import logging
import os

from src.web.config_store import ConfigStore
from src.web.app import create_app, _try_start_assistant

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Initialize config store and load saved config into env
config_store = ConfigStore()
config_store.load_into_env()

# Create Flask app
app = create_app(config_store)

# If already configured, start assistant on boot
if config_store.is_configured() and config_store.gmail_token_exists():
    logger.info("Configuration found — starting email assistant automatically")
    with app.app_context():
        _try_start_assistant(app)
else:
    logger.info("Setup incomplete — visit the web UI to configure")

if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=False)
