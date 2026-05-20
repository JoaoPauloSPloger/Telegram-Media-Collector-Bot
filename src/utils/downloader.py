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
from typing import Callable, Any
import yt_dlp
import yt_dlp.utils
from yt_dlp.utils import DownloadError
from src.utils.security import is_safe_url

# Store active downloads with their state
active_downloads = {}

def get_progress_bar(percentage: float) -> str:
    """Generate ASCII progress bar █████▍    """
    length = 12.5 # Total blocks (each full block is 8 sub-blocks, so 100% = 100 sub-blocks. 100/8 = 12.5 full blocks)
    sub_blocks = ['░', '▏', '▎', '▍', '▌', '▋', '▊', '▉', '█']

    total_sub_blocks = int(percentage)

    full_blocks = total_sub_blocks // 8
    remainder = total_sub_blocks % 8

    bar = sub_blocks[-1] * full_blocks

    # avoid appending if it's already 100% exactly (12.5 full blocks is 100 sub_blocks, we will max out at 100)
    # Since we want exactly ████████████▌ at 100% (12 full blocks + 4/8 block -> 12 full + 1 half)
    if total_sub_blocks >= 100:
        bar = sub_blocks[-1] * 12 + sub_blocks[4]
    else:
        bar += sub_blocks[remainder]

    # calculate remaining empty blocks
    empty_len = 13 - len(bar) # pad out to 13 characters total
    if empty_len > 0:
        bar += sub_blocks[0] * empty_len

    return f"{bar} {percentage:.1f}%"

def progress_hook(d: dict, event_id: str):
    # Check if task was cancelled by the user
    from src.utils.queue_manager import queue_manager
    if queue_manager.is_cancelled(event_id):
        raise DownloadError("Download cancelled by user.")

    if d['status'] == 'downloading':
        try:
            total_bytes = d.get('total_bytes') or d.get('total_bytes_estimate', 0)
            downloaded_bytes = d.get('downloaded_bytes', 0)
            
            if total_bytes > 0:
                percentage = (downloaded_bytes / total_bytes) * 100
                speed = d.get('speed', 0)
                eta = d.get('eta', 0)
                
                active_downloads[event_id] = {
                    'status': 'downloading',
                    'percentage': percentage,
                    'eta': eta,
                    'speed': speed
                }
        except Exception:
            pass
    elif d['status'] == 'finished':
        active_downloads[event_id] = {'status': 'finished', 'percentage': 100.0}

class FfmpegProgressLogger:
    def __init__(self, event_id):
        self.event_id = event_id
        
    def debug(self, msg):
        if self.event_id not in active_downloads:
            active_downloads[self.event_id] = {'status': 'downloading'}
        # Pass ffmpeg/yt-dlp debug lines
        pass
        
    def warning(self, msg): pass
    def error(self, msg): pass


class YtDlpLogger:
    def debug(self, msg): pass
    def warning(self, msg): pass
    def error(self, msg): pass

