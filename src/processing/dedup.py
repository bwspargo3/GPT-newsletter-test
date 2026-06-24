"""
Deduplication for ingested articles.
Two-pass strategy:
  1. URL dedup is handled at insert time (UNIQUE constraint in SQLite)
  2. Title similarity dedup using rapidfuzz — removes near-duplicate headlines
"""

import logging
import sqlite3
from rapidfuzz import fuzz

from src.database.db import get_conn

logger = logging.getLogger(__name__)

SIMILARITY_THRESHOLD = 88  # percent match to flag as duplicate


def _normalize_title(title: str) -> str:
    """Lowercase and strip common news prefixes that inflate similarity."""
    return title.lower().strip()


def find_title_duplicates(days_back: int = 2) -> list[int]:
    """
    Within recent articles, find IDs to remove because their title is
    too similar to an earlier article on the same day.
    
    Returns list of IDs to delete (keeps the one with a higher relevance score,
    or the earlier insert if neither is scored yet).
    """
    sql = """
        SELECT id, title, published_date, relevance_score
        FROM articles
        WHERE published_date >= date('now', ? || ' days')
        ORDER BY published_date DESC, id ASC
    """
    with get_conn() as conn:
        rows = conn.execute(sql, (f'-{days_back}',)).fetchall()

    to_delete: set[int] = set()
    checked = []  # list of (id, normalized_title, relevance_score)

    for row in rows:
        if row['id'] in to_delete:
            continue
        norm = _normalize_title(row['title'])
        for prev_id, prev_title, prev_score in checked:
            if prev_id in to_delete:
                continue
            similarity = fuzz.token_sort_ratio(norm, prev_title)
            if similarity >= SIMILARITY_THRESHOLD:
                # Keep the one with the higher relevance score, or the first if tied
                curr_score = row['relevance_score'] or 0.0
                if curr_score > (prev_score or 0.0):
                    to_delete.add(prev_id)
                    checked.remove((prev_id, prev_title, prev_score))
                else:
                    to_delete.add(row['id'])
                break
        else:
            checked.append((row['id'], norm, row['relevance_score']))

    return list(to_delete)


def purge_duplicates(days_back: int = 2) -> int:
    """
    Find and delete title-similar duplicate articles.
    Returns count of removed articles.
    """
    duplicate_ids = find_title_duplicates(days_back)
    if not duplicate_ids:
        logger.info("Dedup: no duplicates found")
        return 0

    placeholders = ','.join('?' * len(duplicate_ids))
    with get_conn() as conn:
        conn.execute(f"DELETE FROM articles WHERE id IN ({placeholders})", duplicate_ids)

    logger.info("Dedup: removed %d duplicate articles", len(duplicate_ids))
    return len(duplicate_ids)


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    removed = purge_duplicates()
    print(f"Removed {removed} duplicates")
