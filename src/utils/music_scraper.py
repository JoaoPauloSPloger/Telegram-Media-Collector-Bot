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