async def download_video(url: str, cookies_path: str = None, event_id: str = None, download_range: tuple = None, media_type: str = 'video') -> dict:
    if not await is_safe_url(url):
        return {'success': False, 'error': 'Security Policy Violation: Internal/Private IPs are blocked.', 'status_code': 403}

    if not event_id:
        event_id = str(uuid.uuid4())
        
    import os
    download_dir = "downloads"
    os.makedirs(download_dir, exist_ok=True)
    
    from src.database.db import config
    
    # Check if Local API server is configured
    is_local_api = bool(config.get('local_api_server'))
    
    # Set maximum file size (2GB for local api server, 50MB for cloud api)
    if is_local_api:
        max_filesize = 2000000000 # ~1.95GB
    else:
        max_filesize = 50000000 # ~48MB

    bot_username = config.get('bot_username', 'DownloaderBot')
    
    ydl_opts = {
        'outtmpl': f'{download_dir}/{event_id}_%(title).100s %(id)s @{bot_username}.%(ext)s',
        'noplaylist': True,
        'logger': FfmpegProgressLogger(event_id) if download_range else YtDlpLogger(),
        'progress_hooks': [lambda d: progress_hook(d, event_id)],
        'quiet': True,
        'max_filesize': max_filesize,
        'ratelimit': 26214400  # Strict 25MB/s limit to prevent network choke
    }
    
    if media_type == 'audio':
        ydl_opts['format'] = 'bestaudio/best'
        ydl_opts['postprocessors'] = [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }]
    elif media_type == 'video_subtitles':
        # Prioritize H.264 (avc) for universal hardware compatibility (prevents freezing on iOS)
        ydl_opts['format'] = 'bestvideo[vcodec^=avc][ext=mp4]+bestaudio[ext=m4a]/bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best'
        ydl_opts['merge_output_format'] = 'mp4'
        ydl_opts['writesubtitles'] = True
        ydl_opts['subtitlesformat'] = 'srt'
    else:
        # Default Video
        ydl_opts['format'] = 'bestvideo[vcodec^=avc][ext=mp4]+bestaudio[ext=m4a]/bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best'
        ydl_opts['merge_output_format'] = 'mp4'

    if download_range:
        start_time, end_time = download_range
        # For yt-dlp download_ranges, inf is represented as inf. 
        # But wait, yt_dlp.utils.download_range_func is best used here.
        
        # if end_time is None, it means download to the end
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

                # If info is a playlist (e.g. from ytsearch), get the first entry
                # Wait, if we set noplaylist=True, yt-dlp might just return the playlist info or first entry
                # We will just take the first entry to prevent crashing.
                if 'entries' in info:
                    entries = list(info.get('entries', []))
                    if not entries:
                        return {'success': False, 'error': 'No videos found in search.', 'status_code': 404}
                    info = entries[0]

                # Handling merged formats (bestvideo+bestaudio -> mkv/mp4)
                # When yt-dlp merges, the final filename is stored in requested_downloads
                filepath = ydl.prepare_filename(info)
                if 'requested_downloads' in info and info['requested_downloads']:
                    filepath = info['requested_downloads'][0].get('filepath', filepath)
                
                # Check description type (it can be None)
                description = info.get('description')
                if not isinstance(description, str):
                    description = ''

                return {
                    'success': True,
                    'url': url,
                    'filepath': filepath,
                    'title': info.get('title', 'Unknown Title'),
                    'description': description[:500], # truncate desc
                    'duration': info.get('duration', 0)
                }
        except DownloadError as e:
            error_msg = str(e)
            
            # Strip ANSI escape codes
            import re
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
            
            # Strip ANSI escape codes
            import re
            ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
            error_msg = ansi_escape.sub('', error_msg)
            
            return {'success': False, 'error': error_msg, 'status_code': 500}

    # Run the blocking yt-dlp operation in an executor
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, run_download, ydl_opts)
    
    if not result.get('success') and (result.get('retry_without_ffmpeg') or result.get('retry_with_best_format')):
        # Retry with format='best' to avoid ffmpeg merging issues/crashes
        ydl_opts_fallback = ydl_opts.copy()
        ydl_opts_fallback['format'] = 'best'
        result = await loop.run_in_executor(None, run_download, ydl_opts_fallback)
        
    # FALLBACK LOGIC
    if not result.get('success') and not result.get('error', '').startswith('Security'):
        import subprocess
        import json

        # Determine if we should try spotdl
        if 'spotify.com' in url and media_type == 'audio':
            try:
                cmd = ['spotdl', url, '--output', f"{download_dir}/{event_id}_{{title}}.{{ext}}"]
                process = await asyncio.create_subprocess_exec(*cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                try:
                    stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=120)
                except asyncio.TimeoutError:
                    process.kill()
                    raise Exception("spotdl timed out")

                if process.returncode == 0:
                    import glob
                    matches = glob.glob(f"{download_dir}/{event_id}_*.*")
                    if matches:
                        return {
                            'success': True,
                            'url': url,
                            'filepath': matches[0],
                            'title': 'Spotify Track',
                            'description': 'Downloaded via spotDL',
                            'duration': 0
                        }
            except Exception as e:
                pass

        # Tier 2: Cobalt API Fallback
        # Handles Bsky, X/Twitter, Instagram, TikTok reliably without local cookies
        import aiohttp
        try:
            cobalt_api_url = "https://api.cobalt.tools/api/json"
            headers = {
                "Accept": "application/json",
                "Content-Type": "application/json"
            }
            payload = {
                "url": url,
                "isAudioOnly": media_type == 'audio'
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(cobalt_api_url, headers=headers, json=payload, timeout=30) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        status = data.get('status')
                        if status in ['stream', 'redirect'] and 'url' in data:
                            media_url = data['url']
                            ext = 'mp3' if media_type == 'audio' else 'mp4'

                            filename = f"{download_dir}/{event_id}_cobalt.{ext}"

                            async with session.get(media_url) as file_resp:
                                if file_resp.status == 200:
                                    with open(filename, 'wb') as f:
                                        async for chunk in file_resp.content.iter_chunked(1024 * 1024):
                                            f.write(chunk)

                                    return {
                                        'success': True,
                                        'url': url,
                                        'filepath': filename,
                                        'title': 'Downloaded via Cobalt API',
                                        'description': 'Media bypassing successful',
                                        'duration': 0
                                    }
        except Exception as e:
            pass

        # Tier 3: Local Extractors with Timeouts (gallery-dl, spotdl)
        try:
            import os
            # Create a specific temporary directory to prevent race conditions with concurrent users
            temp_dir = f"{download_dir}/temp_{event_id}"
            os.makedirs(temp_dir, exist_ok=True)

            cmd = ['gallery-dl', url, '--dest', temp_dir]
            process = await asyncio.create_subprocess_exec(*cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            # Use wait_for to prevent infinite queue locks if process hangs
            try:
                stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=120)
            except asyncio.TimeoutError:
                process.kill()
                raise Exception("gallery-dl timed out")

            if process.returncode == 0:
                import glob
                import shutil
                # get all files in our isolated temp_dir
                list_of_files = glob.glob(f'{temp_dir}/**/*', recursive=True)
                # filter out directories
                list_of_files = [f for f in list_of_files if os.path.isfile(f)]
                if list_of_files:
                    latest_file = list_of_files[0] # just grab the first file found in this isolated dir
                    # move the file to our desired location
                    new_filepath = f"{download_dir}/{event_id}_gallerydl{os.path.splitext(latest_file)[1]}"
                    shutil.move(latest_file, new_filepath)
                    shutil.rmtree(temp_dir) # cleanup
                    return {
                        'success': True,
                        'url': url,
                        'filepath': new_filepath,
                        'title': 'Social Media Download',
                        'description': 'Downloaded via gallery-dl',
                        'duration': 0
                    }
            # cleanup on failure
            import shutil
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)
        except Exception as e:
            pass

    return result
