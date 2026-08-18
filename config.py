"""config.py - Centralized configuration loaded from environment variables."""
import os
from pathlib import Path
from typing import List

from dotenv import load_dotenv

load_dotenv()


def _parse_int_csv(value: str) -> List[int]:
    return [int(x.strip()) for x in value.split(',') if x.strip().lstrip('-').isdigit()]


BOT_TOKEN = os.getenv('BOT_TOKEN', '').strip()
ADMIN_IDS: List[int] = _parse_int_csv(os.getenv('ADMIN_IDS', ''))
CHANNEL_USERNAME = os.getenv('CHANNEL_USERNAME', '').strip()
DB_PATH = os.getenv('DB_PATH', 'data/users.db')
DOWNLOAD_DIR = os.getenv('DOWNLOAD_DIR', 'downloads')
COOKIES_FILE = os.getenv('COOKIES_FILE', '').strip()
DEFAULT_LANG = os.getenv('DEFAULT_LANG', 'fa').strip().lower()
DEFAULT_QUALITY = int(os.getenv('DEFAULT_QUALITY', '192'))
MAX_FILE_SIZE_MB = int(os.getenv('MAX_FILE_SIZE_MB', '50'))
DOWNLOAD_RETRIES = int(os.getenv('DOWNLOAD_RETRIES', '3'))
DOWNLOAD_DELAY = float(os.getenv('DOWNLOAD_DELAY', '2'))
MAX_SEARCH_RESULTS = int(os.getenv('MAX_SEARCH_RESULTS', '5'))

DOWNLOAD_PATH = Path(DOWNLOAD_DIR)
DATA_PATH = Path(DB_PATH).parent
DOWNLOAD_PATH.mkdir(parents=True, exist_ok=True)
DATA_PATH.mkdir(parents=True, exist_ok=True)

SUPPORTED_AUDIO_EXTS = ('.mp3', '.m4a', '.wav', '.flac', '.ogg', '.opus', '.aac')
SUPPORTED_MEDIA_EXTS = SUPPORTED_AUDIO_EXTS + ('.mp4', '.webm', '.mkv', '.mov')

TELEGRAM_MAX_MSG = 4096
