"""Tests for downloader output parsing (stdlib unittest, no yt-dlp needed)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from downloader import Downloader


class TestParseOutput(unittest.TestCase):
    def setUp(self):
        # output_dir may not exist but _parse_output doesn't touch the filesystem
        self.dl = Downloader(output_dir='/tmp/whatsmusic_dl_test', quiet=True)

    def test_parses_files_and_titles(self):
        stdout = '/tmp/a.mp3\nSong One\n/tmp/b.mp3\nSong Two\n'
        files, titles = self.dl._parse_output(stdout)
        self.assertEqual(files, ['/tmp/a.mp3', '/tmp/b.mp3'])
        self.assertEqual(titles, ['Song One', 'Song Two'])

    def test_fills_missing_titles(self):
        stdout = '/tmp/a.mp3\n/tmp/b.mp3\n'
        files, titles = self.dl._parse_output(stdout)
        self.assertEqual(files, ['/tmp/a.mp3', '/tmp/b.mp3'])
        self.assertEqual(len(titles), 2)

    def test_ignores_progress_lines(self):
        stdout = '[download] 50%\n[ffmpeg] converting\n/tmp/a.mp3\nReal Title\n'
        files, titles = self.dl._parse_output(stdout)
        self.assertEqual(files, ['/tmp/a.mp3'])
        self.assertEqual(titles, ['Real Title'])

    def test_truncates_extra_titles(self):
        stdout = '/tmp/a.mp3\nTitle1\nTitle2\n'
        files, titles = self.dl._parse_output(stdout)
        self.assertEqual(files, ['/tmp/a.mp3'])
        self.assertEqual(titles, ['Title1'])

    def test_empty(self):
        files, titles = self.dl._parse_output('')
        self.assertEqual(files, [])
        self.assertEqual(titles, [])


class TestBuildCmd(unittest.TestCase):
    def setUp(self):
        self.dl = Downloader(output_dir='/tmp/whatsmusic_dl_test', quiet=True)

    def test_search_query_transformed(self):
        cmd = self.dl._build_cmd('eminem', '/tmp/%(title)s.mp3',
                                 extract_audio=True, is_search=True)
        self.assertIn('ytsearch1:eminem', cmd)

    def test_no_playlist_default(self):
        cmd = self.dl._build_cmd('https://youtu.be/abc', '/tmp/%(title)s.mp3',
                                 extract_audio=True)
        self.assertIn('--no-playlist', cmd)

    def test_user_agent_present(self):
        cmd = self.dl._build_cmd('https://youtu.be/abc', '/tmp/%(title)s.mp3',
                                 extract_audio=True)
        self.assertIn('--user-agent', cmd)


if __name__ == '__main__':
    unittest.main()
