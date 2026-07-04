# 🎨 Industrial Design News Bot

Fully automated daily digest of industrial design news — collected, deduplicated, AI-summarized, and delivered to Telegram and Gmail every morning at 08:00 Tehran time.

---

## Architecture

```
RSS Feeds (11) ─┐
Web Scrape  (4) ├──▶ Collector ──▶ Dedup ──▶ AI Enrich ──▶ Report Builder ──▶ Telegram
Google News (3) ┘                                                           └──▶ Gmail
                        ↑
                GitHub Actions cron (04:30 UTC = 08:00 Tehran)
```

---

## Folder Structure

```
design-news-bot/
├── .github/
│   └── workflows/
│       └── daily-news.yml        ← GitHub Actions cron schedule
├── src/
│   ├── sources.py                ← ✏️  EDIT THIS to add/remove sources
│   ├── collector.py              ← RSS parser + web scraper
│   ├── dedup.py                  ← Duplicate removal (URL + title similarity)
│   ├── summarizer.py             ← Claude / OpenRouter AI enrichment
│   ├── report.py                 ← Markdown report builder
│   ├── deliver.py                ← Telegram + Gmail delivery
│   └── main.py                   ← Orchestrator (entry point)
├── reports/                      ← Generated .md files (auto-created)
├── logs/                         ← Run logs (auto-created)
├── requirements.txt
└── README.md
```

---

## Prerequisites

| Requirement | How to get | Cost |
|---|---|---|
| GitHub account | github.com | Free |
| Anthropic API key | console.anthropic.com | ~$0.01–0.10/day |
| **OR** OpenRouter key | openrouter.ai | Free tier available |
| Telegram Bot token | @BotFather on Telegram | Free |
| Telegram Chat ID | @userinfobot on Telegram | Free |
| Gmail App Password | Google Account → Security | Free |

### API Cost Estimate

With **Claude Haiku** (cheapest model):
- ~30 articles/day × 8 articles/batch = ~4 API calls
- ~500 tokens input + 300 output per call = ~3200 tokens/day
- **Cost: ~$0.001–0.005 per day** (less than $0.15/month)

With **OpenRouter free tier** (mistral-7b-instruct:free):
- **Cost: $0** (rate-limited but sufficient for daily use)

---

## Installation

### Step 1 — Fork & Clone

```bash
# Fork the repo on GitHub, then:
git clone https://github.com/YOUR_USERNAME/design-news-bot.git
cd design-news-bot
```

### Step 2 — Set GitHub Secrets

Go to your repo → **Settings → Secrets and variables → Actions → New repository secret**

Add these secrets:

```
ANTHROPIC_API_KEY      = sk-ant-...        (or leave empty to use OpenRouter)
OPENROUTER_API_KEY     = sk-or-...         (or leave empty to use Claude)
TELEGRAM_BOT_TOKEN     = 123456:ABC-DEF... (from @BotFather)
TELEGRAM_CHAT_ID       = -100123456789     (your chat/channel ID)
GMAIL_USER             = yourname@gmail.com
GMAIL_APP_PASSWORD     = xxxx xxxx xxxx xxxx  (16-char App Password)
GMAIL_TO               = yourname@gmail.com   (can be same as GMAIL_USER)
```

### Step 3 — Get Telegram Credentials

**Create a bot:**
1. Open Telegram → search `@BotFather`
2. Send `/newbot` → follow prompts → copy the token

**Get your Chat ID:**
1. Start a conversation with your bot
2. Open Telegram → search `@userinfobot` → send `/start` → copy your ID
3. OR create a channel, add your bot as admin, and use the channel ID (starts with -100)

### Step 4 — Get Gmail App Password

1. Enable 2-Factor Authentication on your Google account
2. Go to: **Google Account → Security → 2-Step Verification → App Passwords**
3. Select "Mail" + "Other" → generate → copy the 16-character password

### Step 5 — Test Locally (optional)

```bash
# Install dependencies
pip install -r requirements.txt

# Set environment variables
export ANTHROPIC_API_KEY="sk-ant-..."
export TELEGRAM_BOT_TOKEN="123456:ABC..."
export TELEGRAM_CHAT_ID="123456789"
export GMAIL_USER="you@gmail.com"
export GMAIL_APP_PASSWORD="xxxx xxxx xxxx xxxx"
export GMAIL_TO="you@gmail.com"

# Run
cd src
python main.py
```

### Step 6 — Enable GitHub Actions

1. Push your fork to GitHub
2. Go to **Actions** tab → enable workflows if prompted
3. Click **"Daily Design News Bot"** → **"Run workflow"** to test manually

The bot will now run automatically at **08:00 Tehran time** every day.

---

## Customize Sources

Edit `src/sources.py`:

```python
# Add a new RSS source:
RSS_SOURCES = [
    ...
    {
        "name": "My New Source",
        "url": "https://example.com/feed.xml",
        "enabled": True,
    },
]

# Add a Google News query:
GOOGLE_NEWS_QUERIES = [
    "industrial design",
    "product design award",
    "my new query",      # ← add here
]
```

---

## Environment Variables Reference

| Variable | Required | Description |
|---|---|---|
| `ANTHROPIC_API_KEY` | One of these two | Claude API key |
| `OPENROUTER_API_KEY` | One of these two | OpenRouter API key |
| `TELEGRAM_BOT_TOKEN` | Yes | Telegram bot token from @BotFather |
| `TELEGRAM_CHAT_ID` | Yes | Your Telegram user ID or channel ID |
| `GMAIL_USER` | Optional | Gmail address for sending |
| `GMAIL_APP_PASSWORD` | Optional | Gmail App Password (not your main password) |
| `GMAIL_TO` | Optional | Recipient email (defaults to GMAIL_USER) |

---

## Cron Schedule

```yaml
# .github/workflows/daily-news.yml
- cron: "30 4 * * *"   # 04:30 UTC = 08:00 Tehran (UTC+3:30)
```

To change the time, use [crontab.guru](https://crontab.guru).

---

## Cost Summary

| Service | Cost |
|---|---|
| GitHub Actions | Free (2000 min/month free) |
| Claude Haiku API | ~$0.05–1.50/month |
| OpenRouter free tier | $0 |
| Telegram Bot API | $0 |
| Gmail SMTP | $0 |
| **Total** | **$0–1.50/month** |

---

## Troubleshooting

**No articles collected:**
- Check Actions logs (`Actions` tab → latest run → `run-bot`)
- Some RSS feeds may block GitHub Actions IPs; the scraper has a fallback

**Telegram not receiving messages:**
- Confirm bot has started a chat with you (send `/start` to your bot first)
- For channels: bot must be an admin with "Post messages" permission

**Gmail not sending:**
- Use an App Password, NOT your Gmail login password
- Make sure 2FA is enabled on your Google account

**AI enrichment failing:**
- Check your API key is correctly set in Secrets
- The bot falls back to keyword-based categorization automatically

---

## Future Improvements

- Add Bale messenger delivery (similar Telegram API)
- Weekly summary email with charts (matplotlib)
- Web dashboard (GitHub Pages) showing article trends
- Slack / Discord webhook delivery
- Filter by category — receive only "Design Awards" articles
- Sentiment analysis per category
- Save to Notion or Airtable database
