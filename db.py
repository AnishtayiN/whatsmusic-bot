"""db.py - SQLite database layer for users, bans and settings."""
import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)


class DB:
    """User, ban and settings store backed by SQLite (WAL mode)."""

    def __init__(self, path: str = 'data/users.db', default_channel: str = ''):
        self.path = path
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.default_channel = default_channel
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA journal_mode=WAL;')
        conn.execute('PRAGMA synchronous=NORMAL;')
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    last_name TEXT,
                    joined_at TEXT,
                    last_active TEXT,
                    is_banned INTEGER DEFAULT 0,
                    is_admin INTEGER DEFAULT 0,
                    download_count INTEGER DEFAULT 0,
                    recognize_count INTEGER DEFAULT 0,
                    lang TEXT DEFAULT 'fa',
                    quality INTEGER DEFAULT 192
                )
            ''')
            conn.execute('''
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            ''')
            conn.execute(
                'INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)',
                ('channel', self.default_channel),
            )

    def get_user(self, user_id: int) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            cur = conn.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
            row = cur.fetchone()
            return dict(row) if row else None

    def add_user(self, user_id: int, username: str = '', first_name: str = '',
                 last_name: str = '') -> None:
        now = datetime.now().isoformat()
        with self._connect() as conn:
            conn.execute('''
                INSERT INTO users (user_id, username, first_name, last_name, joined_at, last_active)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    username=excluded.username,
                    first_name=excluded.first_name,
                    last_name=excluded.last_name,
                    last_active=excluded.last_active
            ''', (user_id, username, first_name, last_name, now, now))

    def update_activity(self, user_id: int) -> None:
        now = datetime.now().isoformat()
        with self._connect() as conn:
            conn.execute('UPDATE users SET last_active = ? WHERE user_id = ?', (now, user_id))

    def increment_download(self, user_id: int) -> None:
        with self._connect() as conn:
            conn.execute('UPDATE users SET download_count = download_count + 1 WHERE user_id = ?',
                         (user_id,))

    def increment_recognize(self, user_id: int) -> None:
        with self._connect() as conn:
            conn.execute('UPDATE users SET recognize_count = recognize_count + 1 WHERE user_id = ?',
                         (user_id,))

    def ban_user(self, user_id: int) -> None:
        with self._connect() as conn:
            conn.execute('UPDATE users SET is_banned = 1 WHERE user_id = ?', (user_id,))

    def unban_user(self, user_id: int) -> None:
        with self._connect() as conn:
            conn.execute('UPDATE users SET is_banned = 0 WHERE user_id = ?', (user_id,))

    def is_banned(self, user_id: int) -> bool:
        with self._connect() as conn:
            cur = conn.execute('SELECT is_banned FROM users WHERE user_id = ?', (user_id,))
            row = cur.fetchone()
            return bool(row and row[0])

    def get_all_users(self) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            cur = conn.execute('SELECT * FROM users ORDER BY joined_at DESC')
            return [dict(row) for row in cur.fetchall()]

    def get_user_count(self) -> int:
        with self._connect() as conn:
            cur = conn.execute('SELECT COUNT(*) FROM users')
            return cur.fetchone()[0] or 0

    def get_stats(self) -> Dict[str, int]:
        with self._connect() as conn:
            total = conn.execute('SELECT COUNT(*) FROM users').fetchone()[0] or 0
            banned = conn.execute('SELECT COUNT(*) FROM users WHERE is_banned=1').fetchone()[0] or 0
            downloads = conn.execute('SELECT COALESCE(SUM(download_count),0) FROM users').fetchone()[0] or 0
            recognizes = conn.execute('SELECT COALESCE(SUM(recognize_count),0) FROM users').fetchone()[0] or 0
        return {'total': total, 'banned': banned, 'downloads': downloads, 'recognizes': recognizes}

    def get_settings(self, key: str) -> Optional[str]:
        with self._connect() as conn:
            cur = conn.execute('SELECT value FROM settings WHERE key = ?', (key,))
            row = cur.fetchone()
            return row[0] if row else None

    def set_setting(self, key: str, value: str) -> None:
        with self._connect() as conn:
            conn.execute('INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)', (key, value))

    def set_language(self, user_id: int, lang: str) -> None:
        with self._connect() as conn:
            conn.execute('UPDATE users SET lang = ? WHERE user_id = ?', (lang, user_id))

    def get_language(self, user_id: int, default: str = 'fa') -> str:
        with self._connect() as conn:
            cur = conn.execute('SELECT lang FROM users WHERE user_id = ?', (user_id,))
            row = cur.fetchone()
            return row[0] if row and row[0] else default
