"""Flask application: landing page, setup wizard, Slack events, status."""
import logging
import os

# Allow OAuth over HTTP behind a trusted reverse proxy (Railway serves
# HTTPS externally but forwards to the container over HTTP).
os.environ.setdefault("OAUTHLIB_INSECURE_TRANSPORT", "1")

from flask import Flask, redirect, render_template, request, flash, session, url_for
from slack_bolt.adapter.flask import SlackRequestHandler

from src.web.config_store import ConfigStore, get_data_path
from src.web import oauth_gmail, oauth_slack

logger = logging.getLogger(__name__)


def create_app(config_store: ConfigStore = None) -> Flask:
    """Create and configure the Flask application."""
    app = Flask(
        __name__,
        template_folder=os.path.join(os.path.dirname(__file__), "..", "..", "templates"),
        static_folder=os.path.join(os.path.dirname(__file__), "..", "..", "static"),
    )
    app.secret_key = os.getenv("FLASK_SECRET_KEY", "dev-secret-change-me")

    if config_store is None:
        config_store = ConfigStore()

    # Store references on app for access in routes
    app.config_store = config_store
    app.email_assistant = None  # Set by run_web.py after setup
    app.slack_handler = None    # Set when SlackBot is ready

    def _app_url() -> str:
        return os.getenv("APP_URL", "http://localhost:5000").rstrip("/")

    # ─── Landing ────────────────────────────────────────────
    @app.route("/")
    def landing():
        if config_store.is_configured() and config_store.gmail_token_exists():
            return redirect(url_for("status"))
        return render_template("landing.html")

    # ─── Step 1: Gmail OAuth ────────────────────────────────
    @app.route("/setup/gmail")
    def setup_gmail():
        connected = config_store.gmail_token_exists()
        return render_template("setup/step1_gmail.html", gmail_connected=connected)

    @app.route("/setup/gmail/authorize")
    def gmail_authorize():
        try:
            auth_url, state = oauth_gmail.get_authorization_url(_app_url())
            session["gmail_oauth_state"] = state
            return redirect(auth_url)
        except FileNotFoundError as e:
            flash(str(e), "error")
            return redirect(url_for("setup_gmail"))

    @app.route("/setup/gmail/callback")
    def gmail_callback():
        state = session.pop("gmail_oauth_state", None)
        if not state:
            flash("OAuth state missing. Please try again.", "error")
            return redirect(url_for("setup_gmail"))

        try:
            oauth_gmail.handle_callback(request.url, state, _app_url())
            flash("Gmail connected successfully!", "success")
        except Exception as e:
            logger.error(f"Gmail OAuth error: {e}", exc_info=True)
            flash(f"Gmail OAuth failed: {e}", "error")

        return redirect(url_for("setup_gmail"))

    # ─── Step 2: Slack OAuth ────────────────────────────────
    @app.route("/setup/slack", methods=["GET", "POST"])
    def setup_slack():
        # Check config store first, then fall back to .env
        bot_token = config_store.get("SLACK_BOT_TOKEN") or os.getenv("SLACK_BOT_TOKEN", "")
        connected = bool(bot_token)
        team_name = config_store.get("SLACK_TEAM_NAME", "")
        oauth_available = bool(os.getenv("SLACK_CLIENT_ID"))

        if request.method == "POST":
            # Manual token entry
            token = request.form.get("slack_bot_token", "").strip()
            signing_secret = request.form.get("slack_signing_secret", "").strip()
            if not token:
                flash("Bot token is required.", "error")
                return redirect(url_for("setup_slack"))
            config_store.save("SLACK_BOT_TOKEN", token)
            if signing_secret:
                config_store.save("SLACK_SIGNING_SECRET", signing_secret)
            flash("Slack token saved.", "success")
            return redirect(url_for("setup_slack"))

        # If token exists in .env but not in config store, persist it
        if bot_token and not config_store.get("SLACK_BOT_TOKEN"):
            config_store.save("SLACK_BOT_TOKEN", bot_token)
            signing = os.getenv("SLACK_SIGNING_SECRET", "")
            if signing:
                config_store.save("SLACK_SIGNING_SECRET", signing)

        return render_template(
            "setup/step2_slack.html",
            slack_connected=connected,
            team_name=team_name,
            oauth_available=oauth_available,
        )

    @app.route("/setup/slack/authorize")
    def slack_authorize():
        try:
            auth_url = oauth_slack.get_authorization_url(_app_url())
            return redirect(auth_url)
        except ValueError as e:
            flash(str(e), "error")
            return redirect(url_for("setup_slack"))

    @app.route("/setup/slack/callback")
    def slack_callback():
        code = request.args.get("code")
        error = request.args.get("error")

        if error:
            flash(f"Slack authorization denied: {error}", "error")
            return redirect(url_for("setup_slack"))

        if not code:
            flash("No authorization code received.", "error")
            return redirect(url_for("setup_slack"))

        try:
            result = oauth_slack.handle_callback(code, _app_url())
            config_store.save("SLACK_BOT_TOKEN", result["bot_token"])
            config_store.save("SLACK_TEAM_ID", result["team_id"])
            config_store.save("SLACK_TEAM_NAME", result["team_name"])
            flash(f"Slack connected! Team: {result['team_name']}", "success")
        except Exception as e:
            logger.error(f"Slack OAuth error: {e}", exc_info=True)
            flash(f"Slack OAuth failed: {e}", "error")

        return redirect(url_for("setup_slack"))

    # ─── Step 3: API Keys ──────────────────────────────────
    @app.route("/setup/keys", methods=["GET", "POST"])
    def setup_keys():
        if request.method == "POST":
            openai_key = request.form.get("openai_api_key", "").strip()
            sheet_id = request.form.get("google_sheet_id", "").strip()
            tavily_key = request.form.get("tavily_api_key", "").strip()

            if not openai_key or not sheet_id:
                flash("OpenAI API Key and Google Sheet ID are required.", "error")
                return redirect(url_for("setup_keys"))

            config_store.save("OPENAI_API_KEY", openai_key)
            config_store.save("GOOGLE_SHEET_ID", sheet_id)
            if tavily_key:
                config_store.save("TAVILY_API_KEY", tavily_key)

            flash("API keys saved.", "success")
            return redirect(url_for("setup_channel"))

        current_values = config_store.get_all()
        # Fall back to .env values for pre-filling the form
        for key in ("OPENAI_API_KEY", "GOOGLE_SHEET_ID", "TAVILY_API_KEY"):
            if key not in current_values:
                env_val = os.getenv(key, "")
                if env_val:
                    current_values[key] = env_val
        return render_template("setup/step3_keys.html", current_values=current_values)

    # ─── Step 4: Channel Selection ─────────────────────────
    @app.route("/setup/channel", methods=["GET", "POST"])
    def setup_channel():
        bot_token = config_store.get("SLACK_BOT_TOKEN") or os.getenv("SLACK_BOT_TOKEN", "")

        if request.method == "POST":
            channel_id = request.form.get("channel_id", "").strip()
            if not channel_id:
                flash("Please select a channel.", "error")
                return redirect(url_for("setup_channel"))

            config_store.save("SLACK_CHANNEL_ID", channel_id)
            return redirect(url_for("setup_complete"))

        # Fetch channels the bot is a member of
        channels = []
        if bot_token:
            try:
                from slack_sdk import WebClient
                client = WebClient(token=bot_token)
                resp = client.conversations_list(
                    types="public_channel,private_channel",
                    exclude_archived=True,
                    limit=200,
                )
                for ch in resp.get("channels", []):
                    if ch.get("is_member"):
                        channels.append({"id": ch["id"], "name": ch["name"]})
            except Exception as e:
                logger.error(f"Error fetching Slack channels: {e}")
                flash("Could not fetch channels. Is the bot installed?", "error")

        selected = config_store.get("SLACK_CHANNEL_ID", "")
        return render_template(
            "setup/step4_channel.html",
            channels=channels,
            selected_channel=selected,
        )

    # ─── Setup Complete ────────────────────────────────────
    @app.route("/setup/complete")
    def setup_complete():
        # Load config into env and start assistant if not already running
        config_store.load_into_env()
        _try_start_assistant(app)
        return render_template("setup/complete.html")

    # ─── Slack Events (HTTP mode) ──────────────────────────
    @app.route("/slack/events", methods=["POST"])
    def slack_events():
        if app.slack_handler:
            return app.slack_handler.handle(request)
        # Respond to Slack URL verification even before bot is ready
        body = request.get_json(silent=True) or {}
        if body.get("type") == "url_verification":
            return {"challenge": body.get("challenge", "")}
        return "", 200

    # ─── Status ────────────────────────────────────────────
    @app.route("/status")
    def status():
        def _check(key):
            return bool(config_store.get(key) or os.getenv(key, ""))

        checks = {
            "Gmail": config_store.gmail_token_exists(),
            "Slack Bot Token": _check("SLACK_BOT_TOKEN"),
            "Slack Channel": _check("SLACK_CHANNEL_ID"),
            "OpenAI Key": _check("OPENAI_API_KEY"),
            "Google Sheet ID": _check("GOOGLE_SHEET_ID"),
            "Assistant Running": app.email_assistant is not None,
        }
        all_ok = all(checks.values())
        return render_template("setup/status.html", checks=checks, all_ok=all_ok)

    return app


def _try_start_assistant(app: Flask) -> None:
    """Start the EmailAssistant in a background thread if not already running."""
    if app.email_assistant is not None:
        return

    try:
        # Import here to avoid circular imports
        from src.web.config_store import ConfigStore
        app.config_store.load_into_env()

        from src.main import EmailAssistant
        import asyncio
        import threading

        assistant = EmailAssistant()
        app.email_assistant = assistant

        # Expose Slack handler for HTTP mode
        from slack_bolt.adapter.flask import SlackRequestHandler
        app.slack_handler = SlackRequestHandler(assistant.slack_bot.app)

        # Run email loop in background thread
        def _run_loop():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(assistant.process_emails_loop())

        t = threading.Thread(target=_run_loop, daemon=True)
        t.start()
        logger.info("Email assistant started in background thread")

    except Exception as e:
        logger.error(f"Failed to start email assistant: {e}", exc_info=True)
        app.email_assistant = None
