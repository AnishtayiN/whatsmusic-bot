import asyncio
import json
import os
from typing import Optional, Dict, Any

from shazamio import Shazam

class Recognizer:
    def __init__(self):
        self.shazam = Shazam()

    async def recognize_file(self, file_path: str) -> Optional[Dict[str, Any]]:
        """تشخیص موزیک از فایل صوتی"""
        if not os.path.exists(file_path):
            return None
        
        try:
            # تشخیص با Shazamio
            result = await self.shazam.recognize_song(file_path)
            if not result:
                return None
            
            # استخراج اطلاعات مفید
            track = result.get('track', {})
            if not track:
                return None
            
            return {
                'title': track.get('title', 'نامشخص'),
                'subtitle': track.get('subtitle', 'خواننده نامشخص'),
                'artists': [track.get('subtitle', '')],
                'album': track.get('sections', [{}])[0].get('metadata', [{}])[0].get('text', ''),
                'genre': track.get('genres', {}).get('primary', ''),
                'release_date': track.get('release-date', ''),
                'coverart': track.get('images', {}).get('coverart', ''),
                'url': track.get('url', ''),
                'shazam_id': track.get('key', '')
            }
        except Exception as e:
            print(f"خطا در تشخیص: {e}")
            return None

    async def recognize_from_url(self, url: str) -> Optional[Dict[str, Any]]:
        """تشخیص موزیک از URL (با دانلود موقت)"""
        # این متد فقط برای لینک‌های مستقیم فایل صوتی کار می‌کند
        # برای لینک‌های ویدئو باید ابتدا دانلود کرد
        return None


    async def search_track(self, query: str, limit: int = 5):
        """جستجوی آهنگ با نام از YouTube"""
        import asyncio
        try:
            ytdlp_path = os.environ.get('YTDLP_PATH', 'yt-dlp')
            cmd = [
                ytdlp_path, "--no-warnings", "--no-playlist", "--no-check-certificates",
                "--user-agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
                f"ytsearch{limit}:{query}",
                "--flat-playlist",
                "--print", "%(title)s|||%(url)s"
            ]
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, _ = await proc.communicate()
            
            results = []
            for line in stdout.decode('utf-8', errors='ignore').splitlines():
                if '|||' in line:
                    title, url = line.split('|||', 1)
                    # استخراج نام آهنگ و خواننده
                    parts = title.split(' - ', 1)
                    if len(parts) == 2:
                        artist, song = parts
                    else:
                        artist, song = 'نامشخص', title
                    results.append({
                        'title': song.strip(),
                        'artist': {'name': artist.strip()},
                        'url': url.strip()
                    })
            return results
        except Exception as e:
            print(f"خطا در جستجو: {e}")
            return []

    async def get_lyrics(self, artist: str, title: str) -> str:
        """دریافت متن ترانه از lyrics.ovh (رایگان)"""
        import urllib.request, urllib.parse, json
        try:
            url = f'https://api.lyrics.ovh/v1/{urllib.parse.quote(artist)}/{urllib.parse.quote(title)}'
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            resp = urllib.request.urlopen(req, timeout=15)
            data = json.loads(resp.read())
            return data.get('lyrics', '')
        except Exception:
            return ''

    def format_result(self, data: Dict[str, Any]) -> str:
        """تبدیل نتیجه به متن زیبا"""
        if not data:
            return "🎵 موزیک شناسایی نشد."
        
        lines = [
            "🎵 **نتیجه تشخیص موزیک:**",
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
        return "\n".join(lines)