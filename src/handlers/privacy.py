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

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

router = Router()

PRIVACY_TEXT = """
 **Terms of Service & Privacy Policy**

**1. Data Collection & Usage**
This bot collects minimal necessary data to provide its services. We store your Telegram User ID, Language Preference, and User interactions (events) solely for the purpose of operational functionality, queuing, and debugging.
We do NOT collect or store your personal messages, except the direct URLs sent to the bot for processing.

**2. Third-Party Services**
When you request a download, the bot proxies your request through external networks (e.g., YouTube, Spotify, etc.) using `yt-dlp`. These third parties have their own privacy policies. We do not transmit any of your personal identifiable information to these services.

**3. Cookies & Authentication**
If you choose to use the "Cookies" feature to download age-restricted or private videos, your `cookies.txt` file is encrypted using AES-256 before being stored in our database. The decryption key is securely held by the bot administrator. You may clear your cookies at any time via the settings menu.

**4. Abuse & Rate Limiting**
By using this bot, you agree not to abuse the service (e.g., Denial of Service attacks). We implement automated queuing and rate-limiting to protect server resources. Misuse may result in a permanent ban.

**5. Disclaimer**
This service is provided "as is" for educational and personal use only. You are solely responsible for ensuring you have the legal right to download the media you request.
"""

@router.message(Command("privacy", "tos"))
async def show_privacy(message: Message):
    await message.answer(PRIVACY_TEXT, parse_mode="Markdown")
