# tag_manager.py - مدیریت برچسب‌ها و فیلترها
import sqlite3
from pathlib import Path
from typing import List, Dict

class TagManager:
    def __init__(self, db_path: str = "data/tags.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS tags (
                    user_id INTEGER,
                    song_id TEXT,
                    tag TEXT,
                    title TEXT,
                    artist TEXT,
                    timestamp TEXT,
                    PRIMARY KEY (user_id, song_id, tag)
                )
            ''')
            conn.execute('CREATE INDEX IF NOT EXISTS idx_user_tag ON tags(user_id, tag)')

    def add_tag(self, user_id: int, song_id: str, tag: str, title: str = "", artist: str = ""):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                INSERT OR REPLACE INTO tags (user_id, song_id, tag, title, artist, timestamp)
                VALUES (?, ?, ?, ?, ?, datetime('now'))
            ''', (user_id, song_id, tag, title, artist))

    def remove_tag(self, user_id: int, song_id: str, tag: str):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('DELETE FROM tags WHERE user_id = ? AND song_id = ? AND tag = ?', (user_id, song_id, tag))

    def get_songs_by_tag(self, user_id: int, tag: str) -> List[Dict]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.execute('SELECT * FROM tags WHERE user_id = ? AND tag = ?', (user_id, tag))
            return [dict(row) for row in cur.fetchall()]

    def get_tags_for_song(self, user_id: int, song_id: str) -> List[str]:
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.execute('SELECT tag FROM tags WHERE user_id = ? AND song_id = ?', (user_id, song_id))
            return [row[0] for row in cur.fetchall()]

    def get_all_tags(self, user_id: int) -> List[str]:
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.execute('SELECT DISTINCT tag FROM tags WHERE user_id = ?', (user_id,))
            return [row[0] for row in cur.fetchall()]