"""Slack bot for email notifications and user interaction."""
import logging
from typing import Dict, Any

from slack_bolt import App
from slack_bolt.response import Response

logger = logging.getLogger(__name__)


class SlackBot:
    """Slack bot for user interaction."""
    
    def __init__(
        self,
        bot_token: str,
        signing_secret: str,
        channel_id: str,
        database,
        email_processor,
    ):
        """Initialize Slack bot."""
        self.app = App(token=bot_token, signing_secret=signing_secret)
        self.channel_id = channel_id
        self.database = database
        self.email_processor = email_processor
        
        # Register event handlers
        self._register_handlers()
    
    def _register_handlers(self):
        """Register Slack event handlers."""
        
        @self.app.action("send_email")
        def handle_send_email(ack, body, logger):
            ack()
            self._on_send_email(body)
        
        @self.app.action("edit_email")
        def handle_edit_email(ack, body, logger):
            ack()
            self._on_edit_email(body)
        
        @self.app.action("ignore_email")
        def handle_ignore_email(ack, body, logger):
            ack()
            self._on_ignore_email(body)
        
        @self.app.message(re.compile(".*"))
        def handle_message(message, say, logger):
            # Only handle messages in threads with our bot
            if "thread_ts" in message:
                self._on_thread_message(message, say)
    
    def send_email_notification(
        self,
        email: Dict[str, Any],
        category: str,
        suggested_reply: str,
        email_db_id: int,
    ) -> str:
        """Send email notification to Slack with action buttons."""
        
        # Format email preview
        subject = email.get("subject", "No Subject")
        sender = email.get("sender", "Unknown")
        body_preview = email.get("body", "")[:200]
        
        # Create message with blocks
        blocks = [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"📧 *New Email* — {category}",
                },
            },
            {
                "type": "divider",
            },
            {
                "type": "section",
                "fields": [
                    {
                        "type": "mrkdwn",
                        "text": f"*From:*\n{sender}",
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Category:*\n{category}",
                    },
                ],
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Subject:*\n{subject}",
                },
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Preview:*\n```{body_preview}```",
                },
            },
            {
                "type": "divider",
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Suggested Reply:*\n```{suggested_reply}```",
                },
            },
            {
                "type": "divider",
            },
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": "✅ Send",
                        },
                        "value": str(email_db_id),
                        "action_id": "send_email",
                        "style": "primary",
                    },
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": "✏️ Edit",
                        },
                        "value": str(email_db_id),
                        "action_id": "edit_email",
                    },
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": "🚫 Ignore",
                        },
                        "value": str(email_db_id),
                        "action_id": "ignore_email",
                        "style": "danger",
                    },
                ],
            },
        ]
        
        try:
            response = self.app.client.chat_postMessage(
                channel=self.channel_id,
                blocks=blocks,
            )
            
            thread_ts = response["ts"]
            email_db_id = self.database.insert_slack_thread(
                email_db_id, self.channel_id, thread_ts
            )
            
            logger.info(f"Posted email notification to Slack (thread: {thread_ts})")
            return thread_ts
        
        except Exception as e:
            logger.error(f"Error posting to Slack: {e}")
            raise
    
    def post_updated_reply(self, thread_ts: str, updated_reply: str) -> None:
        """Post updated reply in thread."""
        try:
            self.app.client.chat_postMessage(
                channel=self.channel_id,
                thread_ts=thread_ts,
                text=f"*Updated Suggested Reply:*\n```{updated_reply}```",
            )
        except Exception as e:
            logger.error(f"Error posting updated reply: {e}")
    
    def _on_send_email(self, body: Dict[str, Any]) -> None:
        """Handle send email action."""
        email_db_id = int(body["actions"][0]["value"])
        thread_ts = body["trigger_id"]
        
        email = self.database.get_email(email_db_id)
        if not email:
            logger.error(f"Email {email_db_id} not found")
            return
        
        # Update database
        self.database.update_email_final_reply(
            email_db_id, email["suggested_reply"]
        )
        
        # TODO: Send the email via Gmail
        logger.info(f"Email {email_db_id} marked for sending")
    
    def _on_edit_email(self, body: Dict[str, Any]) -> None:
        """Handle edit email action (show prompt)."""
        email_db_id = int(body["actions"][0]["value"])
        thread_ts = body["trigger_id"]
        
        # Post message asking for feedback
        try:
            self.app.client.chat_postMessage(
                channel=self.channel_id,
                thread_ts=thread_ts,
                text="📝 What would you like to change about this reply? Please describe your feedback:",
            )
        except Exception as e:
            logger.error(f"Error posting edit prompt: {e}")
    
    def _on_ignore_email(self, body: Dict[str, Any]) -> None:
        """Handle ignore email action."""
        email_db_id = int(body["actions"][0]["value"])
        
        self.database.mark_email_ignored(email_db_id)
        
        try:
            self.app.client.chat_postMessage(
                channel=self.channel_id,
                thread_ts=body["trigger_id"],
                text="✅ Email marked as ignored.",
            )
        except Exception as e:
            logger.error(f"Error posting ignore confirmation: {e}")
    
    def _on_thread_message(self, message: Dict[str, Any], say) -> None:
        """Handle user messages in threads."""
        thread_ts = message["thread_ts"]
        user_message = message.get("text", "")
        
        # Look up email from thread
        thread_data = self.database.get_slack_thread(thread_ts)
        if not thread_data:
            logger.warning(f"Thread {thread_ts} not found in database")
            return
        
        email_db_id = thread_data["email_db_id"]
        email = self.database.get_email(email_db_id)
        
        # Add to conversation history
        self.database.add_conversation(thread_ts, "user", user_message)
        
        # If user provided feedback, refine the reply
        category = email.get("category", "Other")
        current_reply = email.get("suggested_reply", "")
        
        refined_reply = self.email_processor.refine_reply(
            email, current_reply, user_message, category
        )
        
        # Update in database
        self.database.update_email_suggested_reply(email_db_id, refined_reply)
        
        # Post updated reply
        self.post_updated_reply(thread_ts, refined_reply)
        
        # Add to conversation history
        self.database.add_conversation(thread_ts, "assistant", refined_reply)
    
    def start(self) -> None:
        """Start the Slack bot listener."""
        logger.info("Starting Slack bot...")
        self.app.start(port=3000)
    
    def handle_request(self, body: str, signature: str, timestamp: str) -> Response:
        """Handle Slack request (for production)."""
        return self.app.dispatch(
            body=body,
            signature=signature,
            timestamp=timestamp,
        )


import re
