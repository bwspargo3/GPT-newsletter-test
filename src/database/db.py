
import sqlite3
from pathlib import Path
DB=Path('data/articles.db')
def get_conn():
    DB.parent.mkdir(exist_ok=True)
    return sqlite3.connect(DB)
