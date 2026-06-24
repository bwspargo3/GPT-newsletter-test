"""
Daily digest builder.
Fetches scored articles from the last 24h, groups by category,
renders the HTML template, and returns the output.
"""

import logging
import yaml
from datetime import date
from pathlib import Path
from collections import defaultdict

from jinja2 import Environment, FileSystemLoader

from src.database.db import fetch_for_digest, fetch_latest_economic, mark_digest_sent

logger = logging.getLogger(__name__)

CATEGORIES_CONFIG = Path('config/categories.yaml')
TEMPLATES_DIR = Path('templates')


def _load_category_meta() -> dict:
    """Load category display names and priorities."""
    config = yaml.safe_load(CATEGORIES_CONFIG.read_text())
    return config.get('categories', {})


def _group_by_category(articles: list, category_meta: dict) -> list[dict]:
    """Group articles by category, sorted by category priority."""
    grouped = defaultdict(list)
    for row in articles:
        cat = row['category'] or 'MARKET_INTELLIGENCE'
        grouped[cat].append({
            'title': row['title'],
            'url': row['url'],
            'source': row['source'],
            'summary': row['summary'] or '',
            'why_it_matters': row['why_it_matters'] or '',
            'relevance_score': row['relevance_score'],
            'published_date': row['published_date'],
        })

    result = []
    for cat_key, meta in sorted(category_meta.items(),
                                 key=lambda x: x[1].get('priority', 99)):
        if cat_key in grouped:
            result.append({
                'key': cat_key,
                'label': meta.get('label', cat_key),
                'articles': sorted(grouped[cat_key],
                                   key=lambda a: a['relevance_score'] or 0,
                                   reverse=True),
            })
    return result


def build_daily(days_back: int = 1, min_score: float = 6.5,
                max_articles: int = 12, mark_sent: bool = True) -> tuple[str, int]:
    """
    Build the daily HTML digest.
    Returns (html_string, article_count).
    """
    articles = fetch_for_digest(min_score=min_score, days_back=days_back,
                                limit=max_articles)
    logger.info("Building daily digest with %d articles", len(articles))

    category_meta = _load_category_meta()
    grouped_categories = _group_by_category(articles, category_meta)

    economic_rows = fetch_latest_economic()
    economic = [
        {
            'label': row['label'],
            'value': f"{row['value']:.2f}",
            'unit': row['unit'],
        }
        for row in economic_rows
    ]

    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=True,
    )
    template = env.get_template('daily.html')

    html = template.render(
        digest_date=date.today().strftime('%B %-d, %Y'),
        categories=grouped_categories,
        economic=economic,
        total_articles=len(articles),
    )

    if mark_sent and articles:
        mark_digest_sent([row['id'] for row in articles])

    return html, len(articles)


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    html, count = build_daily(mark_sent=False)
    Path('data/preview_daily.html').write_text(html, encoding='utf-8')
    print(f"Preview written: {count} articles → data/preview_daily.html")
