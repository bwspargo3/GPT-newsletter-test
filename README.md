# L&A Actuarial Intelligence

Daily automated briefing for life & annuity actuarial consultants.
Regulatory, market, and economic intelligence — curated by AI, delivered to your inbox at 5:15 AM CT.

**Zero infrastructure. Runs entirely from GitHub Actions. Cost: ~$0/month.**

---

## What it does

Every weekday morning:
1. **5:00 AM** — Ingests RSS feeds, Google News, NAIC regulatory pages, SEC EDGAR filings, Treasury yields, and FRED data
2. **5:15 AM** — Scores each article for L&A relevance (Groq), summarizes relevant ones, builds the daily HTML digest
3. **5:15 AM** — Publishes to GitHub Pages archive and emails all subscribers

**Coverage:**
- Regulatory: NAIC LATF, actuarial guidelines, VM-20/VM-22/PBR, LDTI
- Market: FIA/RILA/VA trends, life reinsurance, M&A, carrier news
- Carrier watch: MetLife, Prudential, Lincoln, Corebridge, Brighthouse, Athene, and more
- Research: SOA, AAA, Milliman, WTW, and other firm publications
- Economics: Treasury curve (10Y/20Y/30Y), SOFR, VIX, HY spreads

---

## Setup

### 1. Fork and clone this repo

```bash
git clone https://github.com/YOUR_USERNAME/la-intelligence.git
cd la-intelligence
```

### 2. Set GitHub Secrets

In your repo: **Settings → Secrets and variables → Actions → New repository secret**

| Secret | Description |
|--------|-------------|
| `GROQ_API_KEY` | From [console.groq.com](https://console.groq.com) — free tier is sufficient |
| `FRED_API_KEY` | From [fred.stlouisfed.org/docs/api](https://fred.stlouisfed.org/docs/api/api_key.html) — free |
| `SMTP_USER` | Your Gmail address (e.g. `yourname@gmail.com`) |
| `SMTP_PASSWORD` | Gmail **App Password** (not your account password) — [create one here](https://myaccount.google.com/apppasswords) |

### 3. Add subscribers

Edit `data/subscribers.csv`:
```csv
email
you@yourfirm.com
colleague@yourfirm.com
```

### 4. Enable GitHub Pages

Settings → Pages → Source: **Deploy from branch** → Branch: `main` → Folder: `/archive`

### 5. Test locally

```bash
pip install -r requirements.txt

# Test ingestion only (no Groq or email needed)
python run_ingest.py

# Preview digest HTML (requires GROQ_API_KEY)
export GROQ_API_KEY=gsk_...
SEND_EMAIL=false python run_digest.py
open data/preview_daily.html
```

### 6. Enable GitHub Actions

The workflows run automatically on schedule. You can also trigger manually:
- **Actions** tab → **Daily Ingest** → **Run workflow**
- **Actions** tab → **Daily Brief** → **Run workflow**

---

## Configuration

### `config/keywords.yaml`
Google News RSS keywords. Add/remove topics and carrier names here.

### `config/rss_feeds.yaml`
Direct RSS feeds. Add any actuarial blog, consulting firm, or regulator feed.

### `config/carriers.yaml`
EDGAR watchlist. Add/remove CIK numbers for carriers you want to track.

### `config/categories.yaml`
Category display names and sort order in the digest.

---

## Architecture

```
GitHub Actions (cron)
    │
    ├── run_ingest.py
    │       ├── src/ingestion/rss.py          (Tier 1: RSS)
    │       ├── src/ingestion/google_news.py  (Tier 2: Google News)
    │       ├── src/ingestion/naic_monitor.py (Tier 3: NAIC diff)
    │       ├── src/ingestion/edgar.py        (Tier 4: SEC filings)
    │       ├── src/ingestion/economic.py     (Treasury + FRED)
    │       └── src/processing/dedup.py       (title similarity filter)
    │
    └── run_digest.py
            ├── src/processing/groq.py         (relevance score + summarize)
            ├── src/digest/daily.py            (Jinja2 HTML render)
            ├── src/delivery/github_pages.py   (archive/YYYY/MM/DD.html)
            └── src/delivery/email.py          (Gmail SMTP)
```

**Database:** SQLite at `data/articles.db` — committed to repo, persisted via GitHub Actions cache.

---

## Phase 2 Roadmap

- [ ] Weekly digest with week-in-review commentary
- [ ] Source health dashboard
- [ ] Trending topics detection (mention frequency)
- [ ] Carrier watchlist dedicated section
- [ ] Historical archive search
- [ ] Unsubscribe link in emails

---

## Cost

| Service | Cost |
|---------|------|
| GitHub Actions | Free (public repo) |
| GitHub Pages | Free |
| Groq API | Free tier (~14,400 req/day on llama-3.3-70b) |
| FRED API | Free |
| EDGAR API | Free (no key needed) |
| Gmail SMTP | Free |
| **Total** | **$0/month** |

The only potential cost is if Groq usage exceeds the free tier on very high-volume days.
