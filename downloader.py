import asyncio
import subprocess
import sys
from pathlib import Path
from typing import Optional, Tuple

from utils import sanitize_filename

class Downloader:
    def __init__(self, output_dir: str = "downloads", cookies_file: Optional[str] = None):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.cookies_file = cookies_file

    def _get_ytdlp_cmd(self, url: str, output_path: str, extract_audio: bool = True) -> list:
        """ساخت دستور yt-dlp"""
        cmd = [
            "yt-dlp",
            "--no-playlist",
            "--quiet",
            "--no-warnings",
        ]
        if self.cookies_file and Path(self.cookies_file).exists():
            cmd.extend(["--cookies", self.cookies_file])
        if extract_audio:
            cmd.extend([
                "-x",
                "--audio-format", "mp3",
                "--audio-quality", "0",
                "-o", output_path,
            ])
        else:
            cmd.extend(["-o", output_path])
        cmd.append(url)
        return cmd

    async def download_audio(self, url: str) -> Tuple[Optional[str], Optional[str]]:
        """دانلود فایل صوتی و برگرداندن مسیر فایل و عنوان"""
        temp_dir = self.output_dir / "temp"
        temp_dir.mkdir(exist_ok=True)
        output_template = str(temp_dir / "%(title)s.%(ext)s")
        
        # مرحله ۱: دانلود با yt-dlp
        cmd = [
            "yt-dlp",
            "--no-playlist",
            "--quiet",
            "--no-warnings",
            "-o", output_template,
            url
        ]
        if self.cookies_file and Path(self.cookies_file).exists():
            cmd.extend(["--cookies", self.cookies_file])
        
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            return None, f"خطا در دانلود: {stderr.decode().strip()}"
        
        # پیدا کردن فایل دانلود شده
        files = list(temp_dir.glob("*"))
        if not files:
            return None, "فایلی دانلود نشد"
        # آخرین فایل تغییر یافته
        downloaded_file = max(files, key=lambda p: p.stat().st_mtime)
        
        # استخراج عنوان از نام فایل
        title = downloaded_file.stem
        
        # مرحله ۲: تبدیل به MP3 اگر نیاز باشد
        if downloaded_file.suffix.lower() not in ['.mp3', '.m4a', '.aac']:
            mp3_path = temp_dir / f"{title}.mp3"
            convert_cmd = [
                "ffmpeg",
                "-i", str(downloaded_file),
                "-acodec", "libmp3lame",
                "-ab", "192k",
                "-y",
                str(mp3_path)
            ]
            conv = await asyncio.create_subprocess_exec(
                *convert_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await conv.communicate()
            if conv.returncode == 0:
                downloaded_file.unlink()  # حذف فایل اصلی
                downloaded_file = mp3_path
            else:
                # اگر ffmpeg نبود، همان فایل اصلی را برمی‌گردانیم
                pass
        
        # انتقال به پوشه اصلی با نام تمیز
        final_name = sanitize_filename(title) + ".mp3"
        final_path = self.output_dir / final_name
        counter = 1
        while final_path.exists():
            final_name = f"{sanitize_filename(title)}_{counter}.mp3"
            final_path = self.output_dir / final_name
            counter += 1
        
        downloaded_file.rename(final_path)
        
        # حذف پوشه temp
        try:
            temp_dir.rmdir()
        except:
            pass
        
        return str(final_path), title

    async def download_video(self, url: str) -> Tuple[Optional[str], Optional[str]]:
        """دانلود ویدئو (بدون استخراج صدا)"""
        temp_dir = self.output_dir / "temp_video"
        temp_dir.mkdir(exist_ok=True)
        output_template = str(temp_dir / "%(title)s.%(ext)s")
        
        cmd = [
            "yt-dlp",
            "--no-playlist",
            "--quiet",
            "--no-warnings",
            "-o", output_template,
            url
        ]
        if self.cookies_file and Path(self.cookies_file).exists():
            cmd.extend(["--cookies", self.cookies_file])
        
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            return None, f"خطا در دانلود ویدئو: {stderr.decode().strip()}"
        
        files = list(temp_dir.glob("*"))
        if not files:
            return None, "فایلی دانلود نشد"
        downloaded_file = max(files, key=lambda p: p.st_mtime)
        
        # انتقال به پوشه اصلی
        final_name = sanitize_filename(downloaded_file.stem) + downloaded_file.suffix
        final_path = self.output_dir / final_name
        counter = 1
        while final_path.exists():
            final_name = f"{sanitize_filename(downloaded_file.stem)}_{counter}{downloaded_file.suffix}"
            final_path = self.output_dir / final_name
            counter += 1
        downloaded_file.rename(final_path)
        
        try:
            temp_dir.rmdir()
        except:
            pass
        
        return str(final_path), downloaded_file.stem