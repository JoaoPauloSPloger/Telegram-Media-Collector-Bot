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

active_downloads = {}

def get_progress_bar(percentage: float) -> str:
    """
    Generates an ASCII progress bar string representation for download statistics.
    """
    length = 12.5
    sub_blocks = ['░', '▏', '▎', '▍', '▌', '▋', '▊', '▉', '█']

    total_sub_blocks = int(percentage)

    full_blocks = total_sub_blocks // 8
    remainder = total_sub_blocks % 8

    bar = sub_blocks[-1] * full_blocks

    if total_sub_blocks >= 100:
        bar = sub_blocks[-1] * 12 + sub_blocks[4]
    else:
        bar += sub_blocks[remainder]

    empty_len = 13 - len(bar)
    if empty_len > 0:
        bar += sub_blocks[0] * empty_len

    return f"{bar} {percentage:.1f}%"

def progress_hook(d: dict, event_id: str):
    """
    Tracks downloading metrics and reports progress percentage, speed, and ETA to the active downloads map.
    """
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
    """
    Logger that handles ffmpeg progress output.
    """
    def __init__(self, event_id):
        self.event_id = event_id
        
    def debug(self, msg):
        if self.event_id not in active_downloads:
            active_downloads[self.event_id] = {'status': 'downloading'}
        pass
        
    def warning(self, msg): pass
    def error(self, msg): pass


class YtDlpLogger:
    """
    Logger that handles yt-dlp logging output.
    """
    def debug(self, msg): pass
    def warning(self, msg): pass
    def error(self, msg): pass

async def download_video(url: str, cookies_path: str = None, event_id: str = None, download_range: tuple = None, media_type: str = 'video', is_admin: bool = False) -> dict:
    """
    Main download coordinator that routes the URL download request through the registered extractors.
    """
    if not await is_safe_url(url):
        return {'success': False, 'error': 'Security Policy Violation: Internal/Private IPs are blocked.', 'status_code': 403}

    if not event_id:
        event_id = str(uuid.uuid4())

    from src.utils.extractors import extractors_registry

    options = {
        'cookies_path': cookies_path,
        'download_range': download_range,
        'is_admin': is_admin
    }

    tier_logs = []
    
    for extractor in extractors_registry:
        if extractor.can_handle(url, media_type):
            try:
                result = await extractor.download(url, event_id, media_type, options)
                if result.get('success'):
                    result['tier_logs'] = tier_logs
                    return result
                else:
                    err_msg = result.get('error', 'Unknown error')
                    tier_logs.append(f"{extractor.name} Failed: {err_msg}")
            except Exception as e:
                tier_logs.append(f"{extractor.name} Exception: {str(e)}")

    return {
        'success': False,
        'error': 'All download fallback options exhausted.',
        'tier_logs': tier_logs,
        'status_code': 500
    }
