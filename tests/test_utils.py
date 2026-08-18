"""Tests for utils helper functions (stdlib unittest, no extra deps)."""
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils import (
    sanitize_filename,
    format_duration,
    extract_platform,
    is_url,
    extract_urls,
    split_artist_title,
    cleanup_file,
    ensure_dir,
    AUDIO_EXTS,
    MEDIA_EXTS,
)


class TestSanitizeFilename(unittest.TestCase):
    def test_strips_invalid_chars(self):
        self.assertEqual(sanitize_filename('a<b>c:d'), 'a_b_c_d')

    def test_strips_dots_and_spaces(self):
        self.assertEqual(sanitize_filename('  ..name..  '), 'name')

    def test_truncates_long_name(self):
        name = 'a' * 300
        self.assertEqual(len(sanitize_filename(name)), 200)

    def test_empty_returns_default(self):
        self.assertEqual(sanitize_filename('///'), 'file')


class TestFormatDuration(unittest.TestCase):
    def test_seconds_only(self):
        self.assertEqual(format_duration(5), '00:05')

    def test_minutes(self):
        self.assertEqual(format_duration(125), '02:05')

    def test_hours(self):
        self.assertEqual(format_duration(3661), '01:01:01')

    def test_none_and_invalid(self):
        self.assertEqual(format_duration(None), '00:00')
        self.assertEqual(format_duration('abc'), '00:00')


class TestExtractPlatform(unittest.TestCase):
    def test_youtube(self):
        self.assertEqual(extract_platform('https://www.youtube.com/watch?v=abc'), 'YouTube')
        self.assertEqual(extract_platform('https://youtu.be/abc'), 'YouTube')

    def test_tiktok(self):
        self.assertEqual(extract_platform('https://www.tiktok.com/@u/video/1'), 'TikTok')

    def test_instagram(self):
        self.assertEqual(extract_platform('https://instagram.com/reel/x'), 'Instagram')

    def test_unknown(self):
        self.assertEqual(extract_platform('not a url'), 'Unknown')
        self.assertEqual(extract_platform(''), 'Unknown')

    def test_generic_web(self):
        self.assertEqual(extract_platform('https://example.com/video'), 'Web')


class TestUrlDetection(unittest.TestCase):
    def test_is_url_true(self):
        self.assertTrue(is_url('https://example.com'))
        self.assertTrue(is_url('http://example.com/path?q=1'))

    def test_is_url_false(self):
        self.assertFalse(is_url('not a url'))
        self.assertFalse(is_url(''))
        self.assertFalse(is_url('example.com'))

    def test_extract_urls(self):
        text = 'see https://a.com and http://b.com/x'
        urls = extract_urls(text)
        self.assertEqual(len(urls), 2)
        self.assertIn('https://a.com', urls)


class TestSplitArtistTitle(unittest.TestCase):
    def test_dash_separator(self):
        self.assertEqual(split_artist_title('Eminem - Lose Yourself'),
                         ('Eminem', 'Lose Yourself'))

    def test_em_dash(self):
        self.assertEqual(split_artist_title('Artist — Song'), ('Artist', 'Song'))

    def test_no_separator(self):
        artist, title = split_artist_title('Eminem')
        self.assertEqual(artist, 'Eminem')
        self.assertEqual(title, '')

    def test_empty(self):
        self.assertEqual(split_artist_title(''), ('', ''))


class TestExts(unittest.TestCase):
    def test_audio_exts_present(self):
        self.assertIn('.mp3', AUDIO_EXTS)
        self.assertIn('.m4a', AUDIO_EXTS)

    def test_media_exts_includes_audio(self):
        for ext in AUDIO_EXTS:
            self.assertIn(ext, MEDIA_EXTS)
        self.assertIn('.mp4', MEDIA_EXTS)


class TestCleanupFile(unittest.TestCase):
    def test_removes_existing(self):
        d = ensure_dir(Path('/tmp/whatsmusic_test'))
        f = d / 'temp_file.txt'
        f.write_text('x')
        self.assertTrue(f.exists())
        cleanup_file(f)
        self.assertFalse(f.exists())

    def test_nonexistent_no_error(self):
        cleanup_file(Path('/tmp/does_not_exist_xyz'))


if __name__ == '__main__':
    unittest.main()
