import json
import os

def load_locales():
    locales = {}
    locale_dir = 'src/locales'
    for file in os.listdir(locale_dir):
        if file.endswith('.json'):
            lang_code = file.split('.')[0]
            with open(os.path.join(locale_dir, file), 'r', encoding='utf-8') as f:
                locales[lang_code] = json.load(f)
    return locales

# Define a fallback translation utility
def get_text(locales, lang_code, key):
    # fallback to 'en'
    if lang_code not in locales:
        lang_code = 'en'
    text = locales.get(lang_code, {}).get(key)
    if not text:
        text = locales.get('en', {}).get(key, f'Missing translation: {key}')
    return text
