"""downloader.py - Download media with yt-dlp, with retries and smart fallbacks."""
import asyncio
import json
import logging
import os
import shutil
from pathlib import Path
from typing import Optional, List, Dict, Any

from utils import sanitize_filename, ensure_dir, MEDIA_EXTS, AUDIO_EXTS, cleanup_dir

logger = logging.getLogger(__name__)

USER_AGENT = (
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
    'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'
)

# YouTube client strategies to try in order (cookies flag, extra args)
_YT_STRATEGIES = [
    (False, ['--extractor-args', 'youtube:player_client=web']),
    (False, ['--extractor-args', 'youtube:player_client=tv_embedded']),
    (False, ['--extractor-args', 'youtube:player_client=android']),
    (False, []),
]


class Downloader:
    """Async wrapper around the yt-dlp CLI for downloads and metadata."""

    def __init__(self, output_dir: str = 'downloads', cookies_file: Optional[str] = None,
                 quiet: bool = False, retries: int = 3, delay: float = 2.0):
        self.output_dir = ensure_dir(Path(output_dir))
        self.cookies_file = cookies_file
        self.quiet = quiet
        self.retries = retries
        self.delay = delay

    def _yt_dlp_path(self) -> str:
        return os.environ.get('YTDLP_PATH', 'yt-dlp')

    def _has_cookies(self) -> bool:
        return bool(self.cookies_file and Path(self.cookies_file).exists())

    def _build_cmd(self, url: str, output_template: str, extract_audio: bool = True,
                   playlist: bool = False, format_filter: Optional[str] = None,
                   is_search: bool = False, use_cookies: bool = False,
                   extra_args: Optional[List[str]] = None) -> List[str]:
        cmd = [self._yt_dlp_path(), '--no-warnings', '--no-check-certificates',
               '--user-agent', USER_AGENT]

        if not playlist:
            cmd.append('--no-playlist')

        if is_search:
            url = f'ytsearch1:{url}'

        if use_cookies and self._has_cookies():
            cmd.extend(['--cookies', self.cookies_file])

        if extract_audio:
            fmt = format_filter or 'mp3'
            cmd.extend(['-f', 'bestaudio/best', '-x',
                        '--audio-format', fmt, '--audio-quality', '0',
                        '--embed-metadata'])
        else:
            if format_filter:
                cmd.extend(['-f', f'bestvideo[ext={format_filter}]+bestaudio[ext={format_filter}]/best[ext={format_filter}]'])
            else:
                cmd.extend(['-f', 'bestvideo+bestaudio/best'])

        if extra_args:
            cmd.extend(extra_args)

        cmd.extend(['-o', output_template, '--restrict-filenames',
                    '--print', 'after_move:filepath', '--print', 'title', url])
        return cmd

    async def _run_download(self, cmd: List[str]) -> tuple:
        """Run yt-dlp and return (stdout, stderr, returncode)."""
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
            return stdout, stderr, proc.returncode
        except FileNotFoundError:
            logger.error('yt-dlp binary not found. Install yt-dlp or set YTDLP_PATH.')
            return b'', b'yt-dlp not found', 1
        except Exception as e:
            logger.error(f'Failed to run yt-dlp: {e}')
            return b'', str(e).encode('utf-8'), 1

    def _parse_output(self, stdout_text: str) -> tuple:
        """Parse yt-dlp output into (file_paths, titles)."""
        lines = [l.strip() for l in stdout_text.splitlines() if l.strip()]

        files: List[str] = []
        titles: List[str] = []
        for line in lines:
            if line.lower().endswith(MEDIA_EXTS) and (Path(line).exists() or '/' in line or '\\' in line):
                files.append(line)
            elif not line.startswith('[') and not line.startswith('http'):
                titles.append(line)

        if len(files) > len(titles):
            titles = [f'فایل {i + 1}' for i in range(len(files))]
        elif len(titles) > len(files):
            titles = titles[:len(files)]

        return files, titles

    async def download(self, url: str, extract_audio: bool = True,
                       playlist: bool = False, format_filter: Optional[str] = None,
                       is_search: bool = False) -> Optional[List[Dict[str, str]]]:
        """Download a file using a smart retry strategy.

        Tries multiple YouTube client strategies (and cookies if available)
        to work around transient rate limits and bot detection.
        """
        temp_dir = self.output_dir / 'temp'
        ensure_dir(temp_dir)

        if extract_audio:
            ext = format_filter or 'mp3'
            output_template = str(temp_dir / f'%(title)s.{ext}')
        else:
            output_template = str(temp_dir / '%(title)s.%(ext)s')

        strategies = list(_YT_STRATEGIES)
        if self._has_cookies():
            strategies.insert(0, (True, []))

        last_error = ''
        for attempt, (use_cookies, extra_args) in enumerate(strategies):
            if attempt > 0 and self.delay:
                await asyncio.sleep(self.delay)

            cmd = self._build_cmd(url, output_template, extract_audio, playlist,
                                  format_filter, is_search, use_cookies, extra_args)

            if not self.quiet:
                tag = 'با کوکی' if use_cookies else 'بدون کوکی'
                logger.info(f'تلاش {attempt + 1}: {tag} {extra_args or ""}')

            stdout, stderr, returncode = await self._run_download(cmd)

            if returncode == 0:
                files, titles = self._parse_output(stdout.decode('utf-8', errors='ignore'))
                if files:
                    return self._move_files(files, titles, temp_dir)

            last_error = stderr.decode('utf-8', errors='ignore')
            if not self.quiet:
                logger.warning(f'تلاش {attempt + 1} ناموفق: {last_error[:120]}')

        cleanup_dir(temp_dir)
        if last_error:
            logger.error(f'All download strategies failed for {url}: {last_error[:200]}')
        return None

    def _move_files(self, files: List[str], titles: List[str], temp_dir: Path) -> List[Dict[str, str]]:
        """Move downloaded files from temp to the output directory."""
        result = []
        for f, t in zip(files, titles):
            src = Path(f)
            if src.exists():
                dest = self.output_dir / sanitize_filename(src.name)
                if src.resolve() != dest.resolve():
                    if dest.exists():
                        dest = self.output_dir / f'{src.stem}_{id(src)}{src.suffix}'
                    src.rename(dest)
                result.append({'filename': str(dest), 'title': t})
            else:
                # Fallback: scan temp dir for media produced by this run
                for p in temp_dir.glob('*'):
                    if p.suffix.lower() in MEDIA_EXTS:
                        dest = self.output_dir / sanitize_filename(p.name)
                        if dest.exists():
                            dest = self.output_dir / f'{p.stem}_{id(p)}{p.suffix}'
                        p.rename(dest)
                        result.append({'filename': str(dest), 'title': t or p.stem})
                        break

        cleanup_dir(temp_dir)
        return result if result else None

    async def get_info(self, url: str) -> Optional[Dict[str, Any]]:
        """Fetch media metadata without downloading."""
        cmd = [self._yt_dlp_path(), '--no-warnings', '--no-playlist',
               '--dump-json', '--skip-download', '--user-agent', USER_AGENT, url]
        if self._has_cookies():
            cmd.extend(['--cookies', self.cookies_file])

        stdout, _, returncode = await self._run_download(cmd)
        if returncode != 0:
            return None

        try:
            data = json.loads(stdout.decode('utf-8', errors='ignore'))
        except json.JSONDecodeError:
            return None

        return {
            'title': data.get('title'),
            'duration': data.get('duration'),
            'uploader': data.get('uploader'),
            'view_count': data.get('view_count') or 0,
            'like_count': data.get('like_count') or 0,
            'thumbnail': data.get('thumbnail'),
            'webpage_url': data.get('webpage_url'),
        }
