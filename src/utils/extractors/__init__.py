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

"""
Extractors registry module organizing and sorting download components in order of matching priority.
"""

from .ytdlp import YtDlpExtractor
from .spotdl import SpotDlExtractor
from .cobalt import CobaltExtractor
from .gallerydl import GalleryDlExtractor
from .tikwm import TikWmExtractor
from .scraper import ScraperExtractor

extractors_registry = [
    SpotDlExtractor(),
    TikWmExtractor(),
    YtDlpExtractor(),
    CobaltExtractor(),
    GalleryDlExtractor(),
    ScraperExtractor()
]
