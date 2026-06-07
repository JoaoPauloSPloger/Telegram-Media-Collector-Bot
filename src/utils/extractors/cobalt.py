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

class CobaltExtractor(BaseExtractor):
    """
    Downloader implementation using the Cobalt HTTP API.
    """
    @property
    def name(self) -> str:
        return "Cobalt API"

    def can_handle(self, url: str, media_type: str) -> bool:
        """
        Determines if the URL is from a social media domain supported by Cobalt.
        """
        social_domains = [
            'twitter.com', 'x.com', 'instagram.com', 
            'tiktok.com', 'reddit.com', 'bsky.app', 
            'youtube.com', 'youtu.be', 'vimeo.com'
        ]
        return any(domain in url for domain in social_domains)

    async def download(self, url: str, event_id: str, media_type: str, options: dict) -> dict:
        """
        Downloads media using Cobalt API endpoint and handles streaming.
        """
        download_dir = "downloads"
        os.makedirs(download_dir, exist_ok=True)
        
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

                            from src.utils.security import is_safe_url
                            if not await is_safe_url(media_url):
                                return {'success': False, 'error': 'Security Policy Violation: Cobalt redirect points to an internal/private IP.', 'status_code': 403}

                            async with session.get(media_url) as file_resp:
                                if file_resp.status == 200:
                                    with open(filename, 'wb') as f:
                                        async for chunk in file_resp.content.iter_chunked(1024 * 1024):
                                            f.write(chunk)

                                    if ext == 'mp4':
                                        fixed_filename = f"{filename}_fixed.mp4"
                                        fix_cmd = ['ffmpeg', '-y', '-i', filename, '-c:v', 'libx264', '-preset', 'fast', '-c:a', 'copy', '-movflags', '+faststart', fixed_filename]
                                        fix_process = await asyncio.create_subprocess_exec(*fix_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                                        try:
                                            await fix_process.communicate()
                                        except asyncio.CancelledError:
                                            try:
                                                fix_process.kill()
                                            except Exception:
                                                pass
                                            raise
                                        if fix_process.returncode == 0 and os.path.exists(fixed_filename):
                                            os.remove(filename)
                                            filename = fixed_filename

                                    return {
                                        'success': True,
                                        'url': url,
                                        'filepath': filename,
                                        'title': 'Downloaded via Cobalt API',
                                        'description': 'Media bypassing successful',
                                        'duration': 0
                                    }
                            return {'success': False, 'error': f'Failed to fetch Cobalt media stream. Status: {file_resp.status}', 'status_code': file_resp.status}
                        return {'success': False, 'error': f'Cobalt returned unsupported status: {status}', 'status_code': 400}
                    return {'success': False, 'error': f'Cobalt API returned status {resp.status}', 'status_code': resp.status}
        except Exception as e:
            return {'success': False, 'error': f'Cobalt API execution error: {str(e)}', 'status_code': 500}
