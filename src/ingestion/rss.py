"""
RSS feed ingestion. Reads config/rss_feeds.yaml and fetches all feeds.
"""

import logging
import yaml
import feedparser
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

from src.database.db import insert_article, record_source_health

logger = logging.getLogger(__name__)

FEEDS_CONFIG = Path('config/rss_feeds.yaml')


def _parse_date(entry) -> str | None:
    """Extract and normalize a publish date from a feedparser entry."""
    # Try published_parsed first (already a struct_time)
    if hasattr(entry, 'published_parsed') and entry.published_parsed:
        try:
            return datetime(*entry.published_parsed[:6], tzinfo=timezone.utc).date().isoformat()
        except Exception:
            pass
    # Fallback to raw string
    if hasattr(entry, 'published') and entry.published:
        try:
            return parsedate_to_datetime(entry.published).date().isoformat()
        except Exception:
            pass
    return datetime.utcnow().date().isoformat()


def _extract_content(entry) -> str:
    """Pull the best available text content from a feed entry."""
    if hasattr(entry, 'content') and entry.content:
        return entry.content[0].get('value', '')[:4000]
    if hasattr(entry, 'summary') and entry.summary:
        return entry.summary[:4000]
    return ''


def fetch_feed(url: str, source_name: str, category: str) -> int:
    """
    Fetch one RSS feed and insert new articles into the DB.
    Returns number of new articles inserted.
    """
    try:
        feed = feedparser.parse(url, request_headers={'User-Agent': 'LA-Intelligence/1.0'})
        if feed.bozo and not feed.entries:
            raise ValueError(f"Feed parse error: {feed.bozo_exception}")

        inserted = 0
        for entry in feed.entries:
            title = getattr(entry, 'title', '').strip()
            url_entry = getattr(entry, 'link', '').strip()
            if not title or not url_entry:
                continue

            article = {
                'source': source_name,
                'title': title,
                'url': url_entry,
                'published_date': _parse_date(entry),
                'content': _extract_content(entry),
                'category': category,
            }
            if insert_article(article):
                inserted += 1

        record_source_health(source_name, 'rss', success=True)
        logger.info("RSS [%s]: %d new articles", source_name, inserted)
        return inserted

    except Exception as exc:
        record_source_health(source_name, 'rss', success=False)
        logger.error("RSS [%s] failed: %s", source_name, exc)
        return 0


def run_all() -> int:
    """Fetch all feeds from config. Returns total new articles."""
    config = yaml.safe_load(FEEDS_CONFIG.read_text())
    total = 0
    for feed in config.get('feeds', []):
        total += fetch_feed(feed['url'], feed['name'], feed['category'])
    logger.info("RSS ingestion complete: %d total new articles", total)
    return total


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    run_all()
