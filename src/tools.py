"""Tools for email processing: web search, portfolio lookup, etc."""
import logging
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)


class ToolKit:
    """Tools available to the AI agent."""
    
    def __init__(self, tavily_api_key: str, sheets_client):
        """Initialize toolkit."""
        self.tavily_api_key = tavily_api_key
        self.sheets_client = sheets_client
        self.tavily_available = bool(tavily_api_key)
    
    def web_search(self, query: str, max_results: int = 3) -> str:
        """
        Search the web using Tavily API.
        Returns formatted search results for LLM context.
        """
        if not self.tavily_available:
            logger.warning("Tavily API not configured, skipping web search")
            return "Web search not available"
        
        try:
            from tavily import Client
            
            client = Client(api_key=self.tavily_api_key)
            response = client.search(query, max_results=max_results)
            
            # Format results
            results = []
            for result in response.get("results", []):
                results.append(f"""
Title: {result.get('title', 'N/A')}
URL: {result.get('url', 'N/A')}
Snippet: {result.get('content', 'N/A')}
""")
            
            if results:
                return "\n---\n".join(results)
            else:
                return "No search results found"
        
        except Exception as e:
            logger.error(f"Web search error: {e}")
            return f"Search failed: {str(e)}"
    
    def lookup_portfolio(self, client_name: str) -> str:
        """Look up portfolio data for a client."""
        portfolio = self.sheets_client.get_portfolio(client_name)
        
        if portfolio:
            return self.sheets_client.format_portfolio_context(portfolio)
        else:
            return f"No portfolio found for {client_name}"
    
    def extract_recipients(self, email_body: str, sender: str) -> List[str]:
        """Extract email recipients from body (for referral emails)."""
        # This is a simple heuristic for referral emails
        # In production, would use email headers (To, CC, BCC)
        recipients = [sender]
        
        # Look for email patterns in body
        import re
        email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
        found_emails = re.findall(email_pattern, email_body)
        
        for email in found_emails:
            if email not in recipients:
                recipients.append(email)
        
        return recipients
