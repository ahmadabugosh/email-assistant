"""Tests for email processor."""
import pytest
from unittest.mock import MagicMock, patch


def test_categorize_portfolio_update(email_processor, sample_portfolio_email):
    """Test categorization of portfolio update email."""
    # Mock OpenAI response
    mock_response = MagicMock()
    mock_response.choices[0].message.content = "Portfolio Updates"
    email_processor.client.chat.completions.create.return_value = mock_response
    
    category = email_processor.categorize_email(sample_portfolio_email)
    
    assert category == "Portfolio Updates"
    email_processor.client.chat.completions.create.assert_called_once()


def test_categorize_investment_advice(email_processor, sample_investment_email):
    """Test categorization of investment advice email."""
    mock_response = MagicMock()
    mock_response.choices[0].message.content = "Investment Advice"
    email_processor.client.chat.completions.create.return_value = mock_response
    
    category = email_processor.categorize_email(sample_investment_email)
    
    assert category == "Investment Advice"


def test_categorize_referral(email_processor, sample_referral_email):
    """Test categorization of referral email."""
    mock_response = MagicMock()
    mock_response.choices[0].message.content = "Referrals"
    email_processor.client.chat.completions.create.return_value = mock_response
    
    category = email_processor.categorize_email(sample_referral_email)
    
    assert category == "Referrals"


def test_categorize_invalid_response(email_processor, sample_email):
    """Test handling of invalid category response."""
    mock_response = MagicMock()
    mock_response.choices[0].message.content = "InvalidCategory"
    email_processor.client.chat.completions.create.return_value = mock_response
    
    category = email_processor.categorize_email(sample_email)
    
    # Should default to Other
    assert category == "Other"


def test_generate_reply_portfolio(email_processor, sample_portfolio_email):
    """Test reply generation for portfolio email."""
    mock_response = MagicMock()
    mock_response.choices[0].message.content = "Thank you for the update. Your portfolio is performing well."
    email_processor.client.chat.completions.create.return_value = mock_response
    
    reply = email_processor.generate_reply(
        sample_portfolio_email, "Portfolio Updates"
    )
    
    assert "Thank you" in reply
    assert len(reply) > 0


def test_generate_reply_investment(email_processor, sample_investment_email):
    """Test reply generation for investment advice email."""
    mock_response = MagicMock()
    mock_response.choices[0].message.content = "Based on my research, the XYZ fund has strong performance metrics."
    email_processor.client.chat.completions.create.return_value = mock_response
    
    reply = email_processor.generate_reply(
        sample_investment_email, "Investment Advice"
    )
    
    assert len(reply) > 0


def test_refine_reply(email_processor, sample_email):
    """Test reply refinement based on user feedback."""
    original_reply = "Thank you for your email."
    user_feedback = "Can you make it more detailed?"
    
    mock_response = MagicMock()
    mock_response.choices[0].message.content = "Thank you for your email. I appreciate you reaching out and will provide detailed guidance on your request."
    email_processor.client.chat.completions.create.return_value = mock_response
    
    refined = email_processor.refine_reply(
        sample_email, original_reply, user_feedback, "Other"
    )
    
    assert len(refined) > len(original_reply)


def test_extract_client_name(email_processor):
    """Test client name extraction."""
    # From formatted sender
    name = email_processor._extract_client_name(
        "John Smith <john@example.com>", ""
    )
    assert name == "John Smith"
    
    # From email
    name = email_processor._extract_client_name("john@example.com", "")
    assert name == "john"


def test_system_prompt_portfolio(email_processor):
    """Test system prompt for portfolio category."""
    prompt = email_processor._get_system_prompt("Portfolio Updates")
    assert "investment adviser" in prompt.lower()
    assert "portfolio" in prompt.lower()


def test_system_prompt_referral(email_processor):
    """Test system prompt for referral category."""
    prompt = email_processor._get_system_prompt("Referrals")
    assert "professional" in prompt.lower()
    assert "warm" in prompt.lower()
