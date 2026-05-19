import asyncio
from src.utils.downloader import download_video

async def test():
    res = await download_video("https://www.youtube.com/watch?v=I90U69CdDoQ", download_range=(300, 310))
    print(res)

asyncio.run(test())
