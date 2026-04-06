"""Slack bot for email notifications and user interaction."""
import json
import logging
import re
from typing import Dict, Any, Optional, Tuple

from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from slack_bolt.response import BoltResponse

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
        gmail_client=None,
        slack_app_token: str = "",
    ):
        """Initialize Slack bot."""
        self.app = App(token=bot_token, signing_secret=signing_secret)
        self.channel_id = channel_id
        self.database = database
        self.email_processor = email_processor
        self.gmail_client = gmail_client
        self.app_token = slack_app_token

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
        """Send email notification to Slack.

        Posts a compact summary as the top-level message, then puts
        the full body, suggested reply, and action buttons inside
        the thread so the channel stays clean.
        """
        subject = email.get("subject", "No Subject")
        sender = email.get("sender", "Unknown")
        date = email.get("date", "Unknown")
        body_preview = email.get("body", "")[:500]

        # ── Top-level message: compact summary ──
        summary_blocks = [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"📧 *New Email* — _{category}_",
                },
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*From:* {sender}"},
                    {"type": "mrkdwn", "text": f"*Received:* {date}"},
                ],
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Subject:* {subject}",
                },
            },
        ]

        # ── Thread message: full details + actions ──
        detail_blocks = [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Email Body:*\n```{body_preview}```",
                },
            },
            {"type": "divider"},
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Suggested Reply:*\n```{suggested_reply}```",
                },
            },
            {"type": "divider"},
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "Send"},
                        "value": str(email_db_id),
                        "action_id": "send_email",
                        "style": "primary",
                    },
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "Edit"},
                        "value": str(email_db_id),
                        "action_id": "edit_email",
                    },
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "Ignore"},
                        "value": str(email_db_id),
                        "action_id": "ignore_email",
                        "style": "danger",
                    },
                ],
            },
        ]

        try:
            # Post summary to channel
            response = self.app.client.chat_postMessage(
                channel=self.channel_id,
                blocks=summary_blocks,
                text=f"New email from {sender}: {subject}",
            )
            thread_ts = response["ts"]

            # Post details inside the thread
            detail_response = self.app.client.chat_postMessage(
                channel=self.channel_id,
                thread_ts=thread_ts,
                blocks=detail_blocks,
                text=f"Suggested reply for: {subject}",
            )
            detail_message_ts = detail_response["ts"]

            self.database.insert_slack_thread(
                email_db_id, self.channel_id, thread_ts,
                detail_message_ts=detail_message_ts,
            )

            logger.info(f"Posted email notification to Slack (thread: {thread_ts})")
            return thread_ts

        except Exception as e:
            logger.error(f"Error posting to Slack: {e}")
            raise
    
    def send_followup_notification(
        self,
        email: Dict[str, Any],
        category: str,
        suggested_reply: str,
        email_db_id: int,
        existing_thread_ts: str,
    ) -> str:
        """Post a follow-up email into an existing Slack thread."""
        sender = email.get("sender", "Unknown")
        date = email.get("date", "Unknown")
        body_preview = email.get("body", "")[:500]

        blocks = [
            {"type": "divider"},
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*New Reply* from {sender} — _{category}_\n*Received:* {date}",
                },
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Email Body:*\n```{body_preview}```",
                },
            },
            {"type": "divider"},
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Suggested Reply:*\n```{suggested_reply}```",
                },
            },
            {"type": "divider"},
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "Send"},
                        "value": str(email_db_id),
                        "action_id": "send_email",
                        "style": "primary",
                    },
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "Edit"},
                        "value": str(email_db_id),
                        "action_id": "edit_email",
                    },
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "Ignore"},
                        "value": str(email_db_id),
                        "action_id": "ignore_email",
                        "style": "danger",
                    },
                ],
            },
        ]

        try:
            detail_response = self.app.client.chat_postMessage(
                channel=self.channel_id,
                thread_ts=existing_thread_ts,
                blocks=blocks,
                text=f"New reply from {sender}",
            )
            detail_message_ts = detail_response["ts"]

            # Map this email to the existing thread
            self.database.insert_slack_thread(
                email_db_id, self.channel_id, existing_thread_ts,
                detail_message_ts=detail_message_ts,
            )

            logger.info(f"Posted follow-up in existing thread: {existing_thread_ts}")
            return existing_thread_ts

        except Exception as e:
            logger.error(f"Error posting follow-up to Slack: {e}")
            raise

    def post_updated_reply(self, thread_ts: str, updated_reply: str, email_db_id: int) -> None:
        """Post updated reply in thread with action buttons."""
        blocks = [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Updated Suggested Reply:*\n```{updated_reply}```",
                },
            },
            {"type": "divider"},
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "Send"},
                        "value": str(email_db_id),
                        "action_id": "send_email",
                        "style": "primary",
                    },
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "Edit"},
                        "value": str(email_db_id),
                        "action_id": "edit_email",
                    },
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "Ignore"},
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
                thread_ts=thread_ts,
                blocks=blocks,
                text=f"Updated Suggested Reply",
            )
            # Update detail_message_ts so Send replaces this message
            self.database.update_detail_message_ts(email_db_id, response["ts"])
        except Exception as e:
            logger.error(f"Error posting updated reply: {e}")
    
    def _get_thread_ts_for_action(self, body: Dict[str, Any]) -> Tuple[int, Optional[str]]:
        """Extract email_db_id and look up thread_ts from an action body."""
        email_db_id = int(body["actions"][0]["value"])
        thread_data = self.database.get_slack_thread_for_email(email_db_id)
        thread_ts = thread_data["thread_ts"] if thread_data else None
        return email_db_id, thread_ts

    def _on_send_email(self, body: Dict[str, Any]) -> None:
        """Handle send email action."""
        email_db_id, thread_ts = self._get_thread_ts_for_action(body)

        email = self.database.get_email(email_db_id)
        if not email:
            logger.error(f"Email {email_db_id} not found")
            return

        reply_text = email["suggested_reply"]
        self.database.update_email_final_reply(email_db_id, reply_text)

        # Send the email via Gmail
        success = False
        if self.gmail_client:
            recipients = json.loads(email.get("recipients_json") or "{}")
            in_reply_to = email.get("rfc_message_id", "")

            # Referral-specific routing
            if email.get("category") == "Referrals" and recipients.get("referred"):
                referred_emails = ", ".join(r["email"] for r in recipients["referred"])
                referrer_email = recipients.get("referrer_email", "")
                is_first = not self.database.has_sent_reply_in_thread(email["thread_id"])

                to_addr = referred_emails
                cc_addr = ""
                bcc_addr = referrer_email if is_first else ""
            else:
                to_addr = recipients.get("reply_to") or email["sender"]
                cc_addr = recipients.get("cc", "")
                bcc_addr = ""

            success = self.gmail_client.send_reply(
                to=to_addr,
                subject=email["subject"],
                body=reply_text,
                thread_id=email["thread_id"],
                cc=cc_addr,
                bcc=bcc_addr,
                in_reply_to=in_reply_to,
            )

        logger.info(f"Email {email_db_id}: {'sent' if success else 'failed'}")

        # Replace the detail message in Slack with sent confirmation
        thread_data = self.database.get_slack_thread_for_email(email_db_id)
        detail_ts = thread_data.get("detail_message_ts") if thread_data else None

        if detail_ts and success:
            sent_blocks = [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*Sent Reply:*\n```{reply_text}```",
                    },
                },
            ]
            try:
                self.app.client.chat_update(
                    channel=self.channel_id,
                    ts=detail_ts,
                    blocks=sent_blocks,
                    text=f"Sent reply to: {email['subject']}",
                )
            except Exception as e:
                logger.error(f"Error updating detail message: {e}")
        elif thread_ts:
            status_msg = "Email sent successfully." if success else "Failed to send email."
            try:
                self.app.client.chat_postMessage(
                    channel=self.channel_id,
                    thread_ts=thread_ts,
                    text=status_msg,
                )
            except Exception as e:
                logger.error(f"Error posting send confirmation: {e}")

    def _on_edit_email(self, body: Dict[str, Any]) -> None:
        """Handle edit email action (show prompt)."""
        email_db_id, thread_ts = self._get_thread_ts_for_action(body)
        if not thread_ts:
            logger.error(f"No Slack thread found for email {email_db_id}")
            return

        try:
            self.app.client.chat_postMessage(
                channel=self.channel_id,
                thread_ts=thread_ts,
                text="What would you like to change about this reply? Please describe your feedback:",
            )
        except Exception as e:
            logger.error(f"Error posting edit prompt: {e}")

    def _on_ignore_email(self, body: Dict[str, Any]) -> None:
        """Handle ignore email action."""
        email_db_id, thread_ts = self._get_thread_ts_for_action(body)
        self.database.mark_email_ignored(email_db_id)

        if thread_ts:
            try:
                self.app.client.chat_postMessage(
                    channel=self.channel_id,
                    thread_ts=thread_ts,
                    text="Email marked as ignored.",
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
        conversation_history = self.database.get_conversation_history(thread_ts)

        refined_reply = self.email_processor.refine_reply(
            email, current_reply, user_message, category,
            conversation_history=conversation_history,
        )
        
        # Update in database
        self.database.update_email_suggested_reply(email_db_id, refined_reply)
        
        # Post updated reply with action buttons
        self.post_updated_reply(thread_ts, refined_reply, email_db_id)
        
        # Add to conversation history
        self.database.add_conversation(thread_ts, "assistant", refined_reply)
    
    def start(self) -> None:
        """Start the Slack bot listener.

        Uses Socket Mode if SLACK_APP_TOKEN is set (local dev),
        otherwise logs that HTTP mode is expected (Railway / Flask).
        """
        if not self.app_token:
            logger.info(
                "SLACK_APP_TOKEN not set — running in HTTP mode. "
                "Slack events should be routed to /slack/events via Flask."
            )
            return
        logger.info("Starting Slack bot (Socket Mode)...")
        handler = SocketModeHandler(self.app, self.app_token)
        handler.start()
    
    def handle_request(self, body: str, signature: str, timestamp: str) -> BoltResponse:
        """Handle Slack request (for production)."""
        return self.app.dispatch(
            body=body,
            signature=signature,
            timestamp=timestamp,
        )
