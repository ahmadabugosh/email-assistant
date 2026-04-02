"""Gmail API client for fetching and sending emails."""
import base64
import logging
from typing import Optional, List, Dict, Any
from email.mime.text import MIMEText
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.service_account import Credentials
from google.auth.oauthlib.flow import InstalledAppFlow
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials as OAuth2Credentials
from google.auth.exceptions import RefreshError
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]


class GmailClient:
    """Gmail API client for reading and sending emails."""
    
    def __init__(self, credentials_path: str, token_path: str):
        """Initialize Gmail client with OAuth2."""
        self.credentials_path = credentials_path
        self.token_path = token_path
        self.service = None
        self._authenticate()
    
    def _authenticate(self) -> None:
        """Authenticate with Gmail API."""
        creds = None
        
        # Try to load existing token
        if Path(self.token_path).exists():
            creds = OAuth2Credentials.from_authorized_user_file(
                self.token_path, SCOPES
            )
        
        # If no valid credentials, get new ones
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                except RefreshError:
                    logger.warning("Token refresh failed, requesting new auth")
                    creds = self._get_new_credentials()
            else:
                creds = self._get_new_credentials()
            
            # Save token
            with open(self.token_path, "w") as f:
                f.write(creds.to_json())
        
        self.service = build("gmail", "v1", credentials=creds)
    
    def _get_new_credentials(self) -> OAuth2Credentials:
        """Get new OAuth2 credentials."""
        flow = InstalledAppFlow.from_client_secrets_file(
            self.credentials_path, SCOPES
        )
        creds = flow.run_local_server(port=0)
        return creds
    
    def get_new_emails(self, max_results: int = 50) -> List[Dict[str, Any]]:
        """
        Fetch new emails from inbox.
        Uses Gmail History API for incremental sync after initial load.
        """
        try:
            # Get recent messages from inbox
            results = self.service.users().messages().list(
                userId="me",
                q="is:inbox is:unread",
                maxResults=max_results,
            ).execute()
            
            messages = results.get("messages", [])
            emails = []
            
            for message in messages:
                email_data = self._get_message_details(message["id"])
                if email_data:
                    emails.append(email_data)
            
            return emails
        
        except HttpError as error:
            logger.error(f"Gmail API error: {error}")
            return []
    
    def _get_message_details(self, message_id: str) -> Optional[Dict[str, Any]]:
        """Get full message details by ID."""
        try:
            message = self.service.users().messages().get(
                userId="me",
                id=message_id,
                format="full",
            ).execute()
            
            headers = message["payload"]["headers"]
            subject = next(
                (h["value"] for h in headers if h["name"] == "Subject"),
                "No Subject"
            )
            sender = next(
                (h["value"] for h in headers if h["name"] == "From"),
                "Unknown"
            )
            
            # Extract body
            body = self._extract_body(message["payload"])
            
            return {
                "gmail_id": message_id,
                "message_id": message.get("id"),
                "thread_id": message.get("threadId"),
                "subject": subject,
                "sender": sender,
                "body": body,
            }
        
        except HttpError as error:
            logger.error(f"Error getting message {message_id}: {error}")
            return None
    
    def _extract_body(self, payload: Dict[str, Any]) -> str:
        """Extract body from Gmail payload."""
        body = ""
        
        if "parts" in payload:
            for part in payload["parts"]:
                if part["mimeType"] == "text/plain":
                    if "data" in part["body"]:
                        body += base64.urlsafe_b64decode(
                            part["body"]["data"]
                        ).decode("utf-8")
        else:
            if "body" in payload and "data" in payload["body"]:
                body = base64.urlsafe_b64decode(
                    payload["body"]["data"]
                ).decode("utf-8")
        
        return body.strip()
    
    def send_reply(
        self,
        to: str,
        subject: str,
        body: str,
        thread_id: str,
    ) -> bool:
        """Send email reply in Gmail thread."""
        try:
            message = MIMEText(body)
            message["to"] = to
            message["subject"] = f"Re: {subject}"
            
            raw_message = base64.urlsafe_b64encode(
                message.as_bytes()
            ).decode("utf-8")
            
            self.service.users().messages().send(
                userId="me",
                body={
                    "raw": raw_message,
                    "threadId": thread_id,
                },
            ).execute()
            
            logger.info(f"Sent reply to {to} in thread {thread_id}")
            return True
        
        except HttpError as error:
            logger.error(f"Error sending email: {error}")
            return False
    
    def mark_as_read(self, message_id: str) -> bool:
        """Mark message as read."""
        try:
            self.service.users().messages().modify(
                userId="me",
                id=message_id,
                body={"removeLabelIds": ["UNREAD"]},
            ).execute()
            return True
        except HttpError as error:
            logger.error(f"Error marking message as read: {error}")
            return False
