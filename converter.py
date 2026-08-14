# converter.py - تبدیل ویدیو به صدا با ffmpeg
import asyncio
import subprocess
from pathlib import Path
from typing import Optional

class AudioConverter:
    def __init__(self, output_dir: str = "downloads"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    async def extract_audio(self, video_path: str, output_format: str = "mp3", quality: int = 192) -> Optional[str]:
        """
        استخراج صدا از فایل ویدیویی با ffmpeg
        """
        video_path = Path(video_path)
        if not video_path.exists():
            return None

        output_name = video_path.stem + f".{output_format}"
        output_path = self.output_dir / output_name

        # اگر فایل خروجی وجود دارد، آن را حذف نکنید، اما می‌توانید با نام جدید ذخیره کنید
        if output_path.exists():
            output_path = self.output_dir / f"{video_path.stem}_converted.{output_format}"

        cmd = [
            "ffmpeg",
            "-i", str(video_path),
            "-vn",  # بدون ویدیو
            "-acodec", "libmp3lame" if output_format == "mp3" else "aac",
            "-ab", f"{quality}k",
            "-y",  # بازنویسی
            str(output_path)
        ]

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await proc.communicate()
            if proc.returncode == 0:
                return str(output_path)
            else:
                return None
        except Exception:
            return None

    async def convert_to_audio(self, url: str, quality: int = 192) -> Optional[str]:
        """
        دانلود ویدیو و استخراج صدا با یک مرحله
        """
        # از yt-dlp برای دانلود و استخراج همزمان استفاده می‌کنیم
        # اما اینجا فقط تبدیل را انجام می‌دهیم
        pass