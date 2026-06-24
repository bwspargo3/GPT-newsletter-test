#!/usr/bin/env python3
"""
Main ingestion runner.
Called by daily_ingest.yml GitHub Action (5:00 AM).
Runs all sources in order, then deduplicates.
"""

import logging
import sys
from datetime import datetime

# Ensure project root is on path when run directly
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.database.db import init_db
from src.ingestion import rss, google_news, economic, naic_monitor, edgar, web_scrape, playwright_scrape
from src.processing.dedup import purge_duplicates

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
    ]
)
logger = logging.getLogger('ingest')


def run():
    start = datetime.utcnow()
    logger.info("=== L&A Intelligence Ingestion Started ===")

    # Initialize DB (idempotent)
    init_db()

    totals = {}

    # ── Tier 1: RSS feeds ──────────────────────────────────────────────
    logger.info("--- RSS Feeds ---")
    try:
        totals['rss'] = rss.run_all()
    except Exception as exc:
        logger.error("RSS ingestion failed: %s", exc)
        totals['rss'] = 0

    # ── Tier 2: Google News RSS ────────────────────────────────────────
    logger.info("--- Google News RSS ---")
    try:
        totals['google_news'] = google_news.run_all()
    except Exception as exc:
        logger.error("Google News ingestion failed: %s", exc)
        totals['google_news'] = 0

    # ── Tier 2.5: Listing-page Scrapers (RSS-less sources) ──────────────
    logger.info("--- Web Scrape (SOA Research, etc.) ---")
    try:
        totals['scrape'] = web_scrape.run_all()
    except Exception as exc:
        logger.error("Web scrape ingestion failed: %s", exc)
        totals['scrape'] = 0

    # ── Tier 2.6: Headless-browser Scrapers (JS-rendered sources) ───────
    # Milliman and WTW render their article lists client-side; this tier
    # uses Playwright to execute that JS before scraping. Slower and more
    # fragile than the other tiers by nature — see playwright_scrape.py.
    logger.info("--- Headless Scrape (Milliman, WTW) ---")
    try:
        totals['headless_scrape'] = playwright_scrape.run_all()
    except Exception as exc:
        logger.error("Headless scrape ingestion failed: %s", exc)
        totals['headless_scrape'] = 0

    # ── Tier 3: NAIC Monitoring ────────────────────────────────────────
    logger.info("--- NAIC Monitor ---")
    try:
        totals['naic'] = naic_monitor.run_all()
    except Exception as exc:
        logger.error("NAIC monitor failed: %s", exc)
        totals['naic'] = 0

    # ── Tier 4: EDGAR ─────────────────────────────────────────────────
    logger.info("--- EDGAR ---")
    try:
        totals['edgar'] = edgar.run_all(days_back=2)
    except Exception as exc:
        logger.error("EDGAR ingestion failed: %s", exc)
        totals['edgar'] = 0

    # ── Tier 5: Economic Data ──────────────────────────────────────────
    logger.info("--- Economic Data ---")
    try:
        economic.run_all()
        totals['economic'] = 1
    except Exception as exc:
        logger.error("Economic data fetch failed: %s", exc)
        totals['economic'] = 0

    # ── Deduplication ──────────────────────────────────────────────────
    logger.info("--- Deduplication ---")
    try:
        removed = purge_duplicates(days_back=2)
        totals['dedup_removed'] = removed
    except Exception as exc:
        logger.error("Dedup failed: %s", exc)

    elapsed = (datetime.utcnow() - start).seconds
    logger.info("=== Ingestion Complete in %ds ===", elapsed)
    logger.info("Results: %s", totals)

    total_new = sum(v for k, v in totals.items() if k not in ('dedup_removed', 'economic'))
    return total_new


if __name__ == '__main__':
    count = run()
    print(f"\n✓ Ingestion complete: {count} new articles ingested")
