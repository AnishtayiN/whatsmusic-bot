"""utils.py - Helper functions for filenames, platforms, durations and cleanup."""
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional, List

# Regex matching an http(s) URL anywhere in a string
URL_RE = re.compile(r'https?://\S+', re.IGNORECASE)

# Extensions used by the bot for audio and media files
AUDIO_EXTS = ('.mp3', '.m4a', '.wav', '.flac', '.ogg', '.opus', '.aac')
MEDIA_EXTS = AUDIO_EXTS + ('.mp4', '.webm', '.mkv', '.mov')

# Characters not allowed in filenames on common operating systems
_INVALID_FILENAME_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def sanitize_filename(name: str, max_length: int = 200) -> str:
    """Sanitize a filename for the filesystem, trimming length and invalid chars.

    A name that is empty or made only of separator/junk chars falls back to 'file'.
    """
    name = _INVALID_FILENAME_RE.sub('_', name or '')
    name = name.strip().strip('.')
    if len(name) > max_length:
        name = name[:max_length]
    # If the name is all underscores/spaces, fall back to a default
    if not name or not name.replace('_', '').strip():
        return 'file'
    return name


def ensure_dir(path: Path) -> Path:
    """Ensure a directory exists and return it."""
    path.mkdir(parents=True, exist_ok=True)
    return path


def cleanup_file(path) -> None:
    """Delete a file if it exists. Accepts str or Path. Never raises."""
    try:
        p = Path(path)
        if p.exists():
            p.unlink()
    except Exception:
        pass


def cleanup_dir(path) -> None:
    """Remove a directory tree if it exists. Never raises."""
    try:
        p = Path(path)
        if p.exists():
            shutil.rmtree(p, ignore_errors=True)
    except Exception:
        pass


def get_platform_audio_player() -> Optional[str]:
    """Detect a system audio player for CLI playback."""
    if sys.platform == 'win32':
        return 'start'
    if sys.platform == 'darwin':
        return 'afplay'
    for cmd in ('mpv', 'vlc', 'ffplay'):
        try:
            if subprocess.run(['which', cmd], capture_output=True).returncode == 0:
                return cmd
        except Exception:
            continue
    return None


def format_duration(seconds) -> str:
    """Convert seconds to HH:MM:SS or MM:SS."""
    try:
        seconds = int(seconds or 0)
    except (TypeError, ValueError):
        seconds = 0
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    if h:
        return f'{h:02d}:{m:02d}:{s:02d}'
    return f'{m:02d}:{s:02d}'


def extract_platform(url: str) -> str:
    """Identify the platform of a media URL."""
    if not url:
        return 'Unknown'
    lower = url.lower()
    if 'tiktok.com' in lower:
        return 'TikTok'
    if 'youtube.com' in lower or 'youtu.be' in lower:
        return 'YouTube'
    if 'instagram.com' in lower:
        return 'Instagram'
    if 'soundcloud.com' in lower:
        return 'SoundCloud'
    if 'spotify.com' in lower:
        return 'Spotify'
    if 'vimeo.com' in lower:
        return 'Vimeo'
    if URL_RE.match(url):
        return 'Web'
    return 'Unknown'


def is_url(text: str) -> bool:
    """Return True if text looks like an http(s) URL."""
    return bool(text and URL_RE.match(text.strip()))


def extract_urls(text: str) -> List[str]:
    """Return all http(s) URLs found in text."""
    return URL_RE.findall(text) if text else []


def split_artist_title(text: str) -> tuple:
    """Split 'Artist - Title' or 'Artist Title' into (artist, title).

    Falls back to first word as artist when no separator is present.
    Returns ('', '') when input is empty.
    """
    text = (text or '').strip()
    if not text:
        return '', ''
    for sep in (' - ', ' — ', ' – ', ' by '):
        if sep in text:
            parts = text.split(sep, 1)
            return parts[0].strip(), parts[1].strip()
    parts = text.split(' ', 1)
    artist = parts[0].strip()
    title = parts[1].strip() if len(parts) > 1 else ''
    return artist, title


def safe_open(path, mode: str = 'rb'):
    """Open a file with the caller responsible for closing. Kept for compatibility."""
    return open(path, mode)
