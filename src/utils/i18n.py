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

import json
import os

def load_locales():
    """
    Loads JSON translation files from locales directory into a dictionaries map.
    """
    locales = {}
    locale_dir = 'src/locales'
    for file in os.listdir(locale_dir):
        if file.endswith('.json'):
            lang_code = file.split('.')[0]
            with open(os.path.join(locale_dir, file), 'r', encoding='utf-8') as f:
                locales[lang_code] = json.load(f)
    return locales

def get_text(locales, lang_code, key):
    """
    Retrieves translation for the specified key and language, falling back to 'en' on failure.
    """
    if lang_code not in locales:
        lang_code = 'en'
    text = locales.get(lang_code, {}).get(key)
    if not text:
        text = locales.get('en', {}).get(key, f'Missing translation: {key}')
    return text
