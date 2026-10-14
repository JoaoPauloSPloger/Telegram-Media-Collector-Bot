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
import os
import sys
import aiohttp
import sqlite3
import html

# Ensure project root is in sys.path
BASE_DIR = os.path.abspath('DEV/refactored-parakeet')
os.chdir(BASE_DIR)
sys.path.insert(0, BASE_DIR)
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

from src.database.db import config, AsyncSessionLocal, Event
from src.utils.downloader import download_video

BOT_TOKEN = config['bot_token']
API_BASE = f"https://api.telegram.org/bot{BOT_TOKEN}"

async def retry_failed_downloads():
    print("=" * 60)
    print("[PIPELINE 2] INICIANDO: RECUPERACAO DE DOWNLOADS FALHOS")
    print("=" * 60)

    db_path = "database/bot_database.db"
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute("""
        SELECT event_id, user_id, url, status, error_msg 
        FROM events 
        WHERE status = 'failed' AND url IS NOT NULL AND url != ''
    """)
    rows = cur.fetchall()
    conn.close()

    print(f"Total de eventos com falha encontrados no banco: {len(rows)}")

    # Group by (user_id, url) to avoid spamming the same video repeatedly
    unique_attempts = {}
    for event_id, user_id, url, status, error_msg in rows:
        key = (user_id, url)
        if key not in unique_attempts:
            unique_attempts[key] = []
        unique_attempts[key].append(event_id)

    print(f"Total de mídias únicas para reprocessar: {len(unique_attempts)}\n")

    success_count = 0
    fail_count = 0

    async with aiohttp.ClientSession() as session:
        for (user_id, url), event_ids in unique_attempts.items():
            print(f"\n[REPROCESSANDO] Usuário: {user_id} | Eventos associados: {len(event_ids)}")
            print(f"URL: {url}")

            # Ignore obvious non-media URLs to save bandwidth
            if any(nm in url for nm in ['writereview', 'oauth2', 'marketplace', 'manualpdf']):
                print("⏩ URL ignorada (não é mídia).")
                continue

            try:
                res = await download_video(url, cookies_path="DEV/refactored-parakeet/downloads/cookies.txt")
                if res.get('success'):
                    filepath = res.get('filepath')
                    title = res.get('title', 'Mídia Recuperada')
                    description = res.get('description', '') or ''
                    print(f"✅ Download recuperado com sucesso: {title} ({filepath})")

                    # Construct message caption
                    safe_title = html.escape(title)
                    safe_desc = html.escape(description[:200]) + "..." if len(description) > 200 else html.escape(description)
                    caption = f"🎬 <b>[Reenvio Automático]</b>\n<b>{safe_title}</b>\n\n"
                    if safe_desc:
                        caption += f"<blockquote>{safe_desc}</blockquote>\n\n"
                    caption += (
                        "<i>Seu download solicitado anteriormente havia falhado devido a restrições temporárias da plataforma, "
                        "mas foi reprocessado com sucesso com a nova atualização do sistema!</i>\n\n"
                        f"🤖 @{config.get('bot_username', 'TMCollector_Bot')}"
                    )

                    ext = filepath.split('.')[-1].lower() if filepath else ''
                    endpoint = "sendVideo" if ext in ['mp4', 'mkv', 'mov', 'webm'] else ("sendPhoto" if ext in ['jpg', 'jpeg', 'png', 'webp'] else "sendDocument")
                    field = "video" if endpoint == "sendVideo" else ("photo" if endpoint == "sendPhoto" else "document")

                    data_form = aiohttp.FormData()
                    data_form.add_field('chat_id', str(user_id))
                    data_form.add_field('caption', caption)
                    data_form.add_field('parse_mode', 'HTML')
                    data_form.add_field(field, open(filepath, 'rb'), filename=os.path.basename(filepath))

                    async with session.post(f"{API_BASE}/{endpoint}", data=data_form) as send_resp:
                        if send_resp.status == 200:
                            print(f"📨 Mídia entregue com sucesso ao usuário {user_id}!")
                            success_count += 1
                            
                            # Mark all corresponding event_ids as completed
                            async with AsyncSessionLocal() as db_session:
                                for eid in event_ids:
                                    ev = await db_session.get(Event, eid)
                                    if ev:
                                        ev.status = 'completed'
                                await db_session.commit()
                        else:
                            err_body = await send_resp.text()
                            print(f"Falha no envio para o Telegram: HTTP {send_resp.status} - {err_body[:100]}")
                            fail_count += 1

                    if os.path.exists(filepath):
                        os.remove(filepath)
                else:
                    print(f"❌ Não foi possível baixar: {res.get('error')}")
                    fail_count += 1

            except Exception as e:
                print(f"Exceção durante reprocessamento: {e}")
                fail_count += 1

    print("\n" + "=" * 60)
    print(f"🏁 PIPELINE 2 CONCLUÍDO:")
    print(f"✅ Mídias recuperadas e enviadas: {success_count}")
    print(f"❌ Mídias que continuam indisponíveis/privadas: {fail_count}")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(retry_failed_downloads())
