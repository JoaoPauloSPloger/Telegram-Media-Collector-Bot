import asyncio
from src.utils.downloader import download_video

async def test():
    res = await download_video("https://youtube.com/shorts/A-_g8Z-a3Wc?si=NuVvHzS6fQQ1eg2r")
    print(res)

asyncio.run(test())
