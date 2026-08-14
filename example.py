#!/usr/bin/env python3
"""
مثال ساده برای استفاده از What's Music Bot به صورت برنامه‌ای
"""

import asyncio
from downloader import Downloader
from recognizer import Recognizer

async def example():
    # ۱. دانلود
    downloader = Downloader(output_dir="music")
    result = await downloader.download("https://www.youtube.com/watch?v=dQw4w9WgXcQ", extract_audio=True)
    file_path = result[0]['filename'] if result else None
    
    if file_path:
        print(f"دانلود شد: {file_path}")
        
        # ۲. تشخیص
        recognizer = Recognizer()
        result = await recognizer.recognize_file(file_path)
        print(recognizer.format_result(result))

if __name__ == "__main__":
    asyncio.run(example())