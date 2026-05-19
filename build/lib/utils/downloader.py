import asyncio
import os
import uuid
from typing import Callable, Any
import yt_dlp
from yt_dlp.utils import DownloadError

# Store active downloads with their state
active_downloads = {}

def get_progress_bar(percentage: float) -> str:
    """Generate ASCII progress bar [■■■#####]"""
    filled_blocks = int(percentage / 10)
    empty_blocks = 10 - filled_blocks
    bar = "■" * filled_blocks + "#" * empty_blocks
    return f"[{bar}] {percentage:.1f}%"

def progress_hook(d: dict, event_id: str):
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

class YtDlpLogger:
    def debug(self, msg): pass
    def warning(self, msg): pass
    def error(self, msg): pass

async def download_video(url: str, cookies_path: str = None, event_id: str = None) -> dict:
    if not event_id:
        event_id = str(uuid.uuid4())
        
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
    
    ydl_opts = {
        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
        'merge_output_format': 'mp4',
        'outtmpl': f'{download_dir}/{event_id}_%(title)s.%(ext)s',
        'noplaylist': True,
        'logger': YtDlpLogger(),
        'progress_hooks': [lambda d: progress_hook(d, event_id)],
        'quiet': True,
        'max_filesize': max_filesize
    }
    
    if cookies_path:
        ydl_opts['cookiefile'] = cookies_path

    def run_download(opts=None):
        if opts is None:
            opts = ydl_opts
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True)
                
                # Handling merged formats (bestvideo+bestaudio -> mkv/mp4)
                # When yt-dlp merges, the final filename is stored in requested_downloads
                filepath = ydl.prepare_filename(info)
                if 'requested_downloads' in info and len(info['requested_downloads']) > 0:
                    filepath = info['requested_downloads'][0].get('filepath', filepath)
                
                return {
                    'success': True,
                    'filepath': filepath,
                    'title': info.get('title', 'Unknown Title'),
                    'description': info.get('description', '')[:500], # truncate desc
                    'duration': info.get('duration', 0)
                }
        except DownloadError as e:
            error_msg = str(e)
            
            # Strip ANSI escape codes
            import re
            ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
            error_msg = ansi_escape.sub('', error_msg)
            
            if "Unsupported URL" in error_msg:
                return {'success': False, 'error': 'unsupported_url'}
            
            if "File is larger than max-filesize" in error_msg:
                limit_str = "2GB" if is_local_api else "50MB"
                return {'success': False, 'error': f'File is larger than {limit_str} limit.'}
            
            if "ffmpeg is not installed" in error_msg.lower() and opts.get('format') != 'best':
                return {'success': False, 'retry_without_ffmpeg': True}
                
            return {'success': False, 'error': error_msg}
        except Exception as e:
            error_msg = str(e)
            
            # Strip ANSI escape codes
            import re
            ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
            error_msg = ansi_escape.sub('', error_msg)
            
            return {'success': False, 'error': error_msg}

    # Run the blocking yt-dlp operation in an executor
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, run_download, ydl_opts)
    
    if not result.get('success') and result.get('retry_without_ffmpeg'):
        # Retry with format='best' to avoid ffmpeg
        ydl_opts_fallback = ydl_opts.copy()
        ydl_opts_fallback['format'] = 'best'
        result = await loop.run_in_executor(None, run_download, ydl_opts_fallback)
        
    return result
