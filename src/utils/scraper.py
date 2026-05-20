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
from bs4 import BeautifulSoup
from src.utils.security import is_safe_url

async def download_generic_media(url: str, event_id: str, max_filesize: int) -> dict:
    """Fallback downloader for non-ytdlp supported URLs using direct HTTP request or basic HTML scraping"""
    if not await is_safe_url(url):
        return {'success': False, 'error': 'Security Policy Violation: Internal/Private IPs are blocked.', 'status_code': 403}

    download_dir = "downloads"
    os.makedirs(download_dir, exist_ok=True)
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    try:
        async with aiohttp.ClientSession(headers=headers) as session:
            # First, check if the URL points directly to a file (HEAD request)
            async with session.head(url, allow_redirects=True) as resp:
                content_type = resp.headers.get('Content-Type', '')
                content_length = int(resp.headers.get('Content-Length', 0))
                
            if content_length > max_filesize:
                return {'success': False, 'error': f'File is larger than limit.', 'status_code': 413}
                
            download_url = url
            title = "Media File"
            
            # If it's an HTML page, scrape it to find the real media link
            if 'text/html' in content_type.lower():
                async with session.get(url) as resp:
                    html_content = await resp.text()
                    soup = BeautifulSoup(html_content, 'html.parser')
                    
                    # Try to find OpenGraph video or image
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
            
            # Now download the actual file
            async with session.get(download_url) as resp:
                if resp.status != 200:
                    return {'success': False, 'error': 'Failed to download media file.', 'status_code': resp.status}
                    
                # Determine extension
                content_type = resp.headers.get('Content-Type', '')
                ext = 'mp4' # Default
                if 'video' in content_type:
                    ext = content_type.split('/')[-1]
                elif 'image' in content_type:
                    ext = content_type.split('/')[-1]
                elif download_url.split('.')[-1].isalnum() and len(download_url.split('.')[-1]) <= 4:
                    ext = download_url.split('.')[-1]
                    
                filepath = f"{download_dir}/{event_id}_generic.{ext}"
                
                # Stream the download asynchronously
                downloaded_size = 0
                import aiofiles
                async with aiofiles.open(filepath, 'wb') as f:
                    async for chunk in resp.content.iter_chunked(1024 * 1024):
                        await f.write(chunk)
                        downloaded_size += len(chunk)
                        if downloaded_size > max_filesize:
                            # Close the file before removing it to avoid permission errors on some OS
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
