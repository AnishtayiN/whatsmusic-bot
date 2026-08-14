import json
from pathlib import Path
from typing import List, Dict, Optional

class PlaylistManager:
    def __init__(self, data_dir: str = "data"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.file = self.data_dir / "playlists.json"
        self._load()

    def _load(self):
        if self.file.exists():
            with open(self.file, 'r', encoding='utf-8') as f:
                self.data = json.load(f)
        else:
            self.data = {}

    def _save(self):
        with open(self.file, 'w', encoding='utf-8') as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)

    def get_playlists(self, user_id: int) -> Dict[str, List[str]]:
        return self.data.get(str(user_id), {})

    def create_playlist(self, user_id: int, name: str) -> bool:
        user_key = str(user_id)
        if user_key not in self.data:
            self.data[user_key] = {}
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
        if user_key not in self.data or playlist_name not in self.data[user_key]:
            return False
        if 0 <= index < len(self.data[user_key][playlist_name]):
            del self.data[user_key][playlist_name][index]
            self._save()
            return True
        return False

    def get_songs(self, user_id: int, playlist_name: str) -> List[Dict[str, str]]:
        user_key = str(user_id)
        return self.data.get(user_key, {}).get(playlist_name, [])

    def list_playlists(self, user_id: int) -> List[str]:
        return list(self.get_playlists(user_id).keys())