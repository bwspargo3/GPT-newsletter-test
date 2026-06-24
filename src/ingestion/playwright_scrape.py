"""
Headless-browser scraper for sources whose article listings are rendered
client-side (no content present in the raw HTML response).

This is a heavier, slower, more fragile tier than rss.py or web_scrape.py.
It exists only because Milliman and WTW's insight pages are Next.js apps
that inject their article lists via JavaScript after page load — a plain
requests.get() returns an empty shell no matter what selectors you write
against it (confirmed by direct fetch; see notes in each fetch_* function).

IMPORTANT — selectors here are NOT verified against a live render.
This was written without the ability to load these pages in a real
browser and inspect the rendered DOM (sandboxed, no network egress to
test against). The CSS selectors below are informed best guesses based
on what Next.js / typical card-listing markup looks like, not confirmed
fact. Treat the first real run as the actual test. If a source returns
zero articles, see "HOW TO FIX A BROKEN SELECTOR" at the bottom of this
file for a five-minute manual fix using browser devtools.

Each scraper function returns a list of article dicts in the same shape
insert_article() expects, so run_all() can feed them through the normal
pipeline, mirroring web_scrape.py's structure.
"""

import logging
from datetime import date

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

from src.database.db import insert_article, record_source_health

logger = logging.getLogger(__name__)

USER_AGENT = 'Mozilla/5.0 (compatible; LA-Intelligence/1.0; actuarial research bot)'

# How long to wait for the page's JS to populate content, in milliseconds.
# These sites are content-heavy enterprise marketing sites (slow third-party
# scripts, analytics, cookie banners) so this is generous on purpose —
# better to spend an extra few seconds than return a false "zero results".
RENDER_TIMEOUT_MS = 20_000


