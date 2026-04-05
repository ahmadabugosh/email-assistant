# How It Works

A detailed look at how the Email Assistant works behind the scenes — from Gmail polling to Slack interaction to sending replies.

## Table of Contents

- [Lifecycle of an Email](#lifecycle-of-an-email)
- [Gmail Integration & Reliability](#gmail-integration--reliability)
- [Email Categorization & Reply Generation](#email-categorization--reply-generation)
- [Slack Interaction Flow](#slack-interaction-flow)
- [Sending Replies](#sending-replies)
- [Database & State Management](#database--state-management)
- [Security](#security)

---

## Lifecycle of an Email

Here's what happens end-to-end when a new email arrives:

```
1. Gmail receives new email
2. Polling loop detects it via History API
3. Email details are fetched (headers, body, recipients)
4. Deduplicated by RFC Message-ID (prevents duplicates)
5. Stored in SQLite database
6. LLM categorizes it (Portfolio Updates / Investment Advice / Referrals / Other)
7. Context is gathered based on category:
   - Portfolio Updates → Google Sheets portfolio lookup
   - Investment Advice → Tavily web search for market data
   - Referrals → To/CC recipient extraction
8. LLM generates a suggested reply using the context
9. Slack receives:
   - Channel message: compact summary (sender, date, subject, category)
   - Thread reply: full email body + suggested reply + action buttons
10. User reviews and clicks Send, Edit, or Ignore
11. If Send → reply is sent via Gmail as a proper threaded reply
12. The detail message in Slack is updated to show "Sent Reply"
```

---

## Gmail Integration & Reliability

### Why History API Instead of Polling for Unread?

A naive approach would be to poll Gmail for `is:inbox is:unread` emails. The problem: if a user reads an email on their phone before the assistant processes it, the email is marked as read and the assistant never sees it.

The Gmail History API solves this. It tracks **all changes** to the mailbox, not just unread status. It works like a changelog:

1. Gmail assigns a `historyId` to every state change
2. We store the last seen `historyId` in the database
3. Each poll asks: "What messages were added to the inbox since this `historyId`?"
4. Gmail returns all new message IDs, regardless of read/unread status

### First Run Behavior

On the very first run, the assistant does **not** fetch your entire inbox history. Instead, it:

1. Calls `users().getProfile()` to get the current `historyId`
2. Saves it to the database as the starting point
3. From this point forward, only processes new emails

This avoids flooding Slack with hundreds of old emails on first startup.

### Never Missing an Email

Three mechanisms ensure no email is ever lost:

**1. History API Tracking**
Every poll uses `users().history().list()` with `historyTypes=messageAdded` and `labelId=INBOX`. This catches every email added to the inbox, even if it was immediately read or archived elsewhere.

**2. Idempotent Processing**
Each email is inserted into the database with `INSERT OR IGNORE` on a unique Gmail ID. If the same email appears twice (e.g., from overlapping history windows), it's silently skipped.

**3. Crash Recovery**
On startup, the assistant checks for any emails that were fetched into the database but never fully processed (inserted but no category assigned). These are retried before the normal polling loop begins. This handles cases where:
- The app crashed mid-processing
- An API call (OpenAI, Slack) failed for one email in a batch
- The app was stopped between fetching and processing

### History ID Expiration

Gmail only keeps history for about 7 days. If the app is offline for longer, the history ID becomes invalid (HTTP 404). When this happens, the assistant resets to the current point — any emails from the gap that were already fetched will be caught by crash recovery on the next startup.

### Duplicate Prevention

The same physical email can sometimes appear with different Gmail internal IDs (e.g., when labels change). To prevent duplicate Slack notifications, emails are deduplicated by their RFC `Message-ID` header — a globally unique identifier assigned by the sending mail server.

---

## Email Categorization & Reply Generation

### Categorization

Each email is categorized by sending it to OpenAI's `gpt-4o-mini` with a zero-temperature prompt. The model returns exactly one of four categories:

| Category | Trigger | Example |
|----------|---------|---------|
| **Portfolio Updates** | Portfolio performance, rebalancing, account changes | "Your Q1 portfolio returned 8.2%" |
| **Investment Advice** | Questions about stocks, funds, allocation | "Should I increase my tech exposure?" |
| **Referrals** | Client introductions, CC'd recipients | "Meet my colleague John who needs..." |
| **Other** | Everything else | "Can we reschedule our meeting?" |

If the model returns an unexpected value, it defaults to "Other".

### Context Gathering

Before generating a reply, the assistant gathers relevant context based on the category:

- **Portfolio Updates**: Extracts the client name from the sender, looks up their portfolio in the connected Google Sheet (value, holdings, risk profile)
- **Investment Advice**: Extracts investment keywords from the email body and runs a Tavily web search for current market data and research
- **Referrals**: Extracts all recipients (To, CC) so the reply can acknowledge the referrer and address new clients

### Reply Generation

The reply is generated with a category-specific system prompt that sets the tone:
- Portfolio Updates: formal, acknowledges information, offers insights
- Investment Advice: conservative, data-driven, mentions risks
- Referrals: warm, acknowledges referrer, outlines next steps
- Other: helpful and professional

The model receives the full email content, any gathered context, and generates a reply under 150 words.

### Reply Refinement

When a user clicks "Edit" and provides feedback in the Slack thread, the assistant refines the reply. It sends the full conversation history (all previous feedback and revisions) to the LLM so it understands the multi-turn context. This allows iterative refinement:

```
User: "Make it more formal"
→ Assistant generates formal version
User: "Add a mention of the Q1 report"
→ Assistant adds Q1 reference while keeping the formal tone
```

---

## Slack Interaction Flow

### Message Structure

Each email creates two Slack messages:

1. **Channel message** (top-level): A compact summary card showing sender, date, subject, and category. This keeps the channel scannable.

2. **Thread reply**: The full email body, suggested reply in a code block, and three action buttons (Send, Edit, Ignore). This keeps details contained within a thread.

### Action Buttons

| Button | What Happens |
|--------|-------------|
| **Send** | Sends the suggested reply via Gmail as a threaded reply. The detail message in Slack is replaced with a "Sent Reply" confirmation showing exactly what was sent. |
| **Edit** | Posts a prompt in the thread asking for feedback. The user replies with what they want changed, and the assistant generates a refined version. |
| **Ignore** | Marks the email as ignored in the database. A confirmation is posted in the thread. |

### Socket Mode

The Slack bot uses Socket Mode (WebSocket connection) rather than HTTP webhooks. This means:
- No public URL or ngrok needed
- The bot connects outbound to Slack's servers
- Button clicks and messages are received instantly over the WebSocket
- Works behind firewalls and NATs

---

## Sending Replies

### Proper Email Threading

When you click "Send", the reply is sent as a **threaded reply** to the original email, not as a new email. This is done by setting three things:

1. **`threadId`**: Gmail's internal thread identifier, passed in the API call body
2. **`In-Reply-To`**: Set to the original email's RFC `Message-ID` header
3. **`References`**: Also set to the original email's RFC `Message-ID` header

These headers tell the recipient's email client that this is a reply to a specific message, so it appears in the same conversation thread.

### CC Support for Referrals

Referral emails often have multiple recipients. When replying:
- The `To` field is set to the original sender (or `Reply-To` if present)
- The `CC` field preserves the original CC recipients
- The LLM is aware of all recipients and tailors the reply accordingly

---

## Database & State Management

### SQLite Schema

The assistant uses SQLite with four tables:

| Table | Purpose |
|-------|---------|
| `emails` | Every email fetched from Gmail — ID, headers, body, category, suggested/final reply, status |
| `slack_threads` | Maps each email to its Slack thread timestamp and detail message timestamp |
| `conversations` | Stores all messages in Slack threads for multi-turn refinement context |
| `gmail_state` | Tracks the last Gmail `historyId` for incremental sync |

### Idempotency

- Email inserts use `INSERT OR IGNORE` with a unique constraint on `gmail_id`
- Additional deduplication on `rfc_message_id` before processing
- The `category IS NULL` check prevents reprocessing already-categorized emails
- These together mean the system can safely re-encounter the same email without duplicating work

### State Transitions

Each email moves through these statuses:

```
pending → (categorized, reply generated, sent to Slack)
       → sent     (user clicked Send)
       → ignored  (user clicked Ignore)
```

---

## Security

### Prompt Injection Mitigation

All user-provided content (email subject, body, sender) is:
1. **Sanitized** via `sanitize_for_prompt()` — strips control characters and truncates to safe lengths
2. **Wrapped in XML delimiters** (`<email>...</email>`) — helps the LLM distinguish between instructions and user content

### Credential Protection

- OAuth2 token files are written with `0o600` permissions (owner read/write only)
- Credentials and tokens are in `.gitignore` — never committed
- Tokens auto-refresh when expired; if refresh fails, the user is prompted to re-authenticate

### Network Security

- Slack Socket Mode uses outbound WebSocket — no inbound ports exposed
- Private Slack channel restricts who can see email content
- All API calls use HTTPS/TLS
