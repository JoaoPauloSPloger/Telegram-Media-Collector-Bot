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
import os
from .base import BaseExtractor

class SpotDlExtractor(BaseExtractor):
    """
    Downloader implementation using the spotDL CLI utility.
    """
    @property
    def name(self) -> str:
        return "spotDL"

    def can_handle(self, url: str, media_type: str) -> bool:
        """
        Determines if the URL can be handled by spotDL (handles Spotify URLs for audio).
        """
        return 'spotify.com' in url and media_type == 'audio'

    async def download(self, url: str, event_id: str, media_type: str, options: dict) -> dict:
        """
        Downloads the Spotify track using spotDL CLI tool.
        """
        download_dir = "downloads"
        os.makedirs(download_dir, exist_ok=True)
        
        try:
            cmd = ['spotdl', url, '--output', f"{download_dir}/{event_id}_{{title}}.{{ext}}"]
            process = await asyncio.create_subprocess_exec(*cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            try:
                stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=120)
            except (asyncio.TimeoutError, asyncio.CancelledError) as e:
                try:
                    process.kill()
                except Exception:
                    pass
                if isinstance(e, asyncio.TimeoutError):
                    return {'success': False, 'error': 'spotDL download timed out.', 'status_code': 408}
                raise

            if process.returncode == 0:
                matches = glob.glob(f"{download_dir}/{event_id}_*.*")
                if matches:
                    return {
                        'success': True,
                        'url': url,
                        'filepath': matches[0],
                        'title': 'Spotify Track',
                        'description': 'Downloaded via spotDL',
                        'duration': 0
                    }
                return {'success': False, 'error': 'spotDL finished but output file was not found.', 'status_code': 404}
            
            err_log = stderr.decode() if stderr else 'Unknown spotDL error'
            return {'success': False, 'error': f'spotDL failed with return code {process.returncode}. Log: {err_log}', 'status_code': 500}
        except Exception as e:
            return {'success': False, 'error': f'spotDL execution error: {str(e)}', 'status_code': 500}
