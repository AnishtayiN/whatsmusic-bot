# converter.py - تبدیل ویدیو به صدا با ffmpeg
import asyncio
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

        if output_path.exists():
            output_path = self.output_dir / f"{video_path.stem}_converted.{output_format}"

        codec = "libmp3lame" if output_format == "mp3" else "aac" if output_format == "m4a" else "pcm_s16le" if output_format == "wav" else "flac"
        cmd = [
            "ffmpeg",
            "-i", str(video_path),
            "-vn",
            "-acodec", codec,
            "-ab", f"{quality}k",
            "-y",
            str(output_path)
        ]

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await proc.communicate()
            if proc.returncode == 0:
                return str(output_path)
            return None
        except Exception:
            return None

    async def convert_to_audio(self, url: str, quality: int = 192, output_format: str = "mp3") -> Optional[str]:
        """
        دانلود ویدیو از لینک و استخراج صدا
        """
        from downloader import Downloader

        downloader = Downloader(output_dir=str(self.output_dir))
        result = await downloader.download(url, extract_audio=False, playlist=False)

        if not result:
            return None

        video_path = result[0]['filename'] if isinstance(result, list) else result['filename']
        return await self.extract_audio(video_path, output_format=output_format, quality=quality)
