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

import urllib.parse
import re
import aiohttp
import asyncio

def clean_and_split_urls(text: str) -> list[str]:
    """
    Finds and splits valid URLs from text, separating glued URLs
    (e.g. 'https://example.com/ahttps://example.com/b').
    """
    if not text:
        return []

    # Separate URLs glued together without space
    split_pattern = re.compile(r'(https?://[^\s]+?)(?=https?://|$)')
    matches = split_pattern.findall(text)
    
    cleaned = []
    for raw_url in matches:
        url = raw_url.rstrip(',;)>]')
        # Strip radio mix playlist parameters from watch URLs
        if 'youtube.com/watch' in url or 'youtu.be/' in url:
            parsed = urllib.parse.urlparse(url)
            query = urllib.parse.parse_qs(parsed.query)
            if 'list' in query and any(v.startswith('RD') for v in query['list']):
                query.pop('list', None)
                query.pop('start_radio', None)
                new_query = urllib.parse.urlencode(query, doseq=True)
                url = urllib.parse.urlunparse(parsed._replace(query=new_query))
        cleaned.append(url)
        
    return cleaned

async def resolve_redirect_url(url: str) -> str:
    """
    Resolves shortlinks and share links (Reddit /s/, Facebook /share/, etc.)
    to their canonical destination URL.
    """
    redirect_domains = ['reddit.com/r/', 'redd.it', 'facebook.com/share/', 'fb.watch', 'vm.tiktok.com', 'vt.tiktok.com']
    if not any(d in url for d in redirect_domains):
        return url

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
    }

    try:
        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.head(url, allow_redirects=True, timeout=aiohttp.ClientTimeout(total=8)) as resp:
                if resp.status == 200:
                    return str(resp.url)
    except Exception:
        pass

    try:
        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.get(url, allow_redirects=True, timeout=aiohttp.ClientTimeout(total=8)) as resp:
                return str(resp.url)
    except Exception:
        pass

    return url
