#!/usr/bin/env python3
"""
🎵 What's Music Bot
دانلود و تشخیص موزیک از تیک‌تاک، یوتوب، اینستاگرام و ساندکلود
با استفاده از yt-dlp و shazamio
"""

import argparse
import asyncio
import sys
from pathlib import Path

from downloader import Downloader
from recognizer import Recognizer
from utils import ensure_dir, get_platform_audio_player

async def main():
    parser = argparse.ArgumentParser(
        description="🎵 دانلود و تشخیص موزیک از شبکه‌های اجتماعی",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
مثال‌ها:
  python main.py -u "https://www.tiktok.com/@user/video/123" -o ./music
  python main.py -u "https://www.youtube.com/watch?v=abc" --recognize
  python main.py -f song.mp3 --recognize
  python main.py -u "https://www.instagram.com/reel/xyz" --cookies cookies.txt
        """
    )
    
    parser.add_argument(
        "-u", "--url",
        help="لینک ویدئو/صوت (تیک‌تاک، یوتوب، اینستاگرام، ساندکلود)"
    )
    parser.add_argument(
        "-f", "--file",
        help="مسیر فایل صوتی محلی (برای تشخیص)"
    )
    parser.add_argument(
        "-o", "--output",
        default="downloads",
        help="پوشه خروجی (پیش‌فرض: downloads)"
    )
    parser.add_argument(
        "--cookies",
        help="مسیر فایل کوکی (برای سایت‌های نیازمند احراز هویت)"
    )
    parser.add_argument(
        "-r", "--recognize",
        action="store_true",
        help="تشخیص موزیک با Shazam (نیاز به فایل یا لینک)"
    )
    parser.add_argument(
        "-p", "--play",
        action="store_true",
        help="پخش فایل صوتی پس از دانلود (سیستم‌عامل: Windows/Mac/Linux)"
    )
    parser.add_argument(
        "-v", "--video",
        action="store_true",
        help="دانلود ویدئو به جای صدا"
    )
    
    args = parser.parse_args()
    
    if not args.url and not args.file:
        parser.print_help()
        sys.exit(1)
    
    # آماده‌سازی
    ensure_dir(args.output)
    downloader = Downloader(output_dir=args.output, cookies_file=args.cookies)
    recognizer = Recognizer()
    
    file_path = None
    title = None
    
    # حالت ۱: دانلود از لینک
    if args.url:
        print(f"⬇️ در حال دانلود از: {args.url}")
        if args.video:
            file_path, title = await downloader.download_video(args.url)
        else:
            file_path, title = await downloader.download_audio(args.url)
        
        if not file_path:
            print(f"❌ {title}")
            sys.exit(1)
        
        print(f"✅ فایل ذخیره شد: {file_path}")
        
        # اگر حالت پخش فعال باشد
        if args.play:
            player = get_platform_audio_player()
            if player:
                import subprocess
                print(f"▶️ در حال پخش با {player}...")
                if player == 'start':
                    subprocess.Popen([player, file_path], shell=True)
                else:
                    subprocess.Popen([player, file_path])
            else:
                print("⚠️ پخش‌کننده پیدا نشد.")
    
    # حالت ۲: تشخیص از فایل محلی
    if args.file:
        file_path = args.file
        if not Path(file_path).exists():
            print(f"❌ فایل {file_path} وجود ندارد.")
            sys.exit(1)
    
    # تشخیص موزیک
    if args.recognize and file_path:
        print("🔍 در حال تشخیص موزیک با Shazam...")
        result = await recognizer.recognize_file(file_path)
        print(recognizer.format_result(result))
    
    # اگر فقط تشخیص بود و لینکی نبود، تمام شد
    if not args.url and args.file:
        return

if __name__ == "__main__":
    asyncio.run(main())