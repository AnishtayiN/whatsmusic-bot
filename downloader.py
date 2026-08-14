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
                   playlist: bool = False, format_filter: str = None, is_search: bool = False,
                   use_cookies: bool = False) -> List[str]:
        cmd = ["yt-dlp", "--no-warnings", "--no-check-certificates",
               "--user-agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"]

        if not playlist:
            cmd.append("--no-playlist")

        # جستجوی YouTube اگر URL نباشد
        if is_search:
            url = f"ytsearch1:{url}"

        # فقط اگر کوکی خواسته شده و معتبر باشه استفاده کن
        if use_cookies and self.cookies_file and Path(self.cookies_file).exists():
            cmd.extend(["--cookies", self.cookies_file])

        if extract_audio:
            fmt = format_filter or "mp3"
            cmd.extend([
                "-f", "bestaudio",
                "-x", "--audio-format", fmt,
                "--audio-quality", "0"
            ])
        else:
            if format_filter:
                cmd.extend(["-f", f"bestvideo[ext={format_filter}]+bestaudio[ext={format_filter}]/best[ext={format_filter}]"])
            else:
                cmd.extend(["-f", "bestvideo+bestaudio/best"])

        cmd.extend([
            "-o", output_template,
            "--restrict-filenames",
            "--print", "after_move:filepath",
            "--print", "title",
            url
        ])
        return cmd

    async def _run_download(self, cmd: List[str]) -> tuple:
        """اجرای دستور yt-dlp و برگرداندن (stdout, stderr, returncode)"""
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()
        return stdout, stderr, proc.returncode

    def _parse_output(self, stdout_text: str) -> tuple:
        """پردازش خروجی yt-dlp"""
        lines = [l.strip() for l in stdout_text.splitlines() if l.strip()]

        files = []
        titles = []
        for line in lines:
            if line.endswith(('.mp3', '.m4a', '.wav', '.flac', '.mp4', '.webm', '.mkv')):
                files.append(line)
            elif not line.startswith('[') and not line.startswith('http'):
                titles.append(line)

        if len(files) > len(titles):
            titles = [f"فایل {i+1}" for i in range(len(files))]
        elif len(titles) > len(files):
            titles = titles[:len(files)]

        return files, titles

    async def download(self, url: str, extract_audio: bool = True,
                       playlist: bool = False, format_filter: str = None, is_search: bool = False) -> Optional[List[Dict[str, str]]]:
        """
        دانلود فایل با سیستم retry هوشمند
        """
        temp_dir = self.output_dir / "temp"
        temp_dir.mkdir(exist_ok=True)

        if extract_audio:
            ext = format_filter or "mp3"
            output_template = str(temp_dir / f"%(title)s.{ext}")
        else:
            output_template = str(temp_dir / "%(title)s.%(ext)s")

        # لیست استراتژی‌ها: (use_cookies, extra_args)
        strategies = [
            (False, []),                                    # بدون کوکی
            (False, ["--extractor-args", "youtube:player_client=web"]),  # web client
            (False, ["--extractor-args", "youtube:player_client=tv_embedded"]),  # tv client
        ]

        # اگه کوکی داریم، اول با کوکی تست کن
        if self.cookies_file and Path(self.cookies_file).exists():
            strategies.insert(0, (True, []))

        import time
        for attempt, (use_cookies, extra_args) in enumerate(strategies):
            # وقفه بین تلاش‌ها برای جلوگیری از rate limiting
            time.sleep(3)
            
            cmd = self._build_cmd(url, output_template, extract_audio, playlist, format_filter, is_search, use_cookies)
            # اضافه کردن args اضافی
            for i, arg in enumerate(extra_args):
                cmd.insert(-1, arg)  # قبل از URL اضافه کن

            if not self.quiet:
                print(f"🔄 تلاش {attempt+1}: {'با کوکی' if use_cookies else 'بدون کوکی'} {extra_args or ''}")

            stdout, stderr, returncode = await self._run_download(cmd)

            if returncode == 0:
                files, titles = self._parse_output(stdout.decode('utf-8', errors='ignore'))
                if files:  # اگه فایلی پیدا شد
                    return self._move_files(files, titles, temp_dir)

            # اگه خطا "format not available" یا "bot" بود، ادامه بده
            error_msg = stderr.decode('utf-8', errors='ignore')
            if not self.quiet:
                print(f"❌ تلاش {attempt+1} ناموفق: {error_msg[:100]}")

        # پاک کردن temp
        import shutil
        if temp_dir.exists():
            shutil.rmtree(temp_dir, ignore_errors=True)

        return None

    def _move_files(self, files: List[str], titles: List[str], temp_dir: Path) -> List[Dict[str, str]]:
        """انتقال فایل‌ها از temp به output"""
        result = []
        for f, t in zip(files, titles):
            src = Path(f)
            if src.exists():
                dest = self.output_dir / sanitize_filename(src.name)
                if src != dest:
                    src.rename(dest)
                result.append({"filename": str(dest), "title": t})
            else:
                for p in temp_dir.glob("*"):
                    if p.suffix in ['.mp3', '.m4a', '.wav', '.flac', '.mp4', '.webm', '.mkv']:
                        dest = self.output_dir / sanitize_filename(p.name)
                        p.rename(dest)
                        result.append({"filename": str(dest), "title": t or p.stem})
                        break

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
