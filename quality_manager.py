"""quality_manager.py - Per-user audio quality preferences stored as JSON."""
import json
import os
import tempfile
from pathlib import Path

VALID_QUALITIES = (128, 192, 320)
DEFAULT_QUALITY = 192


class QualityManager:
    """Manage per-user preferred audio quality, persisted atomically."""

    def __init__(self, data_dir: str = 'data', default_quality: int = DEFAULT_QUALITY):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.file = self.data_dir / 'qualities.json'
        self.default_quality = default_quality
        self.data: dict = {}
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
        try:
            fd, tmp_path = tempfile.mkstemp(dir=str(self.data_dir), suffix='.tmp')
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
            os.replace(tmp_path, self.file)
        except OSError:
            pass

    def set_quality(self, user_id: int, quality: int) -> None:
        if quality not in VALID_QUALITIES:
            raise ValueError(f'Quality must be one of {VALID_QUALITIES}')
        self.data[str(user_id)] = quality
        self._save()

    def get_quality(self, user_id: int) -> int:
        quality = self.data.get(str(user_id), self.default_quality)
        try:
            quality = int(quality)
        except (TypeError, ValueError):
            quality = self.default_quality
        return quality if quality in VALID_QUALITIES else self.default_quality

    def reset_quality(self, user_id: int) -> None:
        if str(user_id) in self.data:
            del self.data[str(user_id)]
            self._save()
