"""
GitHub Pages archive publisher.
Writes daily HTML to archive/YYYY/MM/DD.html
and updates archive/index.html with a list of recent digests.
"""

import logging
from datetime import date
from pathlib import Path

logger = logging.getLogger(__name__)

ARCHIVE_DIR = Path('archive')


def publish_daily(html: str, digest_date: date = None) -> Path:
    """
    Write the daily digest HTML to the archive directory.
    Returns the output path.
    """
    if digest_date is None:
        digest_date = date.today()

    output_path = ARCHIVE_DIR / str(digest_date.year) / f"{digest_date.month:02d}" / f"{digest_date.day:02d}.html"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding='utf-8')
    logger.info("Published archive: %s", output_path)

    _update_index()
    return output_path


def _update_index():
    """Rebuild archive/index.html from all published daily digests."""
    all_digests = sorted(ARCHIVE_DIR.rglob('*/??/[0-9][0-9].html'), reverse=True)

    links = []
    for path in all_digests[:90]:  # last 90 days
        parts = path.parts  # ('archive', 'YYYY', 'MM', 'DD.html')
        if len(parts) >= 4:
            year = parts[-3]
            month = parts[-2]
            day = parts[-1].replace('.html', '')
            try:
                d = date(int(year), int(month), int(day))
                links.append({
                    'path': str(path.relative_to(ARCHIVE_DIR)),
                    'label': d.strftime('%B %-d, %Y'),
                })
            except ValueError:
                continue

    index_html = _render_index(links)
    index_path = ARCHIVE_DIR / 'index.html'
    index_path.write_text(index_html, encoding='utf-8')
    logger.info("Updated archive index: %d entries", len(links))


def _render_index(links: list[dict]) -> str:
    items = '\n'.join(
        f'<li><a href="{item["path"]}">{item["label"]}</a></li>'
        for item in links
    )
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>L&A Actuarial Intelligence – Archive</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <style>
    body {{ font-family: Georgia, serif; max-width: 640px; margin: 40px auto; padding: 0 20px; color: #1a1a1a; }}
    h1 {{ font-size: 1.4rem; border-bottom: 2px solid #1a3a5c; padding-bottom: 8px; }}
    ul {{ list-style: none; padding: 0; }}
    li {{ padding: 6px 0; border-bottom: 1px solid #eee; }}
    a {{ color: #1a3a5c; text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
    .meta {{ color: #666; font-size: 0.85rem; margin-top: 4px; }}
  </style>
</head>
<body>
  <h1>L&amp;A Actuarial Intelligence — Archive</h1>
  <p class="meta">Daily briefings for life &amp; annuity actuarial consultants.</p>
  <ul>
    {items}
  </ul>
</body>
</html>"""
