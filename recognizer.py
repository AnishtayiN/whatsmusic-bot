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