"""
Google News RSS ingestion.
Builds a feed URL per keyword from config/keywords.yaml and fetches them.
"""

import logging
import yaml
import feedparser
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

from src.database.db import insert_article, record_source_health

logger = logging.getLogger(__name__)

KEYWORDS_CONFIG = Path('config/keywords.yaml')
GOOGLE_NEWS_BASE = 'https://news.google.com/rss/search'


def build_url(keyword: str) -> str:
    params = urllib.parse.urlencode({'q': keyword, 'hl': 'en-US', 'gl': 'US', 'ceid': 'US:en'})
    return f"{GOOGLE_NEWS_BASE}?{params}"


def _parse_date(entry) -> str:
    if hasattr(entry, 'published_parsed') and entry.published_parsed:
        try:
            return datetime(*entry.published_parsed[:6], tzinfo=timezone.utc).date().isoformat()
        except Exception:
            pass
    return datetime.utcnow().date().isoformat()


def fetch_keyword(keyword: str, label: str, category: str) -> int:
    """Fetch Google News RSS for one keyword. Returns new article count."""
    url = build_url(keyword)
    source_name = f"GoogleNews:{label}"
    try:
        feed = feedparser.parse(url, request_headers={
            'User-Agent': 'Mozilla/5.0 (compatible; LA-Intelligence/1.0)'
        })

        inserted = 0
        for entry in feed.entries:
            title = getattr(entry, 'title', '').strip()
            link = getattr(entry, 'link', '').strip()
            if not title or not link:
                continue

            # Google News wraps source names in the title: "Headline - Source Name"
            # Strip trailing source if present
            content = getattr(entry, 'summary', '')[:4000]

            article = {
                'source': source_name,
                'title': title,
                'url': link,
                'published_date': _parse_date(entry),
                'content': content,
                'category': category,
            }
            if insert_article(article):
                inserted += 1

        record_source_health(source_name, 'google_news', success=True)
        logger.info("GoogleNews [%s]: %d new", label, inserted)
        return inserted

    except Exception as exc:
        record_source_health(source_name, 'google_news', success=False)
        logger.error("GoogleNews [%s] failed: %s", label, exc)
        return 0


def run_all() -> int:
    """Fetch all Google News keyword feeds. Returns total new articles."""
    config = yaml.safe_load(KEYWORDS_CONFIG.read_text())
    total = 0
    for item in config.get('google_news_keywords', []):
        total += fetch_keyword(item['keyword'], item['label'], item['category'])
    logger.info("Google News ingestion complete: %d total new", total)
    return total


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    run_all()
