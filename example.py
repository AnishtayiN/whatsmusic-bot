#!/usr/bin/env python3
"""Example: use the bot's downloader and recognizer programmatically."""

import asyncio

from downloader import Downloader
from recognizer import Recognizer


async def example():
    # 1. Download audio from a URL
    downloader = Downloader(output_dir='music')
    result = await downloader.download(
        'https://www.youtube.com/watch?v=dQw4w9WgXcQ', extract_audio=True
    )
    if not result:
        print('Download failed.')
        return

    file_path = result[0]['filename']
    print(f'Downloaded: {file_path}')

    # 2. Recognize the downloaded file
    recognizer = Recognizer()
    recognition = await recognizer.recognize_file(file_path)
    print(recognizer.format_result(recognition))


if __name__ == '__main__':
    asyncio.run(example())
