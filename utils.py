import os
import re
import subprocess
from pathlib import Path

def sanitize_filename(name: str) -> str:
    """پاک‌سازی نام فایل برای سیستم‌عامل"""
    return re.sub(r'[<>:"/\\|?*]', '_', name).strip()

def get_platform_audio_player() -> str:
    """تشخیص پخش‌کننده صوتی سیستم"""
    if os.name == 'nt':
        return 'start'
    elif os.uname().sysname == 'Darwin':
        return 'afplay'
    else:
        # Linux
        for player in ['mpv', 'vlc', 'aplay']:
            if subprocess.run(['which', player], capture_output=True).returncode == 0:
                return player
        return None

def ensure_dir(path: str):
    """ساخت پوشه در صورت نبود"""
    Path(path).mkdir(parents=True, exist_ok=True)