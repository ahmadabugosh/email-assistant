# Email Assistant - Gmail to Slack AI Agent

An intelligent email assistant that connects Gmail to Slack, categorizing incoming emails and generating suggested replies using AI. Perfect for busy investment advisers who want to stay focused in one application.

## Overview

This system:
1. **Polls Gmail** for new emails (never misses any with incremental history tracking)
2. **Categorizes** each email into: Portfolio Updates, Investment Advice, Referrals, or Other
3. **Generates** AI-powered suggested replies using context (portfolio data, web search)
4. **Sends to Slack** with action buttons (Send, Edit, Ignore)
5. **Handles feedback** through Slack threads where users can request modifications
6. **Sends replies** back to Gmail when approved

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Email Assistant                          │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  Gmail API ──> [Email Processor] ──> Slack Bot             │
│   (polling)    • Categorize        • Notify user           │
│                • Generate reply    • Handle actions        │
│                • Call tools       • Thread mgmt            │
│                                                              │
│  Tools:                                                      │
│  • Google Sheets (portfolio lookup)                         │
│  • Tavily Web Search (investment research)                  │
│  • OpenAI LLM (categorization & reply generation)          │
│                                                              │
│  Storage:                                                    │
│  • SQLite (processed emails, thread mapping, history)      │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

## Features

### Email Categorization
- **Portfolio Updates**: Portfolio performance, rebalancing, account updates
- **Investment Advice**: Questions about stocks, funds, asset allocation
- **Referrals**: New client introductions with courteous responses
- **Other**: General inquiries with best-effort responses

### Smart Context
- **Portfolio Updates**: Fetch relevant portfolio data from Google Sheets
- **Investment Advice**: Run web searches for current market data and research
- **Referrals**: Detect multiple recipients, use professional tone

### User Interaction
- One-click actions: Send, Edit, Ignore
- Thread-based feedback system for reply modifications
- Conversation history maintained in Slack threads

## Prerequisites

- **Python 3.11+**
- **Google Account** with Gmail API enabled
- **Google Cloud Project** with Sheets & Gmail APIs
- **Slack Workspace** with bot permissions
- **OpenAI API Key** (for LLM)
- **Tavily API Key** (optional, for web search)

## Setup

### 1. Google Cloud Setup

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select existing
3. Enable APIs:
   - Gmail API
   - Google Sheets API
4. Create OAuth 2.0 credentials:
   - Go to "Credentials" → "Create Credentials" → "OAuth client ID"
   - Choose "Desktop application"
   - Download JSON file as `credentials.json`
5. Create a Google Sheet for portfolio data:
   - Use the sample sheet: https://docs.google.com/spreadsheets/d/1iboWR0CpWKRvzsw8wTIjeYo4UStzH9I1IzDZPWFCwUk/edit
   - Copy columns: Client Name | Portfolio Value | Holdings | Risk Profile | Last Updated
   - Get the Sheet ID from the URL

### 2. Slack App Setup

