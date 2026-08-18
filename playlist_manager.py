"""playlist_manager.py - Per-user playlists stored as JSON."""
import json
import os
import tempfile
from pathlib import Path
from typing import List, Dict, Optional


class PlaylistManager:
    """Manage per-user playlists persisted to a JSON file (atomic writes)."""

    def __init__(self, data_dir: str = 'data'):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.file = self.data_dir / 'playlists.json'
        self.data: Dict[str, Dict[str, List[Dict[str, str]]]] = {}
        self._load()

    def _load(self) -> None:
        if not self.file.exists():
            self.data = {}
            return
        try:
            with open(self.file, 'r', encoding='utf-8') as f:
                self.data = json.load(f)
        except (json.JSONDecodeError, OSError):
            self.data = {}

    def _save(self) -> None:
        """Atomically write the JSON data to disk."""
        try:
            fd, tmp_path = tempfile.mkstemp(dir=str(self.data_dir), suffix='.tmp')
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
            os.replace(tmp_path, self.file)
        except OSError:
            pass

    def get_playlists(self, user_id: int) -> Dict[str, List[Dict[str, str]]]:
        return self.data.get(str(user_id), {})

    def create_playlist(self, user_id: int, name: str) -> bool:
        user_key = str(user_id)
        self.data.setdefault(user_key, {})
        if name in self.data[user_key]:
            return False
        self.data[user_key][name] = []
        self._save()
        return True

    def delete_playlist(self, user_id: int, name: str) -> bool:
        user_key = str(user_id)
        if user_key not in self.data or name not in self.data[user_key]:
            return False
        del self.data[user_key][name]
        self._save()
        return True

    def add_song(self, user_id: int, playlist_name: str, song: Dict[str, str]) -> bool:
        user_key = str(user_id)
        if user_key not in self.data or playlist_name not in self.data[user_key]:
            return False
        self.data[user_key][playlist_name].append(song)
        self._save()
        return True

    def remove_song(self, user_id: int, playlist_name: str, index: int) -> bool:
        user_key = str(user_id)
        songs = self.data.get(user_key, {}).get(playlist_name, [])
        if not (0 <= index < len(songs)):
            return False
        del songs[index]
        self._save()
        return True

    def get_songs(self, user_id: int, playlist_name: str) -> List[Dict[str, str]]:
        return self.data.get(str(user_id), {}).get(playlist_name, [])

    def list_playlists(self, user_id: int) -> List[str]:
        return list(self.get_playlists(user_id).keys())
