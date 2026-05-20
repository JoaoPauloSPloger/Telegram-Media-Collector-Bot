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

import aiohttp
from bs4 import BeautifulSoup
import re

async def get_music_metadata(url: str) -> str:
    """
    Attempts to fetch metadata (title and artist) from Spotify, Deezer or other music platforms
    using OpenGraph tags to form a search query.
    Returns the search query (e.g. "Artist - Title") or None if it fails.
    """
    # Using a bot user-agent helps bypass JS-only renderings on Spotify
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"
    }

    try:
        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.get(url) as resp:
                if resp.status != 200:
                    return None
                    
                html_content = await resp.text()
                soup = BeautifulSoup(html_content, 'html.parser')
                
                # Check OpenGraph title
                og_title = soup.find('meta', property='og:title')
                og_desc = soup.find('meta', property='og:description')
                
                title_str = og_title['content'].strip() if og_title and og_title.get('content') else None
                desc_str = og_desc['content'].strip() if og_desc and og_desc.get('content') else None
                
                if title_str:
                    # Spotify format is often in og:title, but let's return title + description for better search
                    # Often desc is something like "Artist · Song · 2023"
                    if desc_str:
                        clean_desc = desc_str.split('·')[0].strip() if '·' in desc_str else desc_str
                        return f"{title_str} {clean_desc}"
                        
                    return title_str
                    
        return None
    except Exception:
        return None
