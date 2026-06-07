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
import aiohttp
import os
import subprocess
from .base import BaseExtractor

class TikWmExtractor(BaseExtractor):
    """
    Downloader implementation using the TikWM API for TikTok and Douyin media downloads.
    """
    @property
    def name(self) -> str:
        return "TikWM API"

    def can_handle(self, url: str, media_type: str) -> bool:
        """
        Determines if the URL is a TikTok or Douyin link.
        """
        return 'tiktok.com' in url or 'douyin.com' in url

    async def download(self, url: str, event_id: str, media_type: str, options: dict) -> dict:
        """
        Downloads the video or audio file using TikWM API streaming.
        """
        download_dir = "downloads"
        os.makedirs(download_dir, exist_ok=True)
        
        api_url = "https://www.tikwm.com/api/"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(api_url, data={'url': url}) as resp:
                    if resp.status == 200:
                        json_data = await resp.json()
                        if json_data.get('code') == 0:
                            data = json_data.get('data', {})
                            
                            if media_type == 'audio':
                                download_url = data.get('music')
                                ext = 'mp3'
                            else:
                                download_url = data.get('play')
                                ext = 'mp4'
                                
                            if not download_url:
                                return {'success': False, 'error': 'TikWM did not return a valid download link.', 'status_code': 404}

                            from src.utils.security import is_safe_url
                            if not await is_safe_url(download_url):
                                return {'success': False, 'error': 'Security Policy Violation: TikWM media URL points to an internal/private IP.', 'status_code': 403}

                            filename = f"{download_dir}/{event_id}_tikwm.{ext}"
                            
                            async with session.get(download_url) as file_resp:
                                if file_resp.status == 200:
                                    with open(filename, 'wb') as f:
                                        async for chunk in file_resp.content.iter_chunked(1024 * 1024):
                                            f.write(chunk)
                                            
                                    if ext == 'mp4':
                                        fixed_filename = f"{filename}_fixed.mp4"
                                        fix_cmd = ['ffmpeg', '-y', '-i', filename, '-c:v', 'libx264', '-preset', 'fast', '-c:a', 'copy', '-movflags', '+faststart', fixed_filename]
                                        fix_process = await asyncio.create_subprocess_exec(*fix_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                                        await fix_process.communicate()
                                        if fix_process.returncode == 0 and os.path.exists(fixed_filename):
                                            os.remove(filename)
                                            filename = fixed_filename

                                    title = data.get('title', 'TikTok Video')
                                    author = data.get('author', {}).get('nickname', '')
                                    desc = f"TikTok download by {author}" if author else "Downloaded via TikWM"
                                    
                                    return {
                                        'success': True,
                                        'url': url,
                                        'filepath': filename,
                                        'title': title,
                                        'description': desc,
                                        'duration': data.get('duration', 0)
                                    }
                            return {'success': False, 'error': f'Failed to fetch TikWM media. Status: {file_resp.status}', 'status_code': file_resp.status}
                        return {'success': False, 'error': f"TikWM API error: {json_data.get('msg', 'Unknown TikWM error')}", 'status_code': 400}
                    return {'success': False, 'error': f'TikWM API endpoint returned status {resp.status}', 'status_code': resp.status}
        except Exception as e:
            return {'success': False, 'error': f'TikWM API execution error: {str(e)}', 'status_code': 500}
