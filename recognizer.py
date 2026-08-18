"""recognizer.py - Music recognition with Shazam, track search and lyrics."""
import asyncio
import json
import logging
import os
import urllib.parse
from typing import Optional, Dict, Any, List

from shazamio import Shazam

logger = logging.getLogger(__name__)

USER_AGENT = (
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
    'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'
)


class Recognizer:
    """Recognize music from audio files and search for tracks."""

    def __init__(self):
        self.shazam = Shazam()

    async def recognize_file(self, file_path: str) -> Optional[Dict[str, Any]]:
        """Recognize a track from a local audio file via Shazam."""
        if not file_path or not os.path.exists(file_path):
            return None

        try:
            result = await self.shazam.recognize_song(file_path)
        except Exception as e:
            logger.error(f'Shazam recognition error: {e}')
            return None

        if not result:
            return None

        track = result.get('track', {})
        if not track:
            return None

        metadata = track.get('sections', [{}])[0].get('metadata', []) if track.get('sections') else []
        album = metadata[0].get('text', '') if metadata else ''

        return {
            'title': track.get('title', 'نامشخص'),
            'subtitle': track.get('subtitle', 'خواننده نامشخص'),
            'artists': [track.get('subtitle', '')],
            'album': album,
            'genre': track.get('genres', {}).get('primary', ''),
            'release_date': track.get('release-date', ''),
            'coverart': track.get('images', {}).get('coverart', ''),
            'url': track.get('url', ''),
            'shazam_id': track.get('key', ''),
        }

    async def search_track(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Search for tracks on YouTube using yt-dlp's flat-playlist search."""
        if not query or not query.strip():
            return []
        query = query.strip()

        ytdlp_path = os.environ.get('YTDLP_PATH', 'yt-dlp')
        cmd = [
            ytdlp_path, '--no-warnings', '--no-playlist', '--no-check-certificates',
            '--user-agent', USER_AGENT,
            f'ytsearch{limit}:{query}',
            '--flat-playlist',
            '--print', '%(title)s|||%(url)s',
        ]

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()
        except FileNotFoundError:
            logger.error('yt-dlp binary not found for search. Set YTDLP_PATH.')
            return []
        except Exception as e:
            logger.error(f'Search error: {e}')
            return []

        results: List[Dict[str, Any]] = []
        for line in stdout.decode('utf-8', errors='ignore').splitlines():
            if '|||' not in line:
                continue
            title, url = line.split('|||', 1)
            title = title.strip()
            url = url.strip()
            if not title:
                continue
            artist, song = self._split_title(title)
            results.append({'title': song, 'artist': {'name': artist}, 'url': url})
        return results

    @staticmethod
    def _split_title(title: str) -> tuple:
        """Best-effort split of a video title into (artist, song)."""
        for sep in (' - ', ' — ', ' – ', ' | '):
            if sep in title:
                artist, song = title.split(sep, 1)
                return artist.strip(), song.strip()
        # Heuristic: "Artist - Topic" suffix from YouTube music channels
        if title.lower().endswith(' - topic'):
            return title[:-7].strip(), title
        return 'نامشخص', title

    async def get_lyrics(self, artist: str, title: str) -> str:
        """Fetch lyrics from the free lyrics.ovh API (async)."""
        if not artist or not title:
            return ''

        # Use asyncio.to_thread to avoid blocking the event loop
        return await asyncio.to_thread(self._fetch_lyrics_sync, artist, title)

    def _fetch_lyrics_sync(self, artist: str, title: str) -> str:
        import urllib.request
        url = f'https://api.lyrics.ovh/v1/{urllib.parse.quote(artist)}/{urllib.parse.quote(title)}'
        req = urllib.request.Request(url, headers={'User-Agent': USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode('utf-8', errors='ignore'))
                lyrics = data.get('lyrics', '') or ''
                return lyrics.strip()
        except Exception as e:
            logger.debug(f'Lyrics fetch failed for {artist} - {title}: {e}')
            return ''

    def format_result(self, data: Optional[Dict[str, Any]]) -> str:
        """Format a recognition result into a readable message."""
        if not data:
            return '🎵 موسیقی شناسایی نشد.'

        lines = [
            '🎵 **نتیجه تشخیص موسیقی:**',
            f"🎶 عنوان: {data.get('title', 'نامشخص')}",
            f"👤 خواننده: {data.get('subtitle', 'نامشخص')}",
        ]
        if data.get('album'):
            lines.append(f"💿 آلبوم: {data['album']}")
        if data.get('genre'):
            lines.append(f"🎸 سبک: {data['genre']}")
        if data.get('release_date'):
            lines.append(f"📅 تاریخ انتشار: {data['release_date']}")
        if data.get('url'):
            lines.append(f"🔗 لینک: {data['url']}")
        return '\n'.join(lines)
