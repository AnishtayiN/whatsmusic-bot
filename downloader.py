import asyncio
import subprocess
import json
import re
from pathlib import Path
from typing import Optional, List, Tuple, Dict, Any

from utils import sanitize_filename, ensure_dir


class Downloader:
    def __init__(self, output_dir: str = "downloads", cookies_file: Optional[str] = None, quiet: bool = False):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.cookies_file = cookies_file
        self.quiet = quiet

    def _build_cmd(self, url: str, output_template: str, extract_audio: bool = True,
                   playlist: bool = False, format_filter: str = None, is_search: bool = False) -> List[str]:
        cmd = ["yt-dlp", "--no-warnings"]

        if not playlist:
            cmd.append("--no-playlist")

        # جستجوی YouTube اگر URL نباشد
        if is_search:
            url = f"ytsearch1:{url}"

        if self.cookies_file and Path(self.cookies_file).exists():
            cmd.extend(["--cookies", self.cookies_file])

        if extract_audio:
            fmt = format_filter or "mp3"
            cmd.extend([
                "-x", "--audio-format", fmt,
                "--audio-quality", "0",
                "--embed-thumbnail",
                "--embed-metadata"
            ])
        else:
            if format_filter:
                cmd.extend(["-f", f"bestvideo[ext={format_filter}]+bestaudio[ext={format_filter}]/best[ext={format_filter}]"])
            else:
                cmd.extend(["-f", "bestvideo+bestaudio/best"])

        cmd.extend([
            "-o", output_template,
            "--no-cache-dir",
            "--restrict-filenames",
            "--print", "after_move:filepath",
            "--print", "title",
            url
        ])
        return cmd

    async def download(self, url: str, extract_audio: bool = True,
                       playlist: bool = False, format_filter: str = None, is_search: bool = False) -> Optional[List[Dict[str, str]]]:
        """
        دانلود فایل (صوتی یا ویدیویی) و برگرداندن لیست دیکشنری‌های {filename, title}
        """
        temp_dir = self.output_dir / "temp"
        temp_dir.mkdir(exist_ok=True)

        # الگوی خروجی با پسوند دلخواه (برای صدا) یا بدون پسوند (برای ویدیو)
        if extract_audio:
            ext = format_filter or "mp3"
            output_template = str(temp_dir / f"%(title)s.{ext}")
        else:
            output_template = str(temp_dir / "%(title)s.%(ext)s")

        cmd = self._build_cmd(url, output_template, extract_audio, playlist, format_filter, is_search)

        if not self.quiet:
            print(f"🔧 اجرای: {' '.join(cmd)}")

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()

        if proc.returncode != 0:
            error_msg = stderr.decode('utf-8', errors='ignore')
            if not self.quiet:
                print(f"❌ خطا: {error_msg[:200]}")
            return None

        # پردازش خروجی
        output_text = stdout.decode('utf-8', errors='ignore')
        lines = [l.strip() for l in output_text.splitlines() if l.strip()]

        # استخراج مسیر فایل‌ها و عناوین
        files = []
        titles = []
        for line in lines:
            if line.endswith('.mp3') or line.endswith('.m4a') or line.endswith('.wav') or line.endswith('.flac') or \
               line.endswith('.mp4') or line.endswith('.webm') or line.endswith('.mkv'):
                files.append(line)
            elif not line.startswith('[') and not line.startswith('http'):
                titles.append(line)

        # اگر تعداد فایل‌ها با عناوین برابر نبود، عناوین را با شماره‌گذاری پر کن
        if len(files) > len(titles):
            titles = [f"فایل {i+1}" for i in range(len(files))]
        elif len(titles) > len(files):
            titles = titles[:len(files)]

        result = []
        for f, t in zip(files, titles):
            src = Path(f)
            if src.exists():
                dest = self.output_dir / sanitize_filename(src.name)
                if src != dest:
                    src.rename(dest)
                result.append({"filename": str(dest), "title": t})
            else:
                # fallback: جستجوی فایل در temp
                for p in temp_dir.glob("*"):
                    if p.suffix in ['.mp3', '.m4a', '.wav', '.flac', '.mp4', '.webm', '.mkv']:
                        dest = self.output_dir / sanitize_filename(p.name)
                        p.rename(dest)
                        result.append({"filename": str(dest), "title": t or p.stem})
                        break

        # پاک کردن temp
        import shutil
        if temp_dir.exists():
            shutil.rmtree(temp_dir, ignore_errors=True)

        return result if result else None

    async def get_info(self, url: str) -> Optional[Dict[str, Any]]:
        """گرفتن اطلاعات ویدیو/صوت بدون دانلود"""
        cmd = [
            "yt-dlp", "--no-warnings", "--no-playlist",
            "--dump-json", "--skip-download",
            url
        ]
        if self.cookies_file and Path(self.cookies_file).exists():
            cmd.extend(["--cookies", self.cookies_file])

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, _ = await proc.communicate()

        if proc.returncode != 0:
            return None

        try:
            data = json.loads(stdout.decode('utf-8', errors='ignore'))
            return {
                "title": data.get("title"),
                "duration": data.get("duration"),
                "uploader": data.get("uploader"),
                "view_count": data.get("view_count"),
                "like_count": data.get("like_count"),
                "thumbnail": data.get("thumbnail"),
                "webpage_url": data.get("webpage_url")
            }
        except:
            return None