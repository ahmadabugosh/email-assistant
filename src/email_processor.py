"""Email processor: categorization and reply generation."""
import logging
from typing import Dict, Any, List

from openai import OpenAI

logger = logging.getLogger(__name__)


class EmailProcessor:
    """Process emails: categorize and generate replies."""
    
    CATEGORIES = [
        "Portfolio Updates",
        "Investment Advice",
        "Referrals",
        "Other",
    ]
    
    def __init__(self, openai_api_key: str, toolkit):
        """Initialize email processor."""
        self.client = OpenAI(api_key=openai_api_key)
        self.toolkit = toolkit
    
    def categorize_email(self, email: Dict[str, Any]) -> str:
        """
        Categorize email using LLM.
        Returns one of: Portfolio Updates, Investment Advice, Referrals, Other
        """
        subject = email.get("subject", "")
        body = email.get("body", "")[:500]  # First 500 chars
        sender = email.get("sender", "")
        
        prompt = f"""You are an email categorization assistant. Categorize this email into one of these categories:
- Portfolio Updates: Updates about high net-worth individuals (HNIs) portfolios, portfolio performance, rebalancing
- Investment Advice: Questions about investing in stocks, funds, or other investment vehicles
- Referrals: Introduction to new customers or clients
- Other: Everything else

Email:
From: {sender}
Subject: {subject}
Body: {body}

Respond with ONLY the category name, nothing else."""
        
        try:
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                temperature=0,
            )
            
            category = response.choices[0].message.content.strip()
            
            # Validate category
            if category not in self.CATEGORIES:
                logger.warning(f"Invalid category returned: {category}, defaulting to Other")
                return "Other"
            
            return category
        
        except Exception as e:
            logger.error(f"Categorization error: {e}")
            return "Other"
    
    def generate_reply(
        self,
        email: Dict[str, Any],
        category: str,
        toolkit_context: str = "",
    ) -> str:
        """
        Generate suggested reply using LLM.
        Includes context from toolkit (web search, portfolio data, etc).
        """
        subject = email.get("subject", "")
        body = email.get("body", "")[:1000]
        sender = email.get("sender", "")
        
        # Build context based on category
        context = ""
        
        if category == "Portfolio Updates":
            # Extract client name and lookup portfolio
            client_name = self._extract_client_name(sender, body)
            if client_name:
                context = f"\n\nClient Portfolio Information:\n{self.toolkit.lookup_portfolio(client_name)}"
        
        elif category == "Investment Advice":
            # Search for investment-related context
            query = self._extract_investment_query(body)
            if query:
                search_results = self.toolkit.web_search(query)
                context = f"\n\nRelevant Research:\n{search_results}"
        
        elif category == "Referrals":
            context = "\n\nThis is a referral email introducing new clients. Use a professional, courteous tone."
        
        # Build system prompt based on category
        system_prompt = self._get_system_prompt(category)
        
        user_prompt = f"""Email from: {sender}
Subject: {subject}

Body:
{body}

{context if context else ""}

Generate a professional, concise suggested reply. Keep it under 150 words."""
        
        try:
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.7,
                max_tokens=300,
            )
            
            reply = response.choices[0].message.content.strip()
            return reply
        
        except Exception as e:
            logger.error(f"Reply generation error: {e}")
            return "Thank you for your email. I will review this and get back to you shortly."
    
    def refine_reply(
        self,
        original_email: Dict[str, Any],
        current_reply: str,
        user_feedback: str,
        category: str,
    ) -> str:
        """
        Refine the reply based on user feedback in Slack thread.
        """
        prompt = f"""The user wants to modify this email reply.

Original Email:
Subject: {original_email.get('subject', '')}
Body: {original_email.get('body', '')[:500]}

Current Reply:
{current_reply}

User Feedback:
{user_feedback}

Based on the feedback, generate an updated reply. Keep it professional and concise."""
        
        try:
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
                max_tokens=300,
            )
            
            refined_reply = response.choices[0].message.content.strip()
            return refined_reply
        
        except Exception as e:
            logger.error(f"Reply refinement error: {e}")
            return current_reply
    
    def _extract_client_name(self, sender: str, body: str) -> str:
        """Extract client name from email."""
        # Try to extract from sender name
        if "<" in sender:
            name = sender.split("<")[0].strip()
            return name if name else ""
        return sender.split("@")[0] if "@" in sender else ""
    
    def _extract_investment_query(self, body: str) -> str:
        """Extract investment-related query from email body."""
        # Simple heuristic: look for investment keywords
        keywords = ["invest", "stock", "fund", "etf", "bond", "portfolio", "return"]
        
        if any(kw in body.lower() for kw in keywords):
            # Return first 100 chars as query
            return body[:100]
        
        return ""
    
    def _get_system_prompt(self, category: str) -> str:
        """Get system prompt based on email category."""
        prompts = {
            "Portfolio Updates": """You are a professional investment adviser responding to portfolio updates. 
Be concise, acknowledge the information, and offer insights if appropriate.
Use formal but friendly tone.""",
            
            "Investment Advice": """You are a professional investment adviser providing thoughtful investment guidance.
Base your suggestions on research and data provided. Be conservative in recommendations.
Always mention risks and suggest consulting with a financial advisor if appropriate.""",
            
            "Referrals": """You are a professional investment adviser responding to client referrals.
Be warm, professional, and courteous. Acknowledge the referrer's recommendation.
Express enthusiasm to work with the new client and outline next steps.""",
            
            "Other": """You are a professional investment adviser responding to general inquiries.
Be helpful and professional. If the question is outside your domain, politely suggest appropriate next steps.""",
        }
        
        return prompts.get(category, prompts["Other"])
