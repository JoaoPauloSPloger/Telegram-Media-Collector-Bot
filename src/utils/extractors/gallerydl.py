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
import subprocess
import glob
import shutil
import os
from .base import BaseExtractor

class GalleryDlExtractor(BaseExtractor):
    """
    Downloader implementation using the gallery-dl CLI utility.
    """
    @property
    def name(self) -> str:
        return "gallery-dl"

    def can_handle(self, url: str, media_type: str) -> bool:
        """
        Determines if the URL is from a social or artwork sharing platform supported by gallery-dl.
        """
        image_domains = [
            'instagram.com', 'pinterest.com', 'flickr.com', 
            'twitter.com', 'x.com', 'reddit.com', 'imgur.com', 
            'deviantart.com', 'artstation.com', 'tumblr.com'
        ]
        return any(domain in url for domain in image_domains)

    async def download(self, url: str, event_id: str, media_type: str, options: dict) -> dict:
        """
        Downloads the media file from the URL using gallery-dl CLI.
        """
        download_dir = "downloads"
        os.makedirs(download_dir, exist_ok=True)
        
        temp_dir = f"{download_dir}/temp_{event_id}"
        os.makedirs(temp_dir, exist_ok=True)
        
        try:
            cmd = ['gallery-dl', url, '--dest', temp_dir]
            process = await asyncio.create_subprocess_exec(*cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            try:
                stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=120)
            except asyncio.TimeoutError:
                process.kill()
                shutil.rmtree(temp_dir, ignore_errors=True)
                return {'success': False, 'error': 'gallery-dl download timed out.', 'status_code': 408}

            if process.returncode == 0:
                list_of_files = glob.glob(f'{temp_dir}/**/*', recursive=True)
                list_of_files = [f for f in list_of_files if os.path.isfile(f)]
                
                if list_of_files:
                    latest_file = list_of_files[0]
                    ext = os.path.splitext(latest_file)[1]
                    new_filepath = f"{download_dir}/{event_id}_gallerydl{ext}"
                    shutil.move(latest_file, new_filepath)
                    shutil.rmtree(temp_dir, ignore_errors=True)

                    if new_filepath.endswith('.mp4'):
                        fixed_filename = f"{new_filepath}_fixed.mp4"
                        fix_cmd = ['ffmpeg', '-y', '-i', new_filepath, '-c:v', 'libx264', '-preset', 'fast', '-c:a', 'copy', '-movflags', '+faststart', fixed_filename]
                        fix_process = await asyncio.create_subprocess_exec(*fix_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                        await fix_process.communicate()
                        if fix_process.returncode == 0 and os.path.exists(fixed_filename):
                            os.remove(new_filepath)
                            new_filepath = fixed_filename

                    return {
                        'success': True,
                        'url': url,
                        'filepath': new_filepath,
                        'title': 'Social Media Download',
                        'description': 'Downloaded via gallery-dl',
                        'duration': 0
                    }
                
                shutil.rmtree(temp_dir, ignore_errors=True)
                return {'success': False, 'error': 'gallery-dl finished but no media files were downloaded.', 'status_code': 404}
            
            shutil.rmtree(temp_dir, ignore_errors=True)
            err_log = stderr.decode() if stderr else 'Unknown gallery-dl error'
            return {'success': False, 'error': f'gallery-dl failed with return code {process.returncode}. Log: {err_log}', 'status_code': 500}
        except Exception as e:
            shutil.rmtree(temp_dir, ignore_errors=True)
            return {'success': False, 'error': f'gallery-dl execution error: {str(e)}', 'status_code': 500}
        
