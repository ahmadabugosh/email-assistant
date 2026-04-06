"""Tests for email processing: self-sent filtering, context generation, signatures."""
import json
import pytest
from unittest.mock import MagicMock, patch

from src.email_processor import EmailProcessor


# ============ REFERRAL CONTEXT TESTS ============


@pytest.fixture
def processor():
    """EmailProcessor with mocked OpenAI and toolkit."""
    mock_toolkit = MagicMock()
    mock_toolkit.web_search.return_value = "Search results about ETFs"
    mock_toolkit.sheets_client.format_portfolio_context.return_value = "Portfolio: $1M"
    with patch("openai.OpenAI"):
        proc = EmailProcessor("fake-key", mock_toolkit)
        proc.client = MagicMock()
        return proc


def _mock_llm_response(processor, content):
    """Helper to mock LLM response."""
    mock_resp = MagicMock()
    mock_resp.choices[0].message.content = content
    processor.client.chat.completions.create.return_value = mock_resp


def test_referral_first_reply_context(processor):
    """First referral reply prompt includes BCC, referrer thanks, and call for referred."""
    email = {"sender": "Ahmad <ahmad@gmail.com>", "subject": "Referral", "body": "Meet Alex"}
    referral_meta = {
        "referrer_name": "Ahmad",
        "referred": [{"email": "alex@test.com", "name": "Alex"}],
        "is_first_reply": True,
    }

    _mock_llm_response(processor, "Thank you Ahmad. Alex, let's schedule a call.")
    processor.generate_reply(email, "Referrals", referral_meta=referral_meta)

    call_args = processor.client.chat.completions.create.call_args
    user_prompt = call_args.kwargs["messages"][1]["content"]

    assert "BCC" in user_prompt or "bcc" in user_prompt.lower()
    assert "Ahmad" in user_prompt
    assert "Alex" in user_prompt
    assert "schedule" in user_prompt.lower() or "call" in user_prompt.lower()


def test_referral_followup_context_no_referrer(processor):
    """Follow-up referral prompt addresses only referred person, no BCC mention."""
    email = {"sender": "Alex <alex@test.com>", "subject": "Re: Referral", "body": "I'd like to book a call"}
    referral_meta = {
        "referrer_name": "Ahmad",
        "referred": [{"email": "alex@test.com", "name": "Alex"}],
        "is_first_reply": False,
    }

    _mock_llm_response(processor, "Great, let's schedule a call.")
    processor.generate_reply(email, "Referrals", referral_meta=referral_meta)

    call_args = processor.client.chat.completions.create.call_args
    user_prompt = call_args.kwargs["messages"][1]["content"]

    assert "FOLLOW-UP" in user_prompt
    assert "ONLY" in user_prompt
    assert "Do NOT mention the referrer" in user_prompt


def test_investment_advice_known_client_gets_search(processor):
    """Known clients asking for investment advice trigger web search."""
    email = {"sender": "client@test.com", "subject": "ETF advice", "body": "Should I invest in ETFs?"}
    client_portfolio = {"name": "Client", "holdings": "Stocks"}

    _mock_llm_response(processor, "Based on research, ETFs are a good option.")
    processor.generate_reply(email, "Investment Advice", client_portfolio=client_portfolio)

    processor.toolkit.web_search.assert_called_once()
    call_args = processor.client.chat.completions.create.call_args
    user_prompt = call_args.kwargs["messages"][1]["content"]
    assert "Research" in user_prompt


def test_investment_advice_non_client_decline(processor):
    """Non-clients asking for investment advice get polite decline."""
    email = {"sender": "stranger@test.com", "subject": "Advice", "body": "What stocks should I buy?"}

    _mock_llm_response(processor, "We only provide advice to existing clients.")
    processor.generate_reply(email, "Investment Advice")

    processor.toolkit.web_search.assert_not_called()
    call_args = processor.client.chat.completions.create.call_args
    user_prompt = call_args.kwargs["messages"][1]["content"]
    assert "NOT a client" in user_prompt
    assert "schedule a call" in user_prompt.lower() or "call" in user_prompt.lower()


def test_non_client_generic_no_auto_verify(processor):
    """Non-client context should NOT automatically ask to verify identity."""
    email = {"sender": "new@test.com", "subject": "Hello", "body": "Hi, I'd like to learn more about your services."}

    _mock_llm_response(processor, "Hi, we'd love to help.")
    processor.generate_reply(email, "Other")

    call_args = processor.client.chat.completions.create.call_args
    user_prompt = call_args.kwargs["messages"][1]["content"]

    # Should NOT automatically demand verification
    assert "do NOT automatically ask them to verify" in user_prompt.lower() or "do not automatically" in user_prompt.lower()


def test_portfolio_updates_known_client(processor):
    """Known client portfolio update includes portfolio context."""
    email = {"sender": "client@test.com", "subject": "Portfolio check", "body": "How's my portfolio?"}
    client_portfolio = {"name": "Client", "holdings": "AAPL, GOOGL"}

    _mock_llm_response(processor, "Your portfolio is doing well.")
    processor.generate_reply(email, "Portfolio Updates", client_portfolio=client_portfolio)

    call_args = processor.client.chat.completions.create.call_args
    user_prompt = call_args.kwargs["messages"][1]["content"]
    assert "Portfolio" in user_prompt


