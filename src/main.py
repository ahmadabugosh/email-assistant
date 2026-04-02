"""Main orchestrator for email assistant."""
import asyncio
import logging
import signal
import sys
from pathlib import Path

from src.config import get_config
from src.database import Database
from src.gmail_client import GmailClient
from src.sheets_client import SheetsClient
from src.tools import ToolKit
from src.email_processor import EmailProcessor
from src.slack_bot import SlackBot

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


class EmailAssistant:
    """Main email assistant orchestrator."""
    
    def __init__(self):
        """Initialize email assistant."""
        # Load config
        self.config = get_config()
        self.config.validate()
        
        # Initialize components
        logger.info("Initializing email assistant...")
        
        self.database = Database(self.config.DB_PATH)
        
        self.gmail_client = GmailClient(
            self.config.GOOGLE_CREDENTIALS_PATH,
            self.config.GOOGLE_TOKEN_PATH,
        )
        
        self.sheets_client = SheetsClient(
            self.config.GOOGLE_SHEET_ID,
            self.config.GOOGLE_CREDENTIALS_PATH,
            self.config.GOOGLE_TOKEN_PATH,
        )
        
        self.toolkit = ToolKit(
            self.config.TAVILY_API_KEY,
            self.sheets_client,
        )
        
        self.email_processor = EmailProcessor(
            self.config.OPENAI_API_KEY,
            self.toolkit,
        )
        
        self.slack_bot = SlackBot(
            self.config.SLACK_BOT_TOKEN,
            self.config.SLACK_SIGNING_SECRET,
            self.config.SLACK_CHANNEL_ID,
            self.database,
            self.email_processor,
        )
        
        self.running = True
        logger.info("Email assistant initialized")
    
    async def process_emails_loop(self) -> None:
        """Main loop: poll for new emails and process them."""
        logger.info(f"Starting email polling loop (interval: {self.config.POLL_INTERVAL}s)")
        
        while self.running:
            try:
                await self._process_batch()
            except Exception as e:
                logger.error(f"Error in email processing loop: {e}", exc_info=True)
            
            # Wait before next poll
            await asyncio.sleep(self.config.POLL_INTERVAL)
    
    async def _process_batch(self) -> None:
        """Process one batch of emails."""
        # Fetch new emails
        emails = self.gmail_client.get_new_emails()
        
        if not emails:
            logger.debug("No new emails")
            return
        
        logger.info(f"Processing {len(emails)} new emails")
        
        for email in emails:
            try:
                await self._process_single_email(email)
            except Exception as e:
                logger.error(f"Error processing email {email.get('gmail_id')}: {e}", exc_info=True)
    
    async def _process_single_email(self, email: dict) -> None:
        """Process a single email."""
        gmail_id = email.get("gmail_id")
        subject = email.get("subject", "No Subject")
        
        logger.info(f"Processing email: {subject}")
        
        # Insert into database (idempotent)
        email_db_id = self.database.insert_email(
            gmail_id=email["gmail_id"],
            message_id=email["message_id"],
            thread_id=email["thread_id"],
            sender=email["sender"],
            subject=email["subject"],
            body=email["body"],
        )
        
        # Skip if already processed
        db_email = self.database.get_email(email_db_id)
        if db_email.get("category"):
            logger.info(f"Email {gmail_id} already processed, skipping")
            return
        
        # Categorize email
        category = self.email_processor.categorize_email(email)
        self.database.update_email_category(email_db_id, category)
        logger.info(f"Email {gmail_id} categorized as: {category}")
        
        # Generate reply
        suggested_reply = self.email_processor.generate_reply(email, category)
        self.database.update_email_suggested_reply(email_db_id, suggested_reply)
        logger.info(f"Generated reply for email {gmail_id}")
        
        # Send to Slack
        try:
            thread_ts = self.slack_bot.send_email_notification(
                email, category, suggested_reply, email_db_id
            )
            logger.info(f"Email {gmail_id} sent to Slack (thread: {thread_ts})")
        except Exception as e:
            logger.error(f"Failed to send to Slack: {e}")
            raise
        
        # Mark as read in Gmail
        self.gmail_client.mark_as_read(gmail_id)
    
    async def run(self) -> None:
        """Run the email assistant."""
        logger.info("Starting email assistant...")
        
        # Register signal handlers for graceful shutdown
        loop = asyncio.get_event_loop()
        
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, self._shutdown)
        
        try:
            # Run email processing loop
            await self.process_emails_loop()
        except Exception as e:
            logger.error(f"Fatal error: {e}", exc_info=True)
            raise
    
    def _shutdown(self) -> None:
        """Handle shutdown signal."""
        logger.info("Shutting down...")
        self.running = False


def main():
    """Entry point."""
    assistant = EmailAssistant()
    
    try:
        asyncio.run(assistant.run())
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
