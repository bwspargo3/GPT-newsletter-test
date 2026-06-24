"""
EDGAR ingestion: monitors 8-K, 10-Q, 10-K filings for L&A carrier watchlist.
Uses SEC's free JSON API — no key required.
"""

import logging
import re
import requests
import yaml
from datetime import date, timedelta
from pathlib import Path

from src.database.db import insert_article, record_source_health

logger = logging.getLogger(__name__)

CARRIERS_CONFIG = Path('config/carriers.yaml')
HEADERS = {'User-Agent': 'LA-Intelligence actuarial-research@example.com'}
SUBMISSIONS_URL = 'https://data.sec.gov/submissions/CIK{cik}.json'


def _is_relevant(text: str, keywords: list[str]) -> bool:
    """Check if filing description/title contains any relevance keyword."""
    text_lower = text.lower()
    return any(kw.lower() in text_lower for kw in keywords)


def fetch_carrier_filings(carrier: dict, filing_types: list[str],
                           relevance_keywords: list[str],
                           days_back: int = 2) -> int:
    """
    Fetch recent EDGAR filings for one carrier. Returns new article count.
    """
    cik = carrier['cik'].lstrip('0').zfill(10)  # normalize to 10 digits
    name = carrier['name']
    source_name = f"EDGAR:{name}"

    try:
        url = SUBMISSIONS_URL.format(cik=cik)
        resp = requests.get(url, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        recent = data.get('filings', {}).get('recent', {})
        forms = recent.get('form', [])
        dates = recent.get('filingDate', [])
        accessions = recent.get('accessionNumber', [])
        descriptions = recent.get('primaryDocument', [])
        items = recent.get('items', [])

        cutoff = (date.today() - timedelta(days=days_back)).isoformat()
        inserted = 0

        for i, (form, filing_date, accession) in enumerate(zip(forms, dates, accessions)):
            if filing_date < cutoff:
                # Filings are sorted newest-first; once we go past cutoff, stop
                break
            if form not in filing_types:
                continue

            desc = items[i] if i < len(items) else ''
            primary_doc = descriptions[i] if i < len(descriptions) else ''

            # Build the filing URL
            acc_clean = accession.replace('-', '')
            filing_url = (
                f"https://www.sec.gov/cgi-bin/browse-edgar"
                f"?action=getcompany&CIK={cik}&type={form}&dateb=&owner=include&count=10"
            )
            doc_url = (
                f"https://www.sec.gov/Archives/edgar/data/"
                f"{int(cik)}/{acc_clean}/{primary_doc}"
            ) if primary_doc else filing_url

            title = f"{name} {form} Filing – {filing_date}"
            content_snippet = f"{form} filing for {name}. Items: {desc}. Accession: {accession}."

            # Only include filings with relevant keywords, or always include 8-Ks
            if form != '8-K' and not _is_relevant(f"{desc} {primary_doc}", relevance_keywords):
                continue

            article = {
                'source': source_name,
                'title': title,
                'url': doc_url,
                'published_date': filing_date,
                'content': content_snippet,
                'category': 'COMPETITOR_INSIGHTS',
            }
            if insert_article(article):
                inserted += 1
                logger.info("EDGAR [%s] new %s filing: %s", name, form, filing_date)

        record_source_health(source_name, 'edgar', success=True)
        return inserted

    except Exception as exc:
        record_source_health(source_name, 'edgar', success=False)
        logger.error("EDGAR [%s] failed: %s", name, exc)
        return 0


def run_all(days_back: int = 2) -> int:
    """Fetch EDGAR filings for all configured carriers."""
    config = yaml.safe_load(CARRIERS_CONFIG.read_text())
    carriers = config.get('carriers', [])
    filing_types = config.get('filing_types', ['8-K', '10-Q', '10-K'])
    relevance_keywords = config.get('relevance_keywords', [])

    total = 0
    for carrier in carriers:
        total += fetch_carrier_filings(carrier, filing_types, relevance_keywords, days_back)

    logger.info("EDGAR ingestion complete: %d new filings", total)
    return total


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    run_all()