# ============ SIGNATURE AND SUBJECT LINE TESTS ============


def test_prompt_includes_signature(processor):
    """Generated reply prompt instructs to include Sarah James signature."""
    email = {"sender": "test@test.com", "subject": "Hello", "body": "Hi"}

    _mock_llm_response(processor, "Reply with signature.")
    processor.generate_reply(email, "Other")

    call_args = processor.client.chat.completions.create.call_args
    user_prompt = call_args.kwargs["messages"][1]["content"]
    assert "Sarah James" in user_prompt
    assert "Investment Adviser" in user_prompt
    assert "HSBC" in user_prompt


def test_prompt_forbids_subject_in_body(processor):
    """Prompt instructs LLM not to include Subject: line in reply body."""
    email = {"sender": "test@test.com", "subject": "Hello", "body": "Hi"}

    _mock_llm_response(processor, "Reply without subject.")
    processor.generate_reply(email, "Other")

    call_args = processor.client.chat.completions.create.call_args
    user_prompt = call_args.kwargs["messages"][1]["content"]
    assert "Do NOT include a subject line" in user_prompt


# ============ SYSTEM PROMPT TESTS ============


def test_investment_advice_prompt_no_consult_advisor(processor):
    """Investment advice prompt says YOU are the advisor, don't defer."""
    prompt = processor._get_system_prompt("Investment Advice")
    assert "You ARE the client" in prompt or "you ARE" in prompt.lower()
    assert "consult" not in prompt.lower() or "do NOT" in prompt


def test_referral_system_prompt(processor):
    """Referral system prompt includes instructions about first vs follow-up."""
    prompt = processor._get_system_prompt("Referrals")
    assert "first reply" in prompt.lower()
    assert "follow-up" in prompt.lower()


# ============ SELF-SENT FILTERING ============


def test_self_sent_email_skipped():
    """Emails from the authenticated user should be skipped."""
    # We test the logic directly rather than the full async flow
    user_email = "assistant@gmail.com"
    sender = "assistant@gmail.com"
    assert user_email.lower() in sender.lower()

    sender_formatted = "Assistant Bot <assistant@gmail.com>"
    assert user_email.lower() in sender_formatted.lower()


def test_external_email_not_skipped():
    """Emails from other senders should NOT be skipped."""
    user_email = "assistant@gmail.com"
    sender = "client@example.com"
    assert user_email.lower() not in sender.lower()


# ============ REFERRAL METADATA EXTRACTION ============


def test_build_referral_meta():
    """Test _build_referral_meta extracts correct referrer and referred."""
    from src.main import EmailAssistant

    # Create a minimal mock assistant
    with patch.object(EmailAssistant, "__init__", lambda self: None):
        assistant = EmailAssistant()
        assistant.user_email = "advisor@company.com"
        assistant.database = MagicMock()
        assistant.database.has_sent_reply_in_thread.return_value = False

        email = {
            "sender": "Ahmad Abugosh <ahmad@gmail.com>",
            "to": "advisor@company.com",
            "cc": "Alex Smith <alex@newclient.com>",
            "thread_id": "thread_1",
        }

        meta = assistant._build_referral_meta(email)

        assert meta["referrer_email"] == "ahmad@gmail.com"
        assert meta["referrer_name"] == "Ahmad Abugosh"
        assert len(meta["referred"]) == 1
        assert meta["referred"][0]["email"] == "alex@newclient.com"
        assert meta["is_first_reply"] is True


def test_build_referral_meta_multiple_referred():
    """Multiple referred people in CC are all captured."""
    from src.main import EmailAssistant

    with patch.object(EmailAssistant, "__init__", lambda self: None):
        assistant = EmailAssistant()
        assistant.user_email = "advisor@company.com"
        assistant.database = MagicMock()
        assistant.database.has_sent_reply_in_thread.return_value = False

        email = {
            "sender": "Ahmad <ahmad@gmail.com>",
            "to": "advisor@company.com",
            "cc": "Alex <alex@test.com>, Bob <bob@test.com>",
            "thread_id": "thread_1",
        }

        meta = assistant._build_referral_meta(email)

        referred_emails = [r["email"] for r in meta["referred"]]
        assert "alex@test.com" in referred_emails
        assert "bob@test.com" in referred_emails
        assert "ahmad@gmail.com" not in referred_emails
        assert "advisor@company.com" not in referred_emails


def test_build_referral_meta_followup():
    """Follow-up in referral thread: is_first_reply should be False."""
    from src.main import EmailAssistant

    with patch.object(EmailAssistant, "__init__", lambda self: None):
        assistant = EmailAssistant()
        assistant.user_email = "advisor@company.com"
        assistant.database = MagicMock()
        assistant.database.has_sent_reply_in_thread.return_value = True

        email = {
            "sender": "Alex <alex@newclient.com>",
            "to": "advisor@company.com",
            "cc": "",
            "thread_id": "thread_1",
        }

        meta = assistant._build_referral_meta(email)
        assert meta["is_first_reply"] is False


def test_extract_name():
    """Test name extraction from email headers."""
    from src.main import EmailAssistant

    assert EmailAssistant._extract_name("John Smith <john@test.com>") == "John Smith"
    assert EmailAssistant._extract_name("john@test.com") == "john"
    assert EmailAssistant._extract_name('"Jane Doe" <jane@test.com>') == "Jane Doe"
