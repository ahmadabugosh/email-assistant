"""Gmail API client for fetching and sending emails."""
import base64
import logging
import os
from typing import Optional, List, Dict, Any, Tuple
from email.mime.text import MIMEText
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.service_account import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
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

            # Save token with restricted permissions
            with open(self.token_path, "w") as f:
                f.write(creds.to_json())
            os.chmod(self.token_path, 0o600)

        self.service = build("gmail", "v1", credentials=creds)

    def _get_new_credentials(self) -> OAuth2Credentials:
        """Get new OAuth2 credentials."""
        flow = InstalledAppFlow.from_client_secrets_file(
            self.credentials_path, SCOPES
        )
        creds = flow.run_local_server(port=0)
        return creds

    # ============ History API ============

    def get_current_history_id(self) -> str:
        """Get the current historyId from Gmail profile."""
        profile = self.service.users().getProfile(userId="me").execute()
        return profile["historyId"]

    def get_history_changes(self, start_history_id: str) -> Tuple[List[str], str]:
        """
        Get message IDs added to inbox since start_history_id.
        Returns (list_of_message_ids, new_history_id).
        Raises HttpError 404 if history_id is too old.
        """
        message_ids = set()
        page_token = None
        latest_history_id = start_history_id

        while True:
            kwargs = {
                "userId": "me",
                "startHistoryId": start_history_id,
                "historyTypes": ["messageAdded"],
                "labelId": "INBOX",
            }
            if page_token:
                kwargs["pageToken"] = page_token

            result = self.service.users().history().list(**kwargs).execute()
            latest_history_id = result.get("historyId", latest_history_id)

            for record in result.get("history", []):
                for msg_added in record.get("messagesAdded", []):
                    message_ids.add(msg_added["message"]["id"])

            page_token = result.get("nextPageToken")
            if not page_token:
                break

        return list(message_ids), latest_history_id

    def get_emails_by_ids(self, message_ids: List[str]) -> List[Dict[str, Any]]:
        """Fetch full email data for a list of message IDs."""
        emails = []
        for msg_id in message_ids:
            email_data = self._get_message_details(msg_id)
            if email_data:
                emails.append(email_data)
        return emails

    def get_new_emails(self, max_results: int = 500) -> Tuple[List[Dict[str, Any]], str]:
        """
        Full sync: fetch inbox emails with pagination.
        Returns (emails, current_history_id) for bootstrapping.
        """
        history_id = self.get_current_history_id()
        all_message_ids = []
        page_token = None

        try:
            while True:
                kwargs = {
                    "userId": "me",
                    "q": "is:inbox",
                    "maxResults": min(max_results - len(all_message_ids), 100),
                }
                if page_token:
                    kwargs["pageToken"] = page_token

                results = self.service.users().messages().list(**kwargs).execute()
                messages = results.get("messages", [])
                all_message_ids.extend(m["id"] for m in messages)

                page_token = results.get("nextPageToken")
                if not page_token or len(all_message_ids) >= max_results:
                    break

            emails = self.get_emails_by_ids(all_message_ids)
            return emails, history_id

        except HttpError as error:
            logger.error(f"Gmail API error during full sync: {error}")
            return [], history_id

    # ============ Message Details ============

    def _get_message_details(self, message_id: str) -> Optional[Dict[str, Any]]:
        """Get full message details by ID."""
        try:
            message = self.service.users().messages().get(
                userId="me",
                id=message_id,
                format="full",
            ).execute()

            headers = message["payload"]["headers"]

            def get_header(name: str) -> str:
                return next(
                    (h["value"] for h in headers if h["name"].lower() == name.lower()),
                    "",
                )

            subject = get_header("Subject") or "No Subject"
            sender = get_header("From") or "Unknown"
            to = get_header("To")
            cc = get_header("Cc")
            reply_to = get_header("Reply-To")
            date = get_header("Date")
            rfc_message_id = get_header("Message-ID") or get_header("Message-Id")

            body = self._extract_body(message["payload"])

            return {
                "gmail_id": message_id,
                "message_id": message.get("id"),
                "thread_id": message.get("threadId"),
                "subject": subject,
                "sender": sender,
                "to": to,
                "cc": cc,
                "reply_to": reply_to,
                "date": date,
                "rfc_message_id": rfc_message_id,
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
                        try:
                            body += base64.urlsafe_b64decode(
                                part["body"]["data"]
                            ).decode("utf-8")
                        except (ValueError, UnicodeDecodeError) as e:
                            logger.warning(f"Failed to decode email body part: {e}")
        else:
            if "body" in payload and "data" in payload["body"]:
                try:
                    body = base64.urlsafe_b64decode(
                        payload["body"]["data"]
                    ).decode("utf-8")
                except (ValueError, UnicodeDecodeError) as e:
                    logger.warning(f"Failed to decode email body: {e}")

        return body.strip()

    # ============ Send & Modify ============

    def send_reply(
        self,
        to: str,
        subject: str,
        body: str,
        thread_id: str,
        cc: str = "",
        in_reply_to: str = "",
    ) -> bool:
        """Send email reply in Gmail thread."""
        try:
            message = MIMEText(body)
            message["to"] = to
            message["subject"] = f"Re: {subject}" if not subject.lower().startswith("re:") else subject
            if cc:
                message["cc"] = cc
            if in_reply_to:
                message["In-Reply-To"] = in_reply_to
                message["References"] = in_reply_to

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
