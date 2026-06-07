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

import os
import aiohttp
import aiofiles
from bs4 import BeautifulSoup
from .base import BaseExtractor
from src.utils.security import is_safe_url

class ScraperExtractor(BaseExtractor):
    """
    Downloader implementation that falls back to generic HTML OpenGraph scraping and file downloading.
    """
    @property
    def name(self) -> str:
        return "Generic Scraper"

    def can_handle(self, url: str, media_type: str) -> bool:
        """
        Determines if the URL uses standard HTTP/HTTPS schemes.
        """
        return url.startswith(('http://', 'https://'))

    async def download(self, url: str, event_id: str, media_type: str, options: dict) -> dict:
        """
        Scrapes HTML or downloads the media file directly based on headers and OpenGraph metadata.
        """
        from src.database.db import config
        is_local_api = bool(config.get('local_api_server'))
        max_filesize = 2000000000 if is_local_api else 50000000

        download_dir = "downloads"
        os.makedirs(download_dir, exist_ok=True)
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }

        try:
            async with aiohttp.ClientSession(headers=headers) as session:
                async with session.head(url, allow_redirects=True) as resp:
                    content_type = resp.headers.get('Content-Type', '')
                    content_length = int(resp.headers.get('Content-Length', 0))
                    
                if content_length > max_filesize:
                    return {'success': False, 'error': f'File is larger than limit.', 'status_code': 413}
                    
                download_url = url
                title = "Media File"
                
                if 'text/html' in content_type.lower():
                    async with session.get(url) as resp:
                        html_content = await resp.text()
                        soup = BeautifulSoup(html_content, 'html.parser')
                        
                        og_video = soup.find('meta', property='og:video') or soup.find('meta', property='og:video:url')
                        og_image = soup.find('meta', property='og:image')
                        og_title = soup.find('meta', property='og:title')
                        
                        if og_video and og_video.get('content'):
                            download_url = og_video['content']
                        elif og_image and og_image.get('content'):
                            download_url = og_image['content']
                        else:
                            return {'success': False, 'error': 'unsupported_url', 'status_code': 400}
                            
                        if og_title and og_title.get('content'):
                            title = og_title['content']
                
                if not await is_safe_url(download_url):
                    return {'success': False, 'error': 'Security Policy Violation: Media URL points to an internal/private IP.', 'status_code': 403}

                async with session.get(download_url) as resp:
                    if resp.status != 200:
                        return {'success': False, 'error': 'Failed to download media file.', 'status_code': resp.status}
                        
                    content_type = resp.headers.get('Content-Type', '')
                    mime_type = content_type.split(';')[0].strip().lower() if content_type else ''
                    
                    MIME_MAP = {
                        'video/mp4': 'mp4',
                        'video/webm': 'webm',
                        'video/x-matroska': 'mkv',
                        'video/quicktime': 'mov',
                        'image/jpeg': 'jpg',
                        'image/png': 'png',
                        'image/gif': 'gif',
                        'image/webp': 'webp',
                        'audio/mpeg': 'mp3',
                        'audio/ogg': 'ogg',
                        'audio/wav': 'wav',
                        'audio/webm': 'webm',
                        'audio/aac': 'aac'
                    }
                    
                    ext = 'mp4'
                    if mime_type in MIME_MAP:
                        ext = MIME_MAP[mime_type]
                    elif 'video' in mime_type:
                        ext = mime_type.split('/')[-1]
                    elif 'image' in mime_type:
                        ext = mime_type.split('/')[-1]
                    else:
                        path_part = download_url.split('?')[0].split('#')[0]
                        if '.' in path_part:
                            url_ext = path_part.split('.')[-1].lower()
                            if url_ext.isalnum() and len(url_ext) <= 4:
                                ext = url_ext
                        
                    filepath = f"{download_dir}/{event_id}_generic.{ext}"
                    
                    downloaded_size = 0
                    async with aiofiles.open(filepath, 'wb') as f:
                        async for chunk in resp.content.iter_chunked(1024 * 1024):
                            await f.write(chunk)
                            downloaded_size += len(chunk)
                            if downloaded_size > max_filesize:
                                break
                                
                    if downloaded_size > max_filesize:
                        os.remove(filepath)
                        return {'success': False, 'error': 'File is larger than limit.', 'status_code': 413}
                                
                    return {
                        'success': True,
                        'filepath': filepath,
                        'title': title,
                        'description': '',
                        'duration': 0
                    }
                    
        except Exception as e:
            return {'success': False, 'error': str(e), 'status_code': 500}
