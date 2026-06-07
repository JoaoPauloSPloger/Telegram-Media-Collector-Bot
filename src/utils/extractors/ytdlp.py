# Telegram Media Collector Bot
# Copyright (C) 2026 Vulpes Tech
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

import asyncio
import math
import os
import uuid
import re
import yt_dlp
import yt_dlp.utils
from yt_dlp.utils import DownloadError
from .base import BaseExtractor
from src.utils.downloader import FfmpegProgressLogger, YtDlpLogger, progress_hook

class YtDlpExtractor(BaseExtractor):
    """
    Downloader implementation using the yt-dlp library.
    """
    @property
    def name(self) -> str:
        return "yt-dlp"

    def can_handle(self, url: str, media_type: str) -> bool:
        """
        Determines if the URL can be downloaded by yt-dlp (handles everything except Spotify links).
        """
        return 'spotify.com' not in url

    async def download(self, url: str, event_id: str, media_type: str, options: dict) -> dict:
        """
        Downloads media files from the URL using yt-dlp.
        """
        cookies_path = options.get('cookies_path')
        download_range = options.get('download_range')
        is_admin = options.get('is_admin', False)

        download_dir = "downloads"
        os.makedirs(download_dir, exist_ok=True)
        
        from src.database.db import config
        is_local_api = bool(config.get('local_api_server'))
        
        if is_local_api:
            max_filesize = 2000000000
        else:
            max_filesize = 5000000

        bot_username = config.get('bot_username', 'DownloaderBot')
        
        ydl_opts = {
            'outtmpl': f'{download_dir}/{event_id}_%(title).100s %(id)s @{bot_username}.%(ext)s',
            'noplaylist': True,
            'logger': FfmpegProgressLogger(event_id) if download_range else YtDlpLogger(),
            'progress_hooks': [lambda d: progress_hook(d, event_id)],
            'quiet': True,
            'max_filesize': max_filesize,
        }
        
        if not is_admin:
            bw_str = str(config.get('max_bandwidth', '25M')).upper()
            bw_limit = 26214400
            try:
                if bw_str.endswith('M'):
                    bw_limit = int(float(bw_str[:-1]) * 1024 * 1024)
                elif bw_str.endswith('K'):
                    bw_limit = int(float(bw_str[:-1]) * 1024)
                else:
                    bw_limit = int(bw_str)
            except ValueError:
                pass

            ydl_opts['ratelimit'] = bw_limit

        if media_type == 'audio':
            ydl_opts['format'] = 'bestaudio/best'
            ydl_opts['postprocessors'] = [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }]
        elif media_type == 'video_subtitles':
            ydl_opts['format'] = 'bestvideo[vcodec^=avc][ext=mp4]+bestaudio[ext=m4a]/bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best'
            ydl_opts['merge_output_format'] = 'mp4'
            ydl_opts['writesubtitles'] = True
            ydl_opts['subtitlesformat'] = 'srt'
            ydl_opts['postprocessor_args'] = ['-movflags', '+faststart']
        else:
            ydl_opts['format'] = 'bestvideo[vcodec^=avc][ext=mp4]+bestaudio[ext=m4a]/bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best'
            ydl_opts['merge_output_format'] = 'mp4'
            ydl_opts['postprocessor_args'] = ['-movflags', '+faststart']

        if download_range:
            start_time, end_time = download_range
            if end_time is None:
                end_time = math.inf
            ydl_opts['download_ranges'] = yt_dlp.utils.download_range_func(None, [(start_time, end_time)])
            ydl_opts['force_keyframes_at_cuts'] = True
        
        if cookies_path:
            ydl_opts['cookiefile'] = cookies_path

        def run_download(opts=None):
            if opts is None:
                opts = ydl_opts
            try:
                with yt_dlp.YoutubeDL(opts) as ydl:
                    info = ydl.extract_info(url, download=True)
                    if not info:
                        return {'success': False, 'error': 'No video information found.', 'status_code': 404}

                    if 'entries' in info:
                        entries = list(info.get('entries', []))
                        if not entries:
                            return {'success': False, 'error': 'No videos found in search.', 'status_code': 404}
                        info = entries[0]

                    filepath = ydl.prepare_filename(info)
                    if 'requested_downloads' in info and info['requested_downloads']:
                        filepath = info['requested_downloads'][0].get('filepath', filepath)
                    
                    description = info.get('description')
                    if not isinstance(description, str):
                        description = ''

                    chapters_text = ""
                    chapters = info.get('chapters')
                    if chapters:
                        chapters_text = "\n\n⏱ Chapters:\n"
                        for chapter in chapters:
                            c_start = int(chapter.get('start_time', 0))
                            title = chapter.get('title', '')
                            m, s = divmod(c_start, 60)
                            h, m = divmod(m, 60)
                            timestamp = f"{h:02d}:{m:02d}:{s:02d}" if h > 0 else f"{m:02d}:{s:02d}"
                            chapters_text += f"{timestamp} - {title}\n"

                    if chapters_text:
                        description = description[:200] + "\n..." if len(description) > 200 else description
                        description += chapters_text

                    return {
                        'success': True,
                        'url': url,
                        'filepath': filepath,
                        'title': info.get('title', 'Unknown Title'),
                        'description': description[:800],
                        'duration': info.get('duration', 0)
                    }
            except DownloadError as e:
                error_msg = str(e)
                ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
                error_msg = ansi_escape.sub('', error_msg)
                
                if "Unsupported URL" in error_msg:
                    return {'success': False, 'error': 'unsupported_url', 'status_code': 400}
                if "File is larger than max-filesize" in error_msg:
                    limit_str = "2GB" if is_local_api else "50MB"
                    return {'success': False, 'error': f'File is larger than {limit_str} limit.', 'status_code': 413}
                if "ffmpeg is not installed" in error_msg.lower() and opts.get('format') != 'best':
                    return {'success': False, 'retry_without_ffmpeg': True}
                if "ffmpeg exited with code" in error_msg.lower() and opts.get('format') != 'best':
                    return {'success': False, 'retry_with_best_format': True}
                if "Sign in to confirm" in error_msg or "Private video" in error_msg or "cookies" in error_msg.lower():
                    return {'success': False, 'error': error_msg, 'status_code': 403}
                if "Video unavailable" in error_msg or "not found" in error_msg.lower():
                    return {'success': False, 'error': error_msg, 'status_code': 404}
                return {'success': False, 'error': error_msg, 'status_code': 500}
            except Exception as e:
                error_msg = str(e)
                ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
                error_msg = ansi_escape.sub('', error_msg)
                return {'success': False, 'error': error_msg, 'status_code': 500}

        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, run_download, ydl_opts)
        
        if not result.get('success') and (result.get('retry_without_ffmpeg') or result.get('retry_with_best_format')):
            ydl_opts_fallback = ydl_opts.copy()
            ydl_opts_fallback['format'] = 'best'
            result = await loop.run_in_executor(None, run_download, ydl_opts_fallback)

        return result
