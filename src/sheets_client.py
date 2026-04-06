"""Google Sheets API client for fetching portfolio data."""
import logging
import os
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta

from google.auth.transport.requests import Request
from google.oauth2.service_account import Credentials
from google.oauth2.credentials import Credentials as OAuth2Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]


class SheetsClient:
    """Google Sheets API client for portfolio data."""
    
    def __init__(self, sheet_id: str, credentials_path: str, token_path: str):
        """Initialize Sheets client."""
        self.sheet_id = sheet_id
        self.credentials_path = credentials_path
        self.token_path = token_path
        self.service = None
        self.cache: Dict[str, Any] = {}
        self.cache_timestamp: Optional[datetime] = None
        self._authenticate()
    
    def _authenticate(self) -> None:
        """Authenticate with Sheets API."""
        from pathlib import Path
        
        creds = None
        
        # Try to load existing token
        if Path(self.token_path).exists():
            creds = OAuth2Credentials.from_authorized_user_file(
                self.token_path, SCOPES
            )
        
        # If no valid credentials, get new ones
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    self.credentials_path, SCOPES
                )
                creds = flow.run_local_server(port=0)
            
            # Save token with restricted permissions
            with open(self.token_path, "w") as f:
                f.write(creds.to_json())
            os.chmod(self.token_path, 0o600)

        self.service = build("sheets", "v4", credentials=creds)
    
    def get_portfolio(self, client_name: str) -> Optional[Dict[str, Any]]:
        """
        Get portfolio data for a specific client.
        Search by client name in the sheet.
        """
        all_portfolios = self._get_all_portfolios()

        # Case-insensitive search (supports both "name" and "client name" headers)
        for portfolio in all_portfolios:
            name = portfolio.get("name", "") or portfolio.get("client name", "")
            if name.lower() == client_name.lower():
                return portfolio

        return None

    def get_portfolio_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        """
        Get portfolio data by client email address.
        More reliable than name matching.
        """
        all_portfolios = self._get_all_portfolios()

        email_lower = email.lower().strip()
        for portfolio in all_portfolios:
            portfolio_email = portfolio.get("email", "").lower().strip()
            if portfolio_email and portfolio_email == email_lower:
                return portfolio

        return None
    
    def get_all_portfolios(self) -> List[Dict[str, Any]]:
        """Get all portfolio data (cached)."""
        return self._get_all_portfolios()
    
    def _is_cache_valid(self) -> bool:
        """Check if cache is still valid (5 minutes)."""
        if not self.cache_timestamp:
            return False
        
        age = datetime.utcnow() - self.cache_timestamp
        return age < timedelta(minutes=5)
    
    def _get_all_portfolios(self) -> List[Dict[str, Any]]:
        """Fetch all portfolios from sheet (with caching)."""
        # Return cached data if valid
        if self._is_cache_valid() and "portfolios" in self.cache:
            return self.cache["portfolios"]
        
        try:
            # Read the sheet
            result = self.service.spreadsheets().values().get(
                spreadsheetId=self.sheet_id,
                range="A1:L1000",
            ).execute()
            
            values = result.get("values", [])
            if not values:
                logger.warning("No data found in sheet")
                return []
            
            # First row is header
            headers = [h.lower() for h in values[0]]
            portfolios = []
            
            # Parse data rows
            for row in values[1:]:
                if not row:
                    continue
                
                portfolio = {}
                for i, header in enumerate(headers):
                    if i < len(row):
                        portfolio[header] = row[i]
                
                if portfolio.get("name") or portfolio.get("client name"):
                    portfolios.append(portfolio)
            
            # Cache the result
            self.cache["portfolios"] = portfolios
            self.cache_timestamp = datetime.utcnow()
            
            logger.info(f"Fetched {len(portfolios)} portfolios from sheet")
            return portfolios
        
        except HttpError as error:
            logger.error(f"Sheets API error: {error}")
            return []
    
    def format_portfolio_context(self, portfolio: Dict[str, Any]) -> str:
        """Format portfolio data for LLM context."""
        name = portfolio.get("name", "") or portfolio.get("client name", "Unknown")
        lines = [
            f"Client: {name}",
            f"Portfolio Holdings: {portfolio.get('portfolio holdings', '') or portfolio.get('holdings', 'N/A')}",
            f"Current Net Worth: {portfolio.get('current net worth ($)', '') or portfolio.get('portfolio value', 'N/A')}",
            f"Expected Next Quarter Earnings: {portfolio.get('expected next quarter earnings ($)', 'N/A')}",
        ]
        # Include beneficiary info if present
        if portfolio.get("has beneficiary (y/n)", "").upper() == "Y":
            lines.append(f"Beneficiary: {portfolio.get('beneficiary name', 'N/A')}")
        return "\n".join(lines)