1. Go to [Slack App Dashboard](https://api.slack.com/apps)
2. Create a new app (From scratch)
3. Add permissions (OAuth & Permissions):
   - `chat:write` - Send messages
   - `channels:history` - Read channel history
   - `groups:history` - Read DM history
4. Install app to workspace
5. Copy Bot Token Xoxb-... and Signing Secret

### 3. Create Private Slack Channel

1. Create a private channel (e.g., `#email-assistant`)
2. Add your bot to the channel
3. Copy the Channel ID (right-click channel → Copy Member ID)

### 4. Environment Setup

```bash
# Copy example to .env
cp .env.example .env

# Edit .env with your credentials
OPENAI_API_KEY=sk-proj-...
SLACK_BOT_TOKEN=xoxb-...
SLACK_SIGNING_SECRET=...
SLACK_CHANNEL_ID=C...
GOOGLE_SHEET_ID=...
TAVILY_API_KEY=...
```

### 5. Get Google OAuth Tokens

First run will trigger OAuth flow:

```bash
# With Docker
docker-compose up

# Without Docker
python -m src.main
```

A browser window will open. Authorize the app. Tokens saved to `token.json`.

## Running

### With Docker (Recommended)

```bash
# Start the service
docker-compose up -d

# View logs
docker-compose logs -f

# Stop
docker-compose down
```

### Without Docker

```bash
# Install dependencies
pip install -r requirements.txt

# Run
python -m src.main

# Stop with Ctrl+C
```

## Testing

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=src tests/

# Run specific test
pytest tests/test_email_processor.py
```

## Configuration

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `OPENAI_API_KEY` | Yes | OpenAI API key for LLM |
| `SLACK_BOT_TOKEN` | Yes | Slack bot token (xoxb-...) |
| `SLACK_SIGNING_SECRET` | Yes | Slack app signing secret |
| `SLACK_CHANNEL_ID` | Yes | Slack channel ID for notifications |
| `GOOGLE_CREDENTIALS_PATH` | Yes | Path to credentials.json |
| `GOOGLE_TOKEN_PATH` | Yes | Path to store token.json |
| `GOOGLE_SHEET_ID` | Yes | Google Sheet ID for portfolios |
| `TAVILY_API_KEY` | No | Tavily API key for web search |
| `POLL_INTERVAL` | No | Email poll interval in seconds (default: 30) |
| `DB_PATH` | No | SQLite database path (default: email_assistant.db) |

## Security Considerations

### OAuth2 & Credentials
- ✅ Uses OAuth2 with minimal required scopes
- ✅ Tokens auto-refreshed when expired
- ✅ Credentials never committed to git (.gitignore)
- ⚠️ Production: Use secure key management (AWS Secrets Manager, HashiCorp Vault)

### Data Privacy
- ✅ Private Slack channel ensures email privacy
- ✅ Email content not logged or exposed
- ⚠️ Production: Encrypt SQLite database at rest (e.g., `sqlcipher`)

### Input Validation
- ✅ LLM prompts sanitized before sending
- ✅ Email parsing handles malformed messages
- ⚠️ Production: Rate limit API calls to prevent abuse

### Rate Limiting
- ✅ Gmail polling interval (configurable)
- ⚠️ Production: Implement exponential backoff for API failures

## Architecture Decisions

### Why Python?
- Fast to develop
- Excellent library support (google-api, slack-bolt, openai)
- Good async/await support

### Why SQLite?
- Zero setup, file-based
- Sufficient for prototype
- Easy to migrate to PostgreSQL for production

### Why Polling instead of Webhooks?
- Simpler to set up (no public endpoint required)
- More reliable for prototype (no webhook delivery issues)
- Good enough for 30-second interval

### Why gpt-4o-mini?
- Cheap and fast (per requirements)
- Good categorization accuracy
- Sufficient for reply generation

## Production Improvements

### Reliability
- [ ] Gmail Push Notifications (Pub/Sub) instead of polling
- [ ] Message queue (Celery/Redis) for async processing
- [ ] Comprehensive logging and monitoring
- [ ] Retry logic with exponential backoff

### Scalability
- [ ] PostgreSQL instead of SQLite
- [ ] Redis for caching portfolio data
- [ ] Horizontal scaling with load balancer
- [ ] API rate limiting

### Security
- [ ] Database encryption at rest (sqlcipher)
- [ ] Secrets management (AWS Secrets Manager)
- [ ] TLS for all communications
- [ ] API authentication/authorization
- [ ] Audit logging for data access

### Observability
- [ ] Structured logging (JSON)
- [ ] Application Performance Monitoring (APM)
- [ ] Alert thresholds for errors
- [ ] Dashboard for system health

### Code Quality
- [ ] Type checking with mypy
- [ ] Code linting (ruff, black)
- [ ] Pre-commit hooks
- [ ] CI/CD pipeline (GitHub Actions)

## Project Structure

```
email-assistant/
├── src/
│   ├── main.py                 # Orchestrator
│   ├── config.py               # Configuration
│   ├── database.py             # SQLite models
│   ├── gmail_client.py         # Gmail API wrapper
│   ├── sheets_client.py        # Google Sheets API
│   ├── email_processor.py      # Categorization & reply generation
│   ├── slack_bot.py            # Slack interactions
│   ├── tools.py                # Web search, portfolio lookup
│   └── utils.py                # Helpers
├── tests/
│   ├── conftest.py             # Pytest fixtures
│   ├── test_database.py        # Database tests
│   ├── test_email_processor.py # Processor tests
│   └── test_gmail_client.py    # Gmail client tests
├── scripts/
│   └── setup_google_oauth.py   # OAuth setup helper
├── docker-compose.yml          # Docker configuration
├── Dockerfile                  # Container image
├── requirements.txt            # Python dependencies
├── .env.example                # Environment template
├── .gitignore                  # Git ignore rules
└── README.md                   # This file
```

## Troubleshooting

### Gmail OAuth Token Expired
```
Error: oauth2: "invalid_grant" "Token has been expired or revoked"
```
**Fix**: Delete `token.json` and restart. Browser will open for re-authentication.

### Slack Bot Not Responding
- Verify `SLACK_BOT_TOKEN` is correct (starts with `xoxb-`)
- Verify bot is added to the private channel
- Check bot scopes include `chat:write` and `channels:history`

### LLM Rate Limit
- OpenAI returns 429 error
- **Fix**: Reduce `POLL_INTERVAL` or upgrade API plan

### Google Sheets Not Loading
- Verify `GOOGLE_SHEET_ID` is correct
- Verify bot has read access to the sheet
- Check sheet has headers in first row

## License

MIT

## Support

For issues, bugs, or feature requests, please open an issue on GitHub.

---

**Built for interview assignment** — Investment Adviser Email Assistant | OpenAI + Google Cloud + Slack
