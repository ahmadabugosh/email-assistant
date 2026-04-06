"""Google Sheets client for fetching portfolio data (no auth required for public sheets)."""
import csv
import io
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta

import requests

logger = logging.getLogger(__name__)


class SheetsClient:
    """Google Sheets client — reads public sheets via CSV export."""

    def __init__(self, sheet_id: str, **kwargs):
        """Initialize Sheets client. Only needs the sheet ID."""
        self.sheet_id = sheet_id
        self.csv_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/gviz/tq?tqx=out:csv"
        self.cache: Dict[str, Any] = {}
        self.cache_timestamp: Optional[datetime] = None

    def get_portfolio(self, client_name: str) -> Optional[Dict[str, Any]]:
        """Get portfolio data by client name."""
        all_portfolios = self._get_all_portfolios()

        for portfolio in all_portfolios:
            name = portfolio.get("name", "") or portfolio.get("client name", "")
            if name.lower() == client_name.lower():
                return portfolio

        return None

    def get_portfolio_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        """Get portfolio data by client email address."""
        all_portfolios = self._get_all_portfolios()

        email_lower = email.lower().strip()
        logger.info(f"Looking up client by email: {email_lower} (sheet has {len(all_portfolios)} portfolios)")
        for portfolio in all_portfolios:
            portfolio_email = portfolio.get("email", "").lower().strip()
            if portfolio_email and portfolio_email == email_lower:
                logger.info(f"Matched client: {portfolio.get('name', 'unknown')}")
                return portfolio

        logger.info(f"No client match for {email_lower}")
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
        """Fetch all portfolios from sheet via CSV export (with caching)."""
        if self._is_cache_valid() and "portfolios" in self.cache:
            return self.cache["portfolios"]

        try:
            response = requests.get(self.csv_url, timeout=10)
            response.raise_for_status()

            reader = csv.DictReader(io.StringIO(response.text))
            portfolios = []

            for row in reader:
                # Lowercase all keys for consistent access
                portfolio = {k.lower(): v for k, v in row.items()}
                if portfolio.get("name") or portfolio.get("client name"):
                    portfolios.append(portfolio)

            self.cache["portfolios"] = portfolios
            self.cache_timestamp = datetime.utcnow()

            logger.info(f"Fetched {len(portfolios)} portfolios from sheet")
            return portfolios

        except Exception as e:
            logger.error(f"Error fetching sheet data: {e}")
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
        if portfolio.get("has beneficiary (y/n)", "").upper() == "Y":
            lines.append(f"Beneficiary: {portfolio.get('beneficiary name', 'N/A')}")
        return "\n".join(lines)
