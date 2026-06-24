"""
Database connection and helper utilities.
"""

import sqlite3
import logging
from pathlib import Path
from datetime import datetime, date

DB_PATH = Path('data/articles.db')
SCHEMA_PATH = Path('src/database/schema.sql')

logger = logging.getLogger(__name__)


def get_conn() -> sqlite3.Connection:
    """Return a SQLite connection with row_factory set."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    """Create tables from schema.sql if they don't exist."""
    schema = SCHEMA_PATH.read_text()
    params = (source_name, source_type, now, now) if success else (source_name, source_type, now)
    with get_conn() as conn:
        conn.execute(sql, params)

    logger.info("Database initialized at %s", DB_PATH)


def insert_article(article: dict) -> bool:
    """
    Insert an article. Returns True if inserted, False if URL already exists.
    
    Expected keys: source, title, url, published_date, content, category
    Optional keys: relevance_score, summary, why_it_matters
    """
    sql = """
        INSERT OR IGNORE INTO articles
            (source, title, url, published_date, content, category,
             relevance_score, summary, why_it_matters)
        VALUES
            (:source, :title, :url, :published_date, :content, :category,
             :relevance_score, :summary, :why_it_matters)
    """
    defaults = {
        'relevance_score': None,
        'summary': None,
        'why_it_matters': None,
        'category': None,
    }
    row = {**defaults, **article}
    with get_conn() as conn:
        cur = conn.execute(sql, row)
        return cur.rowcount > 0


def fetch_unscored(limit: int = 100) -> list[sqlite3.Row]:
    """Articles that have no relevance score yet."""
    sql = """
        SELECT * FROM articles
        WHERE relevance_score IS NULL
        ORDER BY published_date DESC
        LIMIT ?
    """
    with get_conn() as conn:
        return conn.execute(sql, (limit,)).fetchall()


def fetch_for_digest(min_score: float = 6.0, days_back: int = 1,
                     limit: int = 15) -> list[sqlite3.Row]:
    """High-relevance articles from the last N days, not yet in a digest."""
    sql = """
        SELECT * FROM articles
        WHERE relevance_score >= ?
          AND published_date >= date('now', ? || ' days')
          AND included_in_digest = 0
        ORDER BY relevance_score DESC, published_date DESC
        LIMIT ?
    """
    with get_conn() as conn:
        return conn.execute(sql, (min_score, f'-{days_back}', limit)).fetchall()


def mark_digest_sent(article_ids: list[int]):
    """Flag articles as included in a digest."""
    if not article_ids:
        return
    placeholders = ','.join('?' * len(article_ids))
    with get_conn() as conn:
        conn.execute(
            f"UPDATE articles SET included_in_digest=1 WHERE id IN ({placeholders})",
            article_ids
        )


def update_article_processing(article_id: int, category: str,
                               relevance_score: float, summary: str,
                               why_it_matters: str):
    """Write Groq output back to the article row."""
    sql = """
        UPDATE articles
        SET category=?, relevance_score=?, summary=?, why_it_matters=?
        WHERE id=?
    """
    with get_conn() as conn:
        conn.execute(sql, (category, relevance_score, summary, why_it_matters, article_id))


def upsert_economic_data(series_id: str, label: str, value: float, unit: str):
    """Insert or replace today's economic data point."""
    sql = """
        INSERT INTO economic_data (series_id, label, value, unit, fetched_date)
        VALUES (?, ?, ?, ?, date('now'))
        ON CONFLICT(series_id, fetched_date) DO UPDATE SET value=excluded.value
    """
    with get_conn() as conn:
        conn.execute(sql, (series_id, label, value, unit))


def fetch_latest_economic() -> list[sqlite3.Row]:
    """Most recent value per series."""
    sql = """
        SELECT series_id, label, value, unit, fetched_date
        FROM economic_data
        WHERE fetched_date = (SELECT MAX(fetched_date) FROM economic_data)
        ORDER BY series_id
    """
    with get_conn() as conn:
        return conn.execute(sql).fetchall()


def record_source_health(source_name: str, source_type: str, success: bool):
    """Track ingestion health per source."""
    now = datetime.utcnow().isoformat()
    if success:
        sql = """
            INSERT INTO source_health (source_name, source_type, last_success, last_attempt, consecutive_failures)
            VALUES (?, ?, ?, ?, 0)
            ON CONFLICT(source_name) DO UPDATE SET
                last_success=excluded.last_success,
                last_attempt=excluded.last_attempt,
                consecutive_failures=0
        """
    else:
        sql = """
            INSERT INTO source_health (source_name, source_type, last_attempt, consecutive_failures)
            VALUES (?, ?, ?, 1)
            ON CONFLICT(source_name) DO UPDATE SET
                last_attempt=excluded.last_attempt,
                consecutive_failures=consecutive_failures+1
        """
    with get_conn() as conn:
        conn.execute(sql, (source_name, source_type, now) if success else (source_name, source_type, now))


def upsert_naic_page(url: str, label: str, new_hash: str) -> bool:
    """
    Update NAIC page hash. Returns True if the hash changed (new content detected).
    """
    with get_conn() as conn:
        row = conn.execute("SELECT last_hash FROM naic_pages WHERE url=?", (url,)).fetchone()
        changed = row is None or row['last_hash'] != new_hash
        conn.execute("""
            INSERT INTO naic_pages (url, label, last_hash, last_checked, change_detected)
            VALUES (?, ?, ?, datetime('now'), ?)
            ON CONFLICT(url) DO UPDATE SET
                last_hash=excluded.last_hash,
                last_checked=excluded.last_checked,
                change_detected=excluded.change_detected
        """, (url, label, new_hash, int(changed)))
        return changed
