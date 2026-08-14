#!/usr/bin/env python3
"""
🎵 What's Music Bot
دانلود و تشخیص موزیک از تیک‌تاک، یوتوب، اینستاگرام و ساندکلود
با استفاده از yt-dlp و shazamio
"""

import argparse
import asyncio
import subprocess
import sys
from pathlib import Path

from downloader import Downloader
from recognizer import Recognizer
from utils import ensure_dir, get_platform_audio_player, extract_platform

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
  python main.py -u "https://www.youtube.com/playlist?list=..." --playlist
  python main.py -u "https://soundcloud.com/artist/track" -o ./music --info
  python main.py -u "https://www.tiktok.com/@user/video/123" --play
"""
    )
    
    parser.add_argument("-u", "--url", help="لینک ویدیو/صوت از تیک‌تاک، یوتوب، اینستا، ساندکلود")
    parser.add_argument("-f", "--file", help="فایل صوتی محلی برای تشخیص با Shazam")
    parser.add_argument("-o", "--output", default="downloads", help="پوشه ذخیره (پیش‌فرض: downloads)")
    parser.add_argument("--cookies", help="فایل کوکی (برای سایت‌های محدود)")
    parser.add_argument("--recognize", action="store_true", help="تشخیص موزیک با Shazam بعد از دانلود")
    parser.add_argument("--playlist", action="store_true", help="دانلود کل پلی‌لیست (یوتوب)")
    parser.add_argument("--info", action="store_true", help="نمایش اطلاعات بدون دانلود")
    parser.add_argument("--play", action="store_true", help="پخش خودکار بعد از دانلود")
    parser.add_argument("--format", default="mp3", choices=["mp3", "m4a", "wav", "flac"], help="فرمت خروجی (پیش‌فرض: mp3)")
    parser.add_argument("--quiet", action="store_true", help="حالت بی‌صدا")
    parser.add_argument("--no-recognize", action="store_true", help="غیرفعال کردن تشخیص خودکار")

    args = parser.parse_args()
    
    if not args.url and not args.file:
        parser.print_help()
        sys.exit(1)
    
    downloader = Downloader(
        output_dir=args.output,
        cookies_file=args.cookies,
        quiet=args.quiet
    )
    recognizer = Recognizer()
    
    # تشخیص از فایل محلی
    if args.file:
        if not Path(args.file).exists():
            print(f"❌ فایل {args.file} وجود ندارد.")
            sys.exit(1)
        
        if args.recognize:
            print("🔍 در حال تشخیص موزیک با Shazam...")
            result = await recognizer.recognize_file(args.file)
            print(recognizer.format_result(result))
        return
    
    # دانلود از URL
    url = args.url.strip()
    platform = extract_platform(url)
    print(f"📱 پلتفرم: {platform}")
    
    if args.info:
        print("📋 دریافت اطلاعات...")
        info = await downloader.get_info(url)
        if info:
            print(f"🎵 عنوان: {info.get('title', 'نامشخص')}")
            print(f"👤 آپلودر: {info.get('uploader', 'نامشخص')}")
            print(f"⏱ مدت: {info.get('duration', 0)} ثانیه")
            print(f"👁 بازدید: {info.get('view_count', 0):,}")
            print(f"❤️ لایک: {info.get('like_count', 0):,}")
            print(f"🖼 تصویر: {info.get('thumbnail', 'ندارد')}")
        else:
            print("❌ دریافت اطلاعات ناموفق.")
        return
    
    # دانلود
    print(f"⬇️ در حال دانلود از {platform}...")
    result = await downloader.download(
        url=url,
        extract_audio=True,
        playlist=args.playlist,
        format_filter=args.format
    )
    
    if not result:
        print("❌ دانلود ناموفق.")
        sys.exit(1)
    
    if isinstance(result, list):
        print(f"✅ دانلود شد: {len(result)} فایل")
        for r in result:
            print(f"   📁 {r['filename']}")
        if args.recognize and not args.no_recognize:
            for r in result:
                print(f"\n🔍 تشخیص برای {r['filename']}...")
                res = await recognizer.recognize_file(r['filename'])
                print(recognizer.format_result(res))
    else:
        # حالت تک‌فایل (سازگاری با نسخه‌های قدیمی)
        print(f"✅ دانلود شد: {result['filename']}")
        if args.play:
            player = get_platform_audio_player()
            if player:
                subprocess.run([player, result['filename']])
            else:
                print("⚠️ پلیر صوتی یافت نشد.")
        if args.recognize and not args.no_recognize:
            print("🔍 تشخیص موزیک با Shazam...")
            res = await recognizer.recognize_file(result['filename'])
            print(recognizer.format_result(res))

if __name__ == "__main__":
    asyncio.run(main())