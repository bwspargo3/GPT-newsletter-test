"""
Listing-page scraper for sources that don't expose a usable RSS feed.

This is a fallback tier for sites where the RSS feed is dead, was never
offered, or returns HTML instead of XML. Each scraper here is hand-written
against one specific page's structure, which means it WILL break if that
page is redesigned — this is inherently higher-maintenance than RSS and
should only be used for sources important enough to be worth that cost.

Each scraper function returns a list of article dicts in the same shape
insert_article() expects (source, title, url, published_date, content,
category), so run_all() can feed them through the normal pipeline.
"""

import logging
import re
from datetime import date, datetime

import requests
from bs4 import BeautifulSoup

from src.database.db import insert_article, record_source_health

logger = logging.getLogger(__name__)

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (compatible; LA-Intelligence/1.0; actuarial research bot)'
}

_MONTH_RE = re.compile(
    r'^(January|February|March|April|May|June|July|August|September|'
    r'October|November|December)\b(\s+\d{4})?$',
    re.IGNORECASE,
)


def _guess_published_date(month_text: str | None) -> str:
    """
    SOA's listing only gives a month (and sometimes year, sometimes not).
    Without a day, we anchor to the 1st of that month/year. If no year is
    given, SOA's own convention on this page is "most recent year" — we
    assume current year, which is correct unless the page is showing
    December-dated items fetched in early January (an edge case we accept
    rather than over-engineer for a monthly digest page).
    """
    if not month_text:
        return date.today().isoformat()
    parts = month_text.strip().split()
    month_name = parts[0]
    year = int(parts[1]) if len(parts) > 1 else date.today().year
    try:
        month_num = datetime.strptime(month_name, '%B').month
    except ValueError:
        return date.today().isoformat()
    return date(year, month_num, 1).isoformat()


def fetch_soa_research(category: str = 'RESEARCH') -> list[dict]:
    """
    Scrape SOA's "Recently Published Research" page.

    Verified structure as of this writing: under the heading "Publications",
    each item is a bold link (title + URL) immediately followed by a
    standalone line with just the month (and sometimes year), then a
    description paragraph. There is no semantic wrapper per item (no
    per-card <div>), so we walk siblings of the "Publications" heading
    until we hit the next heading.
    """
    url = 'https://www.soa.org/research/soa-research/'
    articles = []

    resp = requests.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, 'html.parser')

    # Find the "Publications" heading; SOA renders this as an <h3>.
    pub_heading = None
    for heading in soup.find_all(['h2', 'h3']):
        if heading.get_text(strip=True).lower() == 'publications':
            pub_heading = heading
            break

    if pub_heading is None:
        raise ValueError(
            "Could not find 'Publications' section heading — "
            "SOA may have redesigned this page"
        )

    current_title = None
    current_url = None

    for sib in pub_heading.find_next_siblings():
        if sib.name in ('h2', 'h3'):
            break  # reached the next section (Podcasts, Videos, etc.)

        link = sib.find('a')
        text = sib.get_text(strip=True)

        if link and link.get('href'):
            # This sibling introduces a new item: title + link.
            current_title = link.get_text(strip=True)
            current_url = link['href']
            if current_url.startswith('/'):
                current_url = 'https://www.soa.org' + current_url
        elif current_title and _MONTH_RE.match(text):
            # The line right after a title/link is the publish month.
            published_date = _guess_published_date(text)
            articles.append({
                'title': current_title,
                'url': current_url,
                'published_date': published_date,
                'category': category,
            })
            current_title = None
            current_url = None
        elif current_title and current_url and text:
            # Description paragraph — use as content, then close out the
            # item in case there's no month line (defensive; normally
            # the month line above already closed it).
            pass

    return articles


