"""Email processor: categorization and reply generation."""
import logging
from typing import Dict, Any, List

from openai import OpenAI

from src.utils import sanitize_for_prompt

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
        subject = sanitize_for_prompt(email.get("subject", ""), max_length=200)
        body = sanitize_for_prompt(email.get("body", ""), max_length=500)
        sender = sanitize_for_prompt(email.get("sender", ""), max_length=200)

        prompt = f"""You are an email categorization assistant. Categorize this email into one of these categories:
- Portfolio Updates: Updates about high net-worth individuals (HNIs) portfolios, portfolio performance, rebalancing
- Investment Advice: Questions about investing in stocks, funds, or other investment vehicles
- Referrals: Introduction to new customers or clients
- Other: Everything else

<email>
From: {sender}
Subject: {subject}
Body: {body}
</email>

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
        client_portfolio: Dict[str, Any] = None,
        referral_meta: Dict[str, Any] = None,
    ) -> str:
        """
        Generate suggested reply using LLM.
        Includes context from toolkit (web search, portfolio data, etc).
        client_portfolio: portfolio dict if sender is a known client, None otherwise.
        """
        subject = sanitize_for_prompt(email.get("subject", ""), max_length=200)
        body = sanitize_for_prompt(email.get("body", ""), max_length=1000)
        sender = sanitize_for_prompt(email.get("sender", ""), max_length=200)

        is_known_client = client_portfolio is not None

        # Build context based on category and client status
        context = ""

        if not is_known_client:
            context = (
                "\n\nNOTE: This sender is NOT in our client list. However, do NOT automatically ask them to verify their identity."
                "\n- If they are asking about a specific portfolio, account details, or other client-sensitive information, "
                "THEN politely mention you couldn't find them in your records and ask for their registered email to verify."
                "\n- If they are responding to an ongoing conversation (e.g. a referral thread), replying to a previous message, "
                "or making a general inquiry, just reply naturally based on the context of the conversation."
                "\n- If they are a new prospective client (e.g. from a referral), treat them warmly and help them with what they need."
            )

        if category == "Portfolio Updates" and is_known_client:
            portfolio_context = self.toolkit.sheets_client.format_portfolio_context(client_portfolio)
            context += f"\n\nClient Portfolio Information:\n{portfolio_context}"

        elif category == "Investment Advice":
            if is_known_client:
                query = self._extract_investment_query(body)
                if not query:
                    # Fallback: use subject + body snippet as search query
                    query = f"investment advice {subject} {body[:80]}"
                logger.info(f"Investment Advice search query: {query}")
                search_results = self.toolkit.web_search(query)
                context += f"\n\nRelevant Research:\n{search_results}"
            else:
                # Override the generic non-client message with an Investment Advice-specific decline
                context = (
                    "\n\nIMPORTANT: This sender is NOT a client. We do not offer investment advice to non-clients."
                    "\nIn your reply:"
                    "\n- Politely explain that investment advice is only available to existing clients"
                    "\n- Express interest in learning more about them — ask them to share a little about their portfolio size"
                    "\n- Offer to schedule a call to discuss whether they would be a good fit as a client"
                    "\n- Keep the tone warm and inviting, not dismissive"
                )

        elif category == "Referrals":
            if referral_meta:
                referrer_name = referral_meta.get("referrer_name", "the referrer")
                referred = referral_meta.get("referred", [])
                referred_names = ", ".join(r.get("name") or r.get("email") for r in referred) if referred else "the new client"
                is_first_reply = referral_meta.get("is_first_reply", True)

                if is_first_reply:
                    context += (
                        f"\n\nThis is a REFERRAL email. The referrer is {referrer_name} (existing client)."
                        f"\nThe referred person(s): {referred_names} (NEW prospective client)."
                        f"\nIMPORTANT — structure the reply in this exact order:"
                        f"\n1. Briefly thank {referrer_name} for the referral and let them know they are being moved to BCC"
                        f"\n2. Then address {referred_names} directly for the rest of the email"
                        f"\n3. Express interest in learning about {referred_names}'s investment needs and financial goals"
                        f"\n4. Ask {referred_names} to schedule a call so you can discuss how you can help THEM"
                        f"\nCRITICAL: The call invitation is for {referred_names}, NOT for {referrer_name}. {referrer_name} is an existing client — only {referred_names} needs onboarding."
                    )
                else:
                    context += (
                        f"\n\nThis is a FOLLOW-UP in a referral thread. The referrer has been removed."
                        f"\nAddress ONLY {referred_names} directly."
                        f"\nDo NOT mention the referrer or BCC. Treat this as a direct conversation with {referred_names}."
                    )
            else:
                to = email.get("to", "")
                cc = email.get("cc", "")
                recipients_info = ""
                if to:
                    recipients_info += f"\nTo: {to}"
                if cc:
                    recipients_info += f"\nCC: {cc}"
                context += f"\n\nThis is a referral email with multiple recipients.{recipients_info}\nAcknowledge the referrer and address the new client(s). Use a professional, courteous tone."

        # Build system prompt based on category
        system_prompt = self._get_system_prompt(category)

        user_prompt = f"""<email>
From: {sender}
Subject: {subject}

Body:
{body}
</email>

{context if context else ""}

Generate a professional, concise suggested reply. Keep it under 150 words.
IMPORTANT: Do NOT include a subject line in the reply body (no "Subject: ..." text). Just write the reply content directly.
Always end the reply with this exact signature:

Best regards,
Sarah James
Investment Adviser
HSBC"""

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
        conversation_history: List[Dict[str, str]] = None,
    ) -> str:
        """
        Refine the reply based on user feedback in Slack thread.
        Includes full conversation history for multi-turn context.
        """
        subject = sanitize_for_prompt(original_email.get("subject", ""), max_length=200)
        body = sanitize_for_prompt(original_email.get("body", ""), max_length=500)
        feedback = sanitize_for_prompt(user_feedback, max_length=500)

        history_text = ""
        if conversation_history:
            history_text = "\nConversation History:\n"
            for msg in conversation_history:
                history_text += f"[{msg['role']}]: {sanitize_for_prompt(msg['content'], max_length=300)}\n"

        prompt = f"""The user wants to modify this email reply.

<email>
Subject: {subject}
Body: {body}
</email>

Current Reply:
{current_reply}
{history_text}
Latest Feedback:
{feedback}

Based on the full conversation context and latest feedback, generate an updated reply. Keep it professional and concise."""

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
        keywords = ["invest", "stock", "fund", "etf", "bond", "portfolio", "return"]

        if any(kw in body.lower() for kw in keywords):
            return body[:100]

        return ""

    def _get_system_prompt(self, category: str) -> str:
        """Get system prompt based on email category."""
        prompts = {
            "Portfolio Updates": """You are a professional investment adviser responding to portfolio updates.
Be concise, acknowledge the information, and offer insights if appropriate.
Use formal but friendly tone.""",

            "Investment Advice": """You are a professional investment adviser providing thoughtful investment guidance.
You ARE the client's financial advisor — give direct, actionable advice based on the research provided.
Be conservative in recommendations and mention risks, but do NOT tell them to "consult a financial advisor" — that's you.""",

            "Referrals": """You are a professional investment adviser responding to client referrals.
Be warm, professional, and courteous. Follow the specific instructions about who to address.
If this is a first reply, thank the referrer and welcome the referred person.
If this is a follow-up, address only the referred person directly.""",

            "Other": """You are a professional investment adviser responding to general inquiries.
Be helpful and professional. If the question is outside your domain, politely suggest appropriate next steps.""",
        }

        return prompts.get(category, prompts["Other"])
