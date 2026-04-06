# Quick Start Guide

## What's Built

Complete email assistant project with:
- Gmail polling & OAuth2 authentication
- Email categorization (Portfolio, Investment, Referrals, Other)
- AI reply generation with context (web search, portfolio data)
- Smart referral routing with BCC (first reply BCC's referrer; follow-ups drop them)
- Client-aware replies (known clients get research-backed advice; non-clients get polite decline)
- Consistent email signature (Sarah James, Investment Adviser, HSBC)
- Slack bot with interactive threads
- SQLite database for state management
- Docker + Docker Compose for easy deployment
- Comprehensive test suite (81 tests across 8 modules)
- Production-ready error handling & logging

## Next Steps to Get Running

### 1. Setup Google Cloud (10 min)

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create new project → Enable **Gmail API** only (Sheets API is NOT needed — portfolio data is read via public CSV export)
3. Create OAuth credentials (Desktop app) → Download `credentials.json`
4. Place `credentials.json` in project root
5. Create a **public** Google Sheet with portfolio data (or use the [sample sheet](https://docs.google.com/spreadsheets/d/1iboWR0CpWKRvzsw8wTIjeYo4UStzH9I1IzDZPWFCwUk/edit))
   - Columns: Name | Email | Portfolio Holdings | Current Net Worth | Expected Next Quarter Earnings | Has Beneficiary | Beneficiary Name
   - Set sharing to "Anyone with the link can view"
6. Copy the Sheet ID from the URL

### 2. Setup Slack App (10 min)

1. Go to [Slack Apps](https://api.slack.com/apps) → Create New App (From scratch)
2. **Enable Socket Mode**: Toggle ON → Create App-Level Token with `connections:write` scope → Copy token (`xapp-...`)
3. Add bot permissions (OAuth & Permissions > Scopes): `chat:write`, `channels:history`, `groups:history`
4. **Enable Event Subscriptions**: Toggle ON → Subscribe to bot events: `message.channels`, `message.groups`
5. **Enable Interactivity & Shortcuts**: Toggle ON (no Request URL needed with Socket Mode)
6. Install to workspace
7. Copy Bot Token (`xoxb-...`) and Signing Secret
8. Create private channel (e.g. `#email-assistant`)
9. Add bot to channel (`/invite @YourBotName`)
10. Copy Channel ID (right-click channel > View channel details)

### 3. Get API Keys (5 min)

- OpenAI: https://platform.openai.com/api-keys → Copy API key
- Tavily (optional): https://tavily.com → Copy API key

### 4. Configure Environment (2 min)

```bash
cp .env.example .env
# Edit .env with your credentials
nano .env
```

Required variables:
```
OPENAI_API_KEY=sk-proj-...
SLACK_BOT_TOKEN=xoxb-...
SLACK_SIGNING_SECRET=...
SLACK_APP_TOKEN=xapp-...
SLACK_CHANNEL_ID=C...
GOOGLE_SHEET_ID=...
TAVILY_API_KEY=...          # optional, for investment advice web search
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
├── main.py              ← Entry point (polling, referral metadata, first-run scan)
├── config.py            ← Configuration loading
├── database.py          ← SQLite models + thread tracking
├── gmail_client.py      ← Gmail API (fetch, send, BCC)
├── sheets_client.py     ← Google Sheets (public CSV, no auth)
├── email_processor.py   ← Categorization + LLM replies + signature
├── slack_bot.py         ← Slack interactions + BCC routing
├── tools.py             ← Web search, portfolio lookups
└── utils.py             ← Sanitization helpers

tests/                   ← 81 tests across 8 modules (all mocked)
docs/                    ← HOW_IT_WORKS.md, TESTING.md, diagrams
docker-compose.yml       ← Docker setup
requirements.txt         ← Python dependencies
.env.example             ← Environment template
README.md                ← Full documentation
```

## Key Features

### How It Works

1. **Poll Gmail** every 30 seconds (first run also scans unread inbox)
2. **Detect client status** by looking up sender email in Google Sheet (public CSV)
3. **Categorize** each email using LLM (gpt-4o-mini)
4. **Generate reply** with context:
   - Portfolio Updates: Fetch client holdings from Google Sheet
   - Investment Advice (known client): Tavily web search → research-backed advice
   - Investment Advice (non-client): Polite decline + offer to schedule a call
   - Referrals: Identify referrer vs referred, generate appropriate first-reply or follow-up
   - Other: Professional response (no automatic identity verification)
5. **Send to Slack** with buttons: Send | Edit | Ignore
6. **Thread handling**: User types feedback → refine reply → post updated version
7. **Route recipients** at send time:
   - Referral (first reply): To=referred, BCC=referrer
   - Referral (follow-up): To=referred only, referrer dropped
   - Other: To=sender (or Reply-To), CC=original CC
8. **Send email** via Gmail with proper threading (In-Reply-To, References headers)

### Database Schema

Four tables:
- `emails` — Gmail messages with category, suggested/final replies, recipients JSON (including referral metadata)
- `slack_threads` — Maps each email to its Slack thread (multiple emails can share a thread)
- `conversations` — Chat history in threads for multi-turn refinement
- `gmail_state` — Tracks last Gmail historyId for incremental sync

All idempotent (safe to restart anytime).

## Testing

```bash
# Run all tests (81 tests, 8 modules)
pytest tests/ -v

# With coverage
pytest --cov=src tests/

# Specific test file
pytest tests/test_referral_routing.py -v
```

Tests use mocks for Gmail/Slack/OpenAI/Tavily APIs (no real API calls, no credentials needed). See [`docs/TESTING.md`](docs/TESTING.md) for full details.

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
- Verify `credentials.json` exists in the project root
- Delete `token.json` and re-authenticate if needed

**Google Sheet Not Loading?**
- Verify `GOOGLE_SHEET_ID` is correct
- Make sure the sheet is set to "Anyone with the link can view" (public access required)

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

## What's Included

| Feature | Status |
|---------|--------|
| Gmail History API polling (never misses emails) | Done |
| First-run inbox scan (catches pre-existing unread) | Done |
| LLM categorization (4 categories) | Done |
| Client detection via Google Sheet (public CSV) | Done |
| Tavily web search for investment advice | Done |
| Referral BCC routing (first reply + follow-up) | Done |
| Non-client context-aware handling | Done |
| Email signature enforcement | Done |
| Slack interactive threads + multi-turn refinement | Done |
| Crash recovery (resume unprocessed emails) | Done |
| RFC Message-ID deduplication | Done |
| Self-sent email filtering | Done |
| 81 tests, 0 network calls | Done |
| Docker + Docker Compose deployment | Done |

## Production Improvements

- Gmail Pub/Sub webhooks (instead of polling)
- PostgreSQL instead of SQLite
- Secrets manager (AWS Secrets Manager, HashiCorp Vault)
- Database encryption at rest (sqlcipher)
- Rate limiting and exponential backoff
- CI/CD pipeline (GitHub Actions)

---

**This project demonstrates:**
- Full-stack integration (Gmail API, OpenAI, Slack, Tavily, Google Sheets)
- Solid architecture (separation of concerns, dependency injection)
- Production thinking (error handling, crash recovery, logging, 81 tests, Docker)
- User-first design (intuitive Slack UX, smart referral routing)
