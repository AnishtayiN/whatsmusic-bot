import json
from pathlib import Path
from typing import Dict

class QualityManager:
    def __init__(self, data_dir: str = "data"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.file = self.data_dir / "qualities.json"
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

    def set_quality(self, user_id: int, quality: int):
        if quality not in [128, 192, 320]:
            raise ValueError("Quality must be 128, 192, or 320")
        self.data[str(user_id)] = quality
        self._save()

    def get_quality(self, user_id: int) -> int:
        return self.data.get(str(user_id), 192)  # default 192 kbps

    def reset_quality(self, user_id: int):
        if str(user_id) in self.data:
            del self.data[str(user_id)]
            self._save()