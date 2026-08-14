import re
import subprocess
import sys
from pathlib import Path
from typing import Optional

def sanitize_filename(name: str) -> str:
    """پاک‌سازی نام فایل برای سیستم‌عامل"""
    # حذف کاراکترهای غیرمجاز
    name = re.sub(r'[<>:"/\\|?*]', '_', name)
    # محدود کردن طول
    if len(name) > 200:
        name = name[:200]
    return name.strip()

def ensure_dir(path: Path) -> Path:
    """اطمینان از وجود دایرکتوری"""
    path.mkdir(parents=True, exist_ok=True)
    return path

def get_platform_audio_player() -> Optional[str]:
    """تشخیص پلیر صوتی سیستم"""
    if sys.platform == "win32":
        return "start"
    elif sys.platform == "darwin":
        return "afplay"
    else:
        # لینوکس
        for cmd in ["mpv", "vlc", "ffplay"]:
            if subprocess.run(["which", cmd], capture_output=True).returncode == 0:
                return cmd
    return None

def format_duration(seconds: int) -> str:
    """تبدیل ثانیه به HH:MM:SS"""
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    if h:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"

def extract_platform(url: str) -> str:
    """تشخیص پلتفرم از URL"""
    if "tiktok.com" in url:
        return "TikTok"
    elif "youtube.com" in url or "youtu.be" in url:
        return "YouTube"
    elif "instagram.com" in url:
        return "Instagram"
    elif "soundcloud.com" in url:
        return "SoundCloud"
    elif "spotify.com" in url:
        return "Spotify"
    else:
        return "Unknown"