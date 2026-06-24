#!/usr/bin/env python3
"""
Daily digest runner.
Called by daily_brief.yml GitHub Action (5:15 AM).
Runs Groq processing → renders HTML → publishes archive → sends email.
"""

import logging
import sys
import os
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.database.db import init_db
from src.processing.groq import process_unscored
from src.digest.daily import build_daily
from src.delivery.github_pages import publish_daily
from src.delivery.email import send_daily_digest

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger('digest')

# Control flags via env vars (set in GitHub Actions or locally)
SEND_EMAIL = os.getenv('SEND_EMAIL', 'true').lower() == 'true'
PUBLISH_ARCHIVE = os.getenv('PUBLISH_ARCHIVE', 'true').lower() == 'true'
MIN_SCORE = float(os.getenv('MIN_RELEVANCE_SCORE', '6.5'))
MAX_ARTICLES = int(os.getenv('MAX_DIGEST_ARTICLES', '12'))


def run():
    logger.info("=== L&A Intelligence Digest Started ===")
    init_db()

    # ── Step 1: Groq processing ────────────────────────────────────────
    logger.info("--- Groq Processing ---")
    stats = process_unscored(batch_size=60)
    logger.info("Processing stats: %s", stats)

    # ── Step 2: Build digest HTML ──────────────────────────────────────
    logger.info("--- Building Digest ---")
    html, article_count = build_daily(
        days_back=1,
        min_score=MIN_SCORE,
        max_articles=MAX_ARTICLES,
        mark_sent=True,
    )

    if article_count == 0:
        logger.warning("No articles met the relevance threshold — skipping send")
        # Still publish to archive so there's a record
        if PUBLISH_ARCHIVE:
            publish_daily(html)
        return 0

    logger.info("Digest built: %d articles", article_count)

    # ── Step 3: Publish to GitHub Pages archive ────────────────────────
    if PUBLISH_ARCHIVE:
        logger.info("--- Publishing Archive ---")
        archive_path = publish_daily(html)
        logger.info("Archive published: %s", archive_path)

    # ── Step 4: Send email ─────────────────────────────────────────────
    if SEND_EMAIL:
        logger.info("--- Sending Email ---")
        email_stats = send_daily_digest(html, article_count)
        logger.info("Email stats: %s", email_stats)

    logger.info("=== Digest Complete: %d articles ===", article_count)
    return article_count


if __name__ == '__main__':
    count = run()
    print(f"\n✓ Digest complete: {count} articles sent")
