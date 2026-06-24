CREATE TABLE IF NOT EXISTS articles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    title TEXT NOT NULL,
    url TEXT UNIQUE NOT NULL,
    published_date DATE,
    content TEXT,
    category TEXT,
    relevance_score REAL,
    summary TEXT,
    why_it_matters TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    included_in_digest INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_articles_published ON articles(published_date DESC);
CREATE INDEX IF NOT EXISTS idx_articles_category ON articles(category);
CREATE INDEX IF NOT EXISTS idx_articles_relevance ON articles(relevance_score DESC);
CREATE INDEX IF NOT EXISTS idx_articles_digest ON articles(included_in_digest, published_date DESC);

CREATE TABLE IF NOT EXISTS economic_data (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    series_id TEXT NOT NULL,
    label TEXT NOT NULL,
    value REAL,
    unit TEXT,
    fetched_date DATE NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(series_id, fetched_date)
);

CREATE TABLE IF NOT EXISTS source_health (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_name TEXT NOT NULL,
    source_type TEXT NOT NULL,
    last_success TIMESTAMP,
    last_attempt TIMESTAMP,
    consecutive_failures INTEGER DEFAULT 0,
    UNIQUE(source_name)
);

CREATE TABLE IF NOT EXISTS naic_pages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    url TEXT UNIQUE NOT NULL,
    label TEXT,
    last_hash TEXT,
    last_checked TIMESTAMP,
    change_detected INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS digests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    digest_type TEXT NOT NULL,
    digest_date DATE NOT NULL,
    article_count INTEGER,
    html_path TEXT,
    sent_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
