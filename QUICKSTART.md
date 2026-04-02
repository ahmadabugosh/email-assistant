# Quick Start Guide

## What's Built

✅ Complete email assistant project with:
- Gmail polling & OAuth2 authentication
- Email categorization (Portfolio, Investment, Referrals, Other)
- AI reply generation with context (web search, portfolio data)
- Slack bot with interactive threads
- SQLite database for state management
- Docker + Docker Compose for easy deployment
- Comprehensive test suite
- Production-ready error handling & logging

## Next Steps to Get Running

### 1. Setup Google Cloud (10 min)

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create new project → Enable Gmail API + Sheets API
3. Create OAuth credentials (Desktop app) → Download `credentials.json`
4. Place `credentials.json` in project root
5. Create a Google Sheet with portfolio data (or use the sample)
6. Copy the Sheet ID from the URL

### 2. Setup Slack App (10 min)

1. Go to [Slack Apps](https://api.slack.com/apps) → Create New App
2. Add permissions: `chat:write`, `channels:history`, `groups:history`
3. Install to workspace
4. Copy Bot Token (`xoxb-...`) and Signing Secret
5. Create private channel `#email-assistant`
6. Add bot to channel
7. Copy Channel ID

### 3. Get API Keys (5 min)

- OpenAI: https://platform.openai.com/api-keys → Copy API key
- Tavily (optional): https://tavily.com → Copy API key

### 4. Configure Environment (2 min)

```bash
cp .env.example .env
# Edit .env with your credentials
nano .env
```

### 5. Run

**With Docker:**
```bash
docker-compose up
```

**Without Docker:**
```bash
pip install -r requirements.txt
python -m src.main
```

First run: Browser opens for Gmail OAuth. Authorize and it saves `token.json`.

Then: Check your Slack private channel for incoming email notifications! 🎉

## Project Structure

```
src/
├── main.py              ← Entry point
├── config.py            ← Configuration loading
├── database.py          ← SQLite models
├── gmail_client.py      ← Gmail API (fetch, send)
├── sheets_client.py     ← Google Sheets (portfolio data)
├── email_processor.py   ← Categorization + LLM replies
├── slack_bot.py         ← Slack interactions + threads
├── tools.py             ← Web search, lookups
└── utils.py             ← Helpers

tests/                   ← Unit tests with mocks
docker-compose.yml       ← Docker setup
requirements.txt         ← Python dependencies
.env.example             ← Environment template
README.md                ← Full documentation
```

## Key Features

### How It Works

1. **Poll Gmail** every 30 seconds → find new emails
2. **Categorize** each email using LLM
3. **Generate reply** with context:
   - Portfolio Updates: Fetch data from Google Sheets
   - Investment Advice: Run Tavily web search
   - Referrals: Detect recipients, professional tone
   - Other: Best-effort with general knowledge
4. **Send to Slack** with buttons: Send ✅ | Edit ✏️ | Ignore 🚫
5. **Thread handling**: User types feedback → refine reply → post updated version
6. **Send email** when user clicks Send button

### Database Schema

Three tables:
- `emails` - Gmail messages with category, suggested/final replies
- `slack_threads` - Maps email to Slack thread
- `conversations` - Chat history in threads

All idempotent (safe to restart anytime).

## Testing

```bash
# Run all tests
pytest

# With coverage
pytest --cov=src tests/

# Specific test file
pytest tests/test_email_processor.py -v
```

Tests use mocks for Gmail/Slack/OpenAI APIs (no real API calls).

## Security Notes

✅ What's secure:
- OAuth2 with minimal scopes
- Credentials in .env (gitignored)
- Private Slack channel for emails
- Token auto-refresh

⚠️ For production:
- Use secrets manager (AWS, HashiCorp Vault)
- Encrypt database at rest
- Add rate limiting
- Use Pub/Sub instead of polling
- PostgreSQL instead of SQLite

## Troubleshooting

**OAuth Token Expired?**
- Delete `token.json` → restart → re-authenticate

**Slack Not Responding?**
- Check bot token is `xoxb-...`
- Verify bot is in private channel
- Check bot has `chat:write` permission

**Gmail Not Fetching?**
- Verify `GOOGLE_CREDENTIALS_PATH` exists
- Check `GOOGLE_SHEET_ID` is correct

**Tests Failing?**
- All tests mock external APIs
- Should pass offline

## Files to Modify

Only need to edit **one file** to customize:

1. **Categories** → `src/email_processor.py` (CATEGORIES list)
2. **Reply prompts** → `src/email_processor.py` (_get_system_prompt method)
3. **Polling interval** → `.env` (POLL_INTERVAL)
4. **Portfolio fields** → `src/sheets_client.py` (_get_all_portfolios)

## Architecture Decision Highlights

**Why this stack?**
- Python: Fast to code, great libraries
- SQLite: Zero setup, easy to switch to PostgreSQL
- OpenAI: Cost-effective (gpt-4o-mini for categorization/replies)
- Slack Bolt: Official SDK, clean async support
- Gmail History API: Incremental sync = reliable + efficient

**Why no Webhooks?**
- Polling is simpler for prototype
- No public URL required
- 30-second interval is plenty fast
- Production: Upgrade to Pub/Sub

## Next Features (Not Included)

1. Gmail Pub/Sub webhooks (instead of polling)
2. Persistent thread state for multi-turn conversations
3. Analytics dashboard (reply sent/ignored rates)
4. Email drafts before sending (add review step)
5. Multi-user support with permission model

---

**Good luck with the interview! This project demonstrates:**
- Full-stack integration (Google APIs, OpenAI, Slack)
- Solid architecture (separation of concerns, dependency injection)
- Production thinking (error handling, logging, tests, Docker)
- User-first design (intuitive Slack UX)

The code is clean, documented, and ready to extend. 🚀
