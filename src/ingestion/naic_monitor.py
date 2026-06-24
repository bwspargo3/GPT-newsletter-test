"""
NAIC regulatory page monitor.
Hashes page content and creates an article when a change is detected.
"""

import hashlib
import logging
import requests
from datetime import date

from src.database.db import insert_article, upsert_naic_page, record_source_health

logger = logging.getLogger(__name__)

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (compatible; LA-Intelligence/1.0; actuarial research bot)'
}

# Key NAIC pages to monitor
#
# NOTE: The previous config included two static PDF URLs
# (cmte_a_latf_agenda.pdf / cmte_a_latf_minutes.pdf) and a second committee
# page (cmte_a_life_actuarial.htm). All three 404 — NAIC does not publish
# agendas/minutes at fixed filenames; they post a new, dated packet PDF for
# every meeting (e.g. "LATF Materials SpNM 2026.pdf") under
# content.naic.org/sites/default/files/national_meeting/, with no stable
# "latest" URL. The committee page below already surfaces current agenda
# items, exposures, and meeting links inline, so it's the single reliable
# page to hash for change detection.
NAIC_PAGES = [
    {
        'url': 'https://content.naic.org/committees/a/life-actuarial-tf',
        'label': 'NAIC LATF Committee Page',
        'category': 'REGULATORY',
    },
]


def hash_page(content: str) -> str:
    return hashlib.sha256(content.encode('utf-8', errors='replace')).hexdigest()


def check_page(url: str, label: str, category: str) -> bool:
    """
    Fetch a NAIC page, compare its hash to the stored value.
    If changed, create an article. Returns True if change detected.
    """
    try:
        resp = requests.get(url, headers=HEADERS, timeout=30)
        resp.raise_for_status()

        new_hash = hash_page(resp.text)
        changed = upsert_naic_page(url, label, new_hash)

        if changed:
            logger.info("NAIC change detected: %s", label)
            article = {
                'source': 'NAIC Monitor',
                'title': f"[UPDATE] {label}",
                'url': url,
                'published_date': date.today().isoformat(),
                'content': f"Content change detected on {label}. Review the page for updates.",
                'category': category,
                'relevance_score': 9.0,   # auto-high: regulatory change is always relevant
                'summary': f"The NAIC page for {label} has been updated. Actuaries should review for new guidance, exposure drafts, or meeting materials.",
                'why_it_matters': "Regulatory changes from NAIC LATF directly affect PBR reserving, actuarial guidelines, and compliance requirements for L&A carriers.",
            }
            insert_article(article)
        else:
            logger.info("NAIC no change: %s", label)

        record_source_health(label, 'naic_monitor', success=True)
        return changed

    except Exception as exc:
        record_source_health(label, 'naic_monitor', success=False)
        logger.error("NAIC monitor [%s] failed: %s", label, exc)
        return False


def run_all() -> int:
    """Check all NAIC pages. Returns count of pages with detected changes."""
    changes = sum(check_page(p['url'], p['label'], p['category']) for p in NAIC_PAGES)
    logger.info("NAIC monitor: %d/%d pages changed", changes, len(NAIC_PAGES))
    return changes


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    run_all()