def _render_page(url: str, wait_selector: str) -> str:
    """
    Launch headless Chromium, navigate to url, wait until wait_selector
    appears in the DOM (i.e. the client-side JS has actually populated
    content, not just that the page "loaded"), and return the fully
    rendered HTML.

    Raises on timeout or navigation failure — callers should catch and
    record_source_health(success=False), same pattern as every other
    ingestion module in this project.
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            page = browser.new_page(user_agent=USER_AGENT)
            page.goto(url, timeout=RENDER_TIMEOUT_MS, wait_until='domcontentloaded')
            page.wait_for_selector(wait_selector, timeout=RENDER_TIMEOUT_MS)
            html = page.content()
            return html
        finally:
            browser.close()


def fetch_milliman_insight(category: str = 'RESEARCH') -> list[dict]:
    """
    Render and scrape Milliman's "Insurance insight" listing page.

    UNVERIFIED SELECTORS: Milliman's site runs Next.js on Sitecore.
    Sitecore-backed Next.js card listings commonly render as repeated
    <article> or <a> blocks with a heading and a short description; the
    selector strategy below looks for anchor tags inside the main content
    region whose href contains '/en/insight/' (Milliman's confirmed URL
    pattern for individual articles, e.g.
    /en/insight/2025-milliman-medical-index) and takes the nearest
    heading text as the title. This is a heuristic, not a confirmed
    selector — see the file-level docstring.
    """
    url = 'https://us.milliman.com/en/insight/insurance-insight'
    html = _render_page(url, wait_selector='a[href*="/en/insight/"]')

    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, 'html.parser')

    articles = []
    seen_urls = set()

    for link in soup.select('a[href*="/en/insight/"]'):
        href = link.get('href', '')
        if not href or href.rstrip('/').endswith('/en/insight'):
            continue  # skip nav links back to the listing page itself
        full_url = href if href.startswith('http') else f'https://us.milliman.com{href}'
        if full_url in seen_urls:
            continue

        # Prefer a heading tag's text — the link's own get_text() will
        # concatenate title + description into one run-on string if the
        # whole card (title, blurb, etc.) is wrapped in a single <a>, so
        # we look for a heading first rather than trusting raw link text.
        heading = link.find(['h1', 'h2', 'h3', 'h4'])
        if not heading:
            container = link.find_parent(['article', 'div', 'li'])
            if container:
                heading = container.find(['h1', 'h2', 'h3', 'h4'])
        title = heading.get_text(strip=True) if heading else link.get_text(strip=True)

        if not title or len(title) < 8:
            continue  # too short to be a real article title; likely nav chrome

        seen_urls.add(full_url)
        articles.append({
            'title': title,
            'url': full_url,
            'published_date': date.today().isoformat(),
            'category': category,
        })

    return articles


def fetch_wtw_insight(category: str = 'RESEARCH') -> list[dict]:
    """
    Render and scrape WTW's "All Insights" listing page.

    UNVERIFIED SELECTORS: same situation as Milliman. WTW's confirmed
    individual-article URL pattern is /en-us/insights/YYYY/MM/slug (seen
    in search results, e.g. /en-us/insights/2026/03/...). The selector
    strategy looks for anchors matching that date-stamped path pattern.
    """
    url = 'https://www.wtwco.com/en-us/insights/all-insights?sort=actual_date+desc'
    html = _render_page(url, wait_selector='a[href*="/insights/20"]')

    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, 'html.parser')

    articles = []
    seen_urls = set()

    for link in soup.select('a[href*="/insights/20"]'):
        href = link.get('href', '')
        if not href:
            continue
        full_url = href if href.startswith('http') else f'https://www.wtwco.com{href}'
        if full_url in seen_urls:
            continue
        # WTW's pattern is /insights/YYYY/MM/slug — require that shape to
        # filter out category/trending-topic links like /insights/all-insights
        path_parts = full_url.split('/insights/', 1)[-1].split('/')
        if len(path_parts) < 3 or not path_parts[0][:4].isdigit():
            continue

        heading = link.find(['h1', 'h2', 'h3', 'h4'])
        if not heading:
            container = link.find_parent(['article', 'div', 'li'])
            if container:
                heading = container.find(['h1', 'h2', 'h3', 'h4'])
        title = heading.get_text(strip=True) if heading else link.get_text(strip=True)

        if not title or len(title) < 8:
            continue

        seen_urls.add(full_url)
        articles.append({
            'title': title,
            'url': full_url,
            'published_date': date.today().isoformat(),
            'category': category,
        })

    return articles


# Registry of available headless scrapers.
HEADLESS_SCRAPERS = [
    (fetch_milliman_insight, 'Milliman (Insight)', 'RESEARCH'),
    (fetch_wtw_insight, 'WTW (Insights)', 'RESEARCH'),
]


def run_source(fetch_fn, source_name: str, category: str) -> int:
    """Run one headless scraper, insert any new articles, record health."""
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

        if inserted == 0 and len(items) == 0:
            logger.warning(
                "Headless scrape [%s]: 0 articles found — this likely means "
                "the page structure changed or a selector is wrong, not "
                "that there's genuinely no new content. See "
                "'HOW TO FIX A BROKEN SELECTOR' in playwright_scrape.py",
                source_name,
            )

        record_source_health(source_name, 'headless_scrape', success=True)
        logger.info("Headless scrape [%s]: %d new articles", source_name, inserted)
        return inserted

    except PlaywrightTimeoutError as exc:
        record_source_health(source_name, 'headless_scrape', success=False)
        logger.error(
            "Headless scrape [%s] timed out waiting for content: %s",
            source_name, exc,
        )
        return 0
    except Exception as exc:
        record_source_health(source_name, 'headless_scrape', success=False)
        logger.error("Headless scrape [%s] failed: %s", source_name, exc)
        return 0


def run_all() -> int:
    """Run all registered headless scrapers. Returns total new articles."""
    total = 0
    for fetch_fn, source_name, category in HEADLESS_SCRAPERS:
        total += run_source(fetch_fn, source_name, category)
    logger.info("Headless scrape ingestion complete: %d total new articles", total)
    return total


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    run_all()


# ─────────────────────────────────────────────────────────────────────────
# HOW TO FIX A BROKEN SELECTOR
#
# If Milliman or WTW consistently return 0 articles, the selector guesses
# above are wrong for the actual rendered page. This is a 5-minute fix:
#
# 1. Open the page in a normal browser (e.g. https://us.milliman.com/en/
#    insight/insurance-insight).
# 2. Right-click an article title in the list → "Inspect".
# 3. Look at the surrounding HTML: what tag wraps the title? What's the
#    href pattern on the link? Is the title in an <h2>/<h3>, or is it the
#    link text itself?
# 4. Update the CSS selector string passed to soup.select(...) in the
#    relevant fetch_* function above to match what you see.
# 5. Re-run: python -m src.ingestion.playwright_scrape
#
# A faster way to check without editing code: run Playwright's own
# codegen tool locally (not in CI) to record selectors interactively:
#   playwright codegen https://us.milliman.com/en/insight/insurance-insight
# ─────────────────────────────────────────────────────────────────────────
