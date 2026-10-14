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
import json
from bs4 import BeautifulSoup

# Ensure project root is in sys.path
BASE_DIR = os.path.abspath('DEV/refactored-parakeet')
os.chdir(BASE_DIR)
sys.path.insert(0, BASE_DIR)
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

from src.database.db import config, AsyncSessionLocal, User, Event
from src.utils.downloader import download_video
from src.utils.url_cleaner import clean_and_split_urls

BOT_TOKEN = config['bot_token']
API_BASE = f"https://api.telegram.org/bot{BOT_TOKEN}"

async def analyze_and_respond_offline_messages():
    print("=" * 60)
    print("[PIPELINE 1] INICIANDO: MENSAGENS E LINKS OFFLINE")
    print("=" * 60)

    async with aiohttp.ClientSession() as session:
        # 1. Fetch pending updates
        async with session.get(f"{API_BASE}/getUpdates?limit=100") as resp:
            if resp.status != 200:
                print(f"Erro ao obter updates: HTTP {resp.status}")
                return
            data = await resp.json()
            updates = data.get('result', [])

        if not updates:
            print("Nenhuma mensagem pendente encontrada.")
            return

        print(f"Encontradas {len(updates)} atualizações pendentes enquanto o serviço estava inativo.\n")
        max_update_id = 0

        for u in updates:
            update_id = u.get('update_id')
            if update_id > max_update_id:
                max_update_id = update_id

            msg = u.get('message') or u.get('channel_post')
            if not msg:
                continue

            chat_id = msg.get('chat', {}).get('id')
            msg_id = msg.get('message_id')
            user = msg.get('from', {})
            user_id = user.get('id')
            user_name = user.get('first_name') or user.get('username') or 'Usuário'
            text = msg.get('text', '')

            print(f"--- Processando Update {update_id} de {user_name} ({user_id}) no chat {chat_id} ---")
            print(f"Conteúdo: {text!r}")

            # Check if text contains URLs
            urls = clean_and_split_urls(text)
            
            if urls:
                for url in urls:
                    print(f"Analisando link: {url}")
                    
                    # Test if it's a media URL downloadable by our extractors
                    download_res = await download_video(url, cookies_path="DEV/refactored-parakeet/downloads/cookies.txt")
                    
                    if download_res.get('success'):
                        filepath = download_res.get('filepath')
                        title = download_res.get('title', 'Mídia')
                        print(f"✅ Mídia baixada com sucesso: {filepath} ({title})")
                        
                        caption = (
                            f"🎬 <b>{title}</b>\n\n"
                            f"<i>O serviço estava temporariamente offline, mas seu link foi processado agora com sucesso!</i>\n\n"
                            f"🤖 @{config.get('bot_username', 'TMCollector_Bot')}"
                        )
                        
                        ext = filepath.split('.')[-1].lower() if filepath else ''
                        endpoint = "sendVideo" if ext in ['mp4', 'mkv', 'mov', 'webm'] else ("sendPhoto" if ext in ['jpg', 'jpeg', 'png', 'webp'] else "sendDocument")
                        field = "video" if endpoint == "sendVideo" else ("photo" if endpoint == "sendPhoto" else "document")
                        
                        data_form = aiohttp.FormData()
                        data_form.add_field('chat_id', str(chat_id))
                        data_form.add_field('reply_to_message_id', str(msg_id))
                        data_form.add_field('caption', caption)
                        data_form.add_field('parse_mode', 'HTML')
                        data_form.add_field(field, open(filepath, 'rb'), filename=os.path.basename(filepath))
                        
                        async with session.post(f"{API_BASE}/{endpoint}", data=data_form) as send_resp:
                            if send_resp.status == 200:
                                print(f"✅ Mídia enviada para {chat_id}!")
                            else:
                                print(f"Erro ao enviar mídia: HTTP {send_resp.status} - {await send_resp.text()}")
                                
                        if os.path.exists(filepath):
                            os.remove(filepath)
                    else:
                        # Non-media URL (e.g. Google Sites / webpage): Analyze with OpenGraph
                        print(f"Link não é mídia direta. Analisando página web...")
                        page_title = "Página Web"
                        page_desc = ""
                        try:
                            async with session.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=aiohttp.ClientTimeout(total=8)) as page_resp:
                                if page_resp.status == 200:
                                    soup = BeautifulSoup(await page_resp.text(), 'html.parser')
                                    og_title = soup.find('meta', property='og:title') or soup.find('title')
                                    og_desc = soup.find('meta', property='og:description') or soup.find('meta', attrs={'name': 'description'})
                                    if og_title:
                                        page_title = og_title.get('content') or og_title.text.strip()
                                    if og_desc:
                                        page_desc = og_desc.get('content') or og_desc.text.strip()
                        except Exception as e:
                            print(f"Erro ao inspecionar página: {e}")

                        reply_text = (
                            f"🌐 <b>Análise de Link Recebido:</b>\n\n"
                            f"📌 <b>Título:</b> {page_title}\n"
                        )
                        if page_desc:
                            reply_text += f"📝 <b>Descrição:</b> <i>{page_desc[:250]}</i>\n"
                        reply_text += (
                            f"\nℹ️ <i>Este link é uma página web ou jogo interativo e não contém arquivos de vídeo ou áudio disponíveis para download direto.</i>"
                        )

                        payload = {
                            'chat_id': chat_id,
                            'reply_to_message_id': msg_id,
                            'text': reply_text,
                            'parse_mode': 'HTML'
                        }
                        async with session.post(f"{API_BASE}/sendMessage", json=payload) as reply_resp:
                            if reply_resp.status == 200:
                                print(f"✅ Resposta de análise enviada para {chat_id}!")
                            else:
                                print(f"Erro ao enviar resposta: {await reply_resp.text()}")

            elif text.startswith('/stats'):
                print("Comando /stats detectado. Respondendo estatísticas...")
                from sqlalchemy import text as sqltxt
                stats_text = "📊 <b>Status do Sistema — Telegram Media Collector Bot</b>\n\n"
                stats_text += "🟢 <b>Serviço:</b> Ativo e Operacional\n"
                try:
                    async with AsyncSessionLocal() as db_session:
                        res = await db_session.execute(sqltxt("SELECT count(*) FROM events;"))
                        total_events = res.scalar() or 0
                        res = await db_session.execute(sqltxt("SELECT count(*) FROM events WHERE status = 'completed';"))
                        completed_events = res.scalar() or 0
                        res = await db_session.execute(sqltxt("SELECT count(*) FROM users;"))
                        total_users = res.scalar() or 0
                        
                    stats_text += f"👥 <b>Total de Usuários:</b> {total_users}\n"
                    stats_text += f"📥 <b>Downloads Concluídos:</b> {completed_events}\n"
                    stats_text += f"⚡ <b>Total de Eventos:</b> {total_events}\n"
                    stats_text += f"🚀 <b>Docker Engine:</b> Ativo"
                except Exception as e:
                    stats_text += f"Estatísticas temporariamente indisponíveis: {e}"

                payload = {
                    'chat_id': chat_id,
                    'reply_to_message_id': msg_id,
                    'text': stats_text,
                    'parse_mode': 'HTML'
                }
                async with session.post(f"{API_BASE}/sendMessage", json=payload) as reply_resp:
                    if reply_resp.status == 200:
                        print("✅ Estatísticas enviadas com sucesso!")

        # 3. Mark updates as processed
        if max_update_id > 0:
            async with session.get(f"{API_BASE}/getUpdates?offset={max_update_id + 1}") as ack_resp:
                if ack_resp.status == 200:
                    print(f"\n✅ Todas as mensagens offline foram processadas e confirmadas (Offset: {max_update_id + 1}).")

if __name__ == "__main__":
    asyncio.run(analyze_and_respond_offline_messages())
