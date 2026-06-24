
CREATE TABLE IF NOT EXISTS articles(
 id INTEGER PRIMARY KEY,
 title TEXT,
 url TEXT UNIQUE,
 source TEXT,
 published TEXT,
 content TEXT,
 category TEXT,
 relevance REAL,
 summary TEXT,
 why_it_matters TEXT
);
