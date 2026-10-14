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
import re
import aiohttp
import asyncio
import subprocess
from .base import BaseExtractor
from src.utils.security import is_safe_url

class FxTwitterExtractor(BaseExtractor):
    """
    Downloader implementation using the public FixTweet / FxTwitter API
    to download Twitter / X videos and high-resolution photos reliably.
    """
    @property
    def name(self) -> str:
        return "FxTwitter API"

    def can_handle(self, url: str, media_type: str) -> bool:
        twitter_domains = [
            'twitter.com', 'x.com', 'fxtwitter.com', 'vxtwitter.com',
            'fixupx.com', 'fixvx.com', 'stupidpenisx.com', 'girlcockx.com'
        ]
        return any(d in url for d in twitter_domains) and ('status/' in url or 'statuses/' in url)

    async def download(self, url: str, event_id: str, media_type: str, options: dict) -> dict:
        m = re.search(r'status(?:es)?/(\d+)', url)
        if not m:
            return {'success': False, 'error': 'Could not extract tweet status ID.', 'status_code': 400}
        
        status_id = m.group(1)
        api_url = f"https://api.fxtwitter.com/status/{status_id}"
        download_dir = "downloads"
        os.makedirs(download_dir, exist_ok=True)

        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            async with aiohttp.ClientSession(headers=headers) as session:
                async with session.get(api_url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                    if resp.status != 200:
                        return {'success': False, 'error': f'FxTwitter API returned status {resp.status}', 'status_code': resp.status}
                    
                    data = await resp.json()
                    tweet = data.get('tweet', {})
                    if not tweet:
                        return {'success': False, 'error': 'Tweet data not found.', 'status_code': 404}

                    media = tweet.get('media', {})
                    videos = media.get('videos', [])
                    photos = media.get('photos', [])

                    author_name = tweet.get('author', {}).get('name', 'Twitter User')
                    author_screen = tweet.get('author', {}).get('screen_name', 'twitter')
                    text = tweet.get('text', '')

                    if videos:
                        video_obj = videos[0]
                        # Pick the best bitrate MP4 variant if available
                        best_url = video_obj.get('url')
                        variants = video_obj.get('variants', [])
                        mp4_variants = [v for v in variants if v.get('content_type') == 'video/mp4']
                        if mp4_variants:
                            mp4_variants.sort(key=lambda v: v.get('bitrate', 0), reverse=True)
                            best_url = mp4_variants[0].get('url', best_url)

                        if not best_url:
                            return {'success': False, 'error': 'No downloadable video URL found.', 'status_code': 404}

                        if not await is_safe_url(best_url):
                            return {'success': False, 'error': 'Security Policy Violation: Tweet media points to internal IP.', 'status_code': 403}

                        filename = f"{download_dir}/{event_id}_twitter.mp4"
                        async with session.get(best_url) as file_resp:
                            if file_resp.status != 200:
                                return {'success': False, 'error': f'Failed downloading video stream. Status {file_resp.status}', 'status_code': file_resp.status}
                            with open(filename, 'wb') as f:
                                async for chunk in file_resp.content.iter_chunked(1024 * 1024):
                                    f.write(chunk)

                        duration = int(video_obj.get('duration', 0))

                        # Remux with faststart if needed
                        fixed_filename = f"{filename}_fixed.mp4"
                        fix_cmd = ['ffmpeg', '-y', '-i', filename, '-c:v', 'copy', '-c:a', 'copy', '-movflags', '+faststart', fixed_filename]
                        try:
                            fix_proc = await asyncio.create_subprocess_exec(*fix_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                            await fix_proc.communicate()
                            if fix_proc.returncode == 0 and os.path.exists(fixed_filename):
                                os.remove(filename)
                                filename = fixed_filename
                        except Exception:
                            pass

                        return {
                            'success': True,
                            'url': url,
                            'filepath': filename,
                            'title': f"Post by {author_name} (@{author_screen})",
                            'description': text,
                            'duration': duration,
                            'width': video_obj.get('width', 0),
                            'height': video_obj.get('height', 0)
                        }

                    elif photos:
                        photo_obj = photos[0]
                        photo_url = photo_obj.get('url')
                        if not photo_url:
                            return {'success': False, 'error': 'No downloadable photo URL found.', 'status_code': 404}

                        if not await is_safe_url(photo_url):
                            return {'success': False, 'error': 'Security Policy Violation: Tweet photo points to internal IP.', 'status_code': 403}

                        filename = f"{download_dir}/{event_id}_twitter.jpg"
                        async with session.get(photo_url) as file_resp:
                            if file_resp.status != 200:
                                return {'success': False, 'error': f'Failed downloading photo stream. Status {file_resp.status}', 'status_code': file_resp.status}
                            with open(filename, 'wb') as f:
                                async for chunk in file_resp.content.iter_chunked(1024 * 1024):
                                    f.write(chunk)

                        return {
                            'success': True,
                            'url': url,
                            'filepath': filename,
                            'title': f"Photo by {author_name} (@{author_screen})",
                            'description': text,
                            'duration': 0
                        }

                    return {'success': False, 'error': 'No media (video or photo) found in this tweet.', 'status_code': 404}

        except Exception as e:
            return {'success': False, 'error': f'FxTwitter extractor error: {str(e)}', 'status_code': 500}
