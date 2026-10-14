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
from .base import BaseExtractor
from src.utils.security import is_safe_url

class BlueskyExtractor(BaseExtractor):
    """
    Downloader implementation using the public Bluesky / ATProto API
    to download Bluesky posts with photos or videos.
    """
    @property
    def name(self) -> str:
        return "Bluesky API"

    def can_handle(self, url: str, media_type: str) -> bool:
        return 'bsky.app' in url and '/post/' in url

    async def download(self, url: str, event_id: str, media_type: str, options: dict) -> dict:
        m = re.search(r'profile/([^/]+)/post/([^/?]+)', url)
        if not m:
            return {'success': False, 'error': 'Invalid Bluesky post URL format.', 'status_code': 400}

        handle, rkey = m.group(1), m.group(2)
        download_dir = "downloads"
        os.makedirs(download_dir, exist_ok=True)

        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }

        try:
            async with aiohttp.ClientSession(headers=headers) as session:
                # 1. Resolve handle to DID if not already a DID
                if handle.startswith('did:'):
                    did = handle
                else:
                    did_url = f"https://public.api.bsky.app/xrpc/com.atproto.identity.resolveHandle?handle={handle}"
                    async with session.get(did_url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                        if resp.status != 200:
                            return {'success': False, 'error': f'Failed to resolve Bluesky handle {handle}.', 'status_code': resp.status}
                        did_data = await resp.json()
                        did = did_data.get('did')
                        if not did:
                            return {'success': False, 'error': 'Did not find DID for Bluesky handle.', 'status_code': 404}

                # 2. Get post thread
                at_uri = f"at://{did}/app.bsky.feed.post/{rkey}"
                thread_url = f"https://public.api.bsky.app/xrpc/app.bsky.feed.getPostThread?uri={at_uri}&depth=0"
                async with session.get(thread_url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status != 200:
                        return {'success': False, 'error': f'Failed to retrieve Bluesky post. Status {resp.status}', 'status_code': resp.status}
                    thread_data = await resp.json()

                post = thread_data.get('thread', {}).get('post', {})
                if not post:
                    return {'success': False, 'error': 'Bluesky post not found.', 'status_code': 404}

                record = post.get('record', {})
                post_text = record.get('text', '')
                embed = post.get('embed', {})

                # Check images
                images = embed.get('images', [])
                if not images and 'media' in embed:
                    images = embed.get('media', {}).get('images', [])

                if images:
                    img_obj = images[0]
                    img_url = img_obj.get('fullsize') or img_obj.get('thumb')
                    if not img_url:
                        return {'success': False, 'error': 'No image URL found in Bluesky post.', 'status_code': 404}

                    if not await is_safe_url(img_url):
                        return {'success': False, 'error': 'Security Policy Violation: Media points to internal IP.', 'status_code': 403}

                    filename = f"{download_dir}/{event_id}_bsky.jpg"
                    async with session.get(img_url) as file_resp:
                        if file_resp.status != 200:
                            return {'success': False, 'error': f'Failed downloading Bluesky image. Status {file_resp.status}', 'status_code': file_resp.status}
                        with open(filename, 'wb') as f:
                            async for chunk in file_resp.content.iter_chunked(1024 * 1024):
                                f.write(chunk)

                    return {
                        'success': True,
                        'url': url,
                        'filepath': filename,
                        'title': f"Post by @{handle}",
                        'description': post_text,
                        'duration': 0
                    }

                # If it's a video, Bluesky embed contains playlist (HLS)
                if 'playlist' in embed:
                    playlist_url = embed.get('playlist')
                    if playlist_url:
                        filename = f"{download_dir}/{event_id}_bsky.mp4"
                        fix_cmd = ['ffmpeg', '-y', '-i', playlist_url, '-c', 'copy', '-bsf:a', 'aac_adtstoasc', '-movflags', '+faststart', filename]
                        try:
                            proc = await asyncio.create_subprocess_exec(*fix_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                            await proc.communicate()
                            if proc.returncode == 0 and os.path.exists(filename):
                                return {
                                    'success': True,
                                    'url': url,
                                    'filepath': filename,
                                    'title': f"Video by @{handle}",
                                    'description': post_text,
                                    'duration': 0
                                }
                        except Exception:
                            pass

                return {'success': False, 'error': 'No compatible video or photo found in Bluesky post.', 'status_code': 404}

        except Exception as e:
            return {'success': False, 'error': f'Bluesky extractor error: {str(e)}', 'status_code': 500}
