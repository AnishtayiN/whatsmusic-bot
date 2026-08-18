"""converter.py - Extract audio from video files using ffmpeg."""
import asyncio
import logging
from pathlib import Path
from typing import Optional

from utils import cleanup_file, ensure_dir

logger = logging.getLogger(__name__)

# Map output format to ffmpeg audio codec
_CODEC_MAP = {
    'mp3': 'libmp3lame',
    'm4a': 'aac',
    'wav': 'pcm_s16le',
    'flac': 'flac',
    'ogg': 'libvorbis',
    'opus': 'libopus',
}


class AudioConverter:
    """Convert video files to audio using ffmpeg."""

    def __init__(self, output_dir: str = 'downloads'):
        self.output_dir = ensure_dir(Path(output_dir))

    async def extract_audio(self, video_path: str, output_format: str = 'mp3',
                            quality: int = 192, delete_source: bool = False) -> Optional[str]:
        """Extract the audio track from a video file.

        Args:
            video_path: Path to the source video file.
            output_format: Target audio format (mp3, m4a, wav, flac, ogg, opus).
            quality: Bitrate in kbps for lossy formats.
            delete_source: If True, delete the source video after conversion.
        """
        video_path = Path(video_path)
        if not video_path.exists():
            logger.error(f'Source video not found: {video_path}')
            return None

        output_format = output_format.lower()
        codec = _CODEC_MAP.get(output_format, 'libmp3lame')
        output_name = f'{video_path.stem}.{output_format}'
        output_path = self.output_dir / output_name

        if output_path.exists():
            output_path = self.output_dir / f'{video_path.stem}_converted.{output_format}'

        cmd = [
            'ffmpeg', '-i', str(video_path),
            '-vn', '-acodec', codec,
            '-ab', f'{quality}k',
            '-y', str(output_path),
        ]

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await proc.communicate()
        except FileNotFoundError:
            logger.error('ffmpeg binary not found. Install ffmpeg.')
            return None
        except Exception as e:
            logger.error(f'ffmpeg failed: {e}')
            return None

        if proc.returncode != 0 or not output_path.exists():
            err = stderr.decode('utf-8', errors='ignore')[:200]
            logger.error(f'Audio extraction failed: {err}')
            cleanup_file(output_path)
            return None

        if delete_source:
            cleanup_file(video_path)

        return str(output_path)

    async def convert_to_audio(self, url: str, quality: int = 192,
                               output_format: str = 'mp3') -> Optional[str]:
        """Download a video from a URL and extract its audio."""
        from downloader import Downloader

        downloader = Downloader(output_dir=str(self.output_dir))
        result = await downloader.download(url, extract_audio=False, playlist=False)

        if not result:
            return None

        video_path = result[0]['filename'] if isinstance(result, list) else result['filename']
        # Delete the intermediate video after extracting audio to save space
        return await self.extract_audio(video_path, output_format=output_format,
                                        quality=quality, delete_source=True)