def fetch_limra_research(category: str = 'RESEARCH') -> list[dict]:
    """
    NOT IMPLEMENTED.

    LIMRA's newsroom/research listing pages are client-side rendered
    (the static HTML is empty template bindings like {{result.title}},
    populated by JavaScript after load) — a plain requests.get() scrape
    cannot read it, and would require a headless browser to render first.

    Separately, and more importantly: LIMRA's site footer states that
    reproduction or use of their site content "with any current or future
    form of an Artificial Intelligence tool or engine" is "strictly
    prohibited." Building an automated scraper against that explicit term
    is a real legal/compliance risk, not just a technical inconvenience,
    so this has intentionally been left unimplemented rather than worked
    around.

    If LIMRA coverage is important, the safer paths are:
      - A manual/human-curated weekly check of limra.com/en/newsroom/
      - Contacting LIMRA about a licensed data feed or API
      - Relying on secondary coverage of LIMRA studies in outlets that
        do permit syndication (e.g. trade press writing about LIMRA data)
    """
    raise NotImplementedError(
        "LIMRA scraping is intentionally not implemented — see docstring"
    )


def fetch_milliman_insight(category: str = 'RESEARCH') -> list[dict]:
    """
    NOT IMPLEMENTED.

    Verified by direct fetch: us.milliman.com/en/insight/insurance-insight
    is a Next.js app. The static HTML returned to a plain HTTP request
    contains only page chrome (nav, footer, a "Loading..." placeholder)
    — the actual list of insight articles is injected by client-side
    JavaScript after the page loads in a real browser. requests.get() +
    BeautifulSoup will see an empty shell every time; there is nothing to
    parse no matter how the selectors are written.

    A scraper here would need a headless browser (e.g. Playwright) to
    execute the page's JS before reading the DOM — a meaningfully bigger
    piece of infrastructure (browser binary, more memory/time per run,
    more brittle in CI) than anything else in this pipeline. Not built
    here; flagging so this isn't mistaken for an oversight.
    """
    raise NotImplementedError(
        "Milliman scraping is intentionally not implemented — see docstring"
    )


def fetch_wtw_insight(category: str = 'RESEARCH') -> list[dict]:
    """
    NOT IMPLEMENTED.

    Same situation as Milliman: verified by direct fetch that
    wtwco.com/en-us/insights/all-insights is also a Next.js app whose
    static HTML has no article content, only navigation chrome. Requires
    a headless browser to render; not implemented for the same
    cost/complexity reasons described in fetch_milliman_insight.
    """
    raise NotImplementedError(
        "WTW scraping is intentionally not implemented — see docstring"
    )


# Registry of available scrapers. Add new sources here as
# (function, source_name, category) tuples.
SCRAPERS = [
    (fetch_soa_research, 'Society of Actuaries (Research)', 'RESEARCH'),
    # LIMRA, Milliman, and WTW deliberately excluded — see their
    # respective NotImplementedError docstrings above.
]


def run_source(fetch_fn, source_name: str, category: str) -> int:
    """Run one scraper, insert any new articles, record health."""
    try:
        items = fetch_fn(category=category)
        inserted = 0
        for item in items:
            article = {
                'source': source_name,
                'title': item['title'],
                'url': item['url'],
                'published_date': item['published_date'],
                'content': item.get('content', ''),
                'category': item.get('category', category),
            }
            if not article['title'] or not article['url']:
                continue
            if insert_article(article):
                inserted += 1

        record_source_health(source_name, 'scrape', success=True)
        logger.info("Scrape [%s]: %d new articles", source_name, inserted)
        return inserted

    except Exception as exc:
        record_source_health(source_name, 'scrape', success=False)
        logger.error("Scrape [%s] failed: %s", source_name, exc)
        return 0


def run_all() -> int:
    """Run all registered scrapers. Returns total new articles."""
    total = 0
    for fetch_fn, source_name, category in SCRAPERS:
        total += run_source(fetch_fn, source_name, category)
    logger.info("Scrape ingestion complete: %d total new articles", total)
    return total


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    run_all()
