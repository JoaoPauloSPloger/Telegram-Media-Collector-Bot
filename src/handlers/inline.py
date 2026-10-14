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

import hashlib
import uuid
import urllib.parse
from aiogram import Router
from aiogram.types import (
    InlineQuery,
    InlineQueryResultArticle,
    InputTextMessageContent,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    InlineQueryResultCachedVideo,
    InlineQueryResultCachedAudio,
    InlineQueryResultsButton,
)
from src.handlers.download import URL_REGEX
from src.utils.i18n import load_locales, get_text
from src.utils.url_cleaner import clean_and_split_urls
from src.database.db import config

router = Router()
locales = load_locales()

def detect_platform_badge(url: str) -> tuple[str, str]:
    """Detects platform and returns (icon_name, display_title)."""
    parsed = urllib.parse.urlparse(url)
    netloc = parsed.netloc.lower()
    
    if "instagram.com" in netloc:
        return "📸", "Instagram"
    elif "youtube.com" in netloc or "youtu.be" in netloc:
        return "🎬", "YouTube"
    elif "tiktok.com" in netloc:
        return "🎵", "TikTok"
    elif any(d in netloc for d in ["twitter.com", "x.com", "fxtwitter.com", "fixupx.com"]):
        return "🐦", "Twitter / X"
    elif "bsky.app" in netloc:
        return "🦋", "Bluesky"
    elif any(d in netloc for d in ["spotify.com", "open.spotify.com"]):
        return "🎧", "Spotify"
    elif any(d in netloc for d in ["facebook.com", "fb.watch"]):
        return "📘", "Facebook"
    elif "reddit.com" in netloc:
        return "🤖", "Reddit"
    elif "pinterest.com" in netloc or "pin.it" in netloc:
        return "📌", "Pinterest"
    elif "soundcloud.com" in netloc:
        return "☁️", "SoundCloud"
    return "🌐", "Web Media"

@router.inline_query()
async def inline_query_handler(inline_query: InlineQuery, db_user):
    """
    Enhanced Inline Mode Handler for TMCB.
    
    Supports:
    - Empty query: interactive guide, live status card, format tips.
    - URL query: platform auto-detection, cached video/audio delivery,
      and deep-link download buttons.
    - Keywords (status, stats, help, ping): shareable bot metrics card.
    """
    raw_query = inline_query.query.strip()
    bot_username = config.get('bot_username', 'TMCollector_Bot')
    lang = db_user.language_code if db_user else 'pt'

    # Switch PM button on top of inline query popup
    pm_button = InlineQueryResultsButton(
        text="🚀 Abrir TMCB no Chat Privado",
        start_parameter="inline_guide"
    )

    results = []

    # CASE 1: Empty Query
    if not raw_query:
        # Card 1: How to use
        results.append(
            InlineQueryResultArticle(
                id="guide_how_to",
                title="📥 Como Baixar Mídias Inline",
                description="Cole o link de um vídeo ou áudio aqui para baixar instantaneamente.",
                input_message_content=InputTextMessageContent(
                    message_text=(
                        f"🤖 <b>Telegram Media Collector Bot (@{bot_username})</b>\n\n"
                        f"Para baixar vídeos ou áudios em qualquer chat:\n"
                        f"1. Digite <code>@{bot_username}</code> seguido do link da mídia.\n"
                        f"2. Escolha entre baixar em <b>Vídeo (MP4)</b> ou <b>Áudio (MP3)</b>.\n"
                        f"3. O download será processado e entregue com máxima velocidade!\n\n"
                        f"✨ <i>Suporta Instagram, TikTok, YouTube, Twitter/X, Bluesky, Spotify e mais!</i>"
                    ),
                    parse_mode="HTML"
                ),
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                    InlineKeyboardButton(text="⚡ Testar no Chat Privado", url=f"https://t.me/{bot_username}?start=inline_guide", style="primary")
                ]])
            )
        )

        # Card 2: Shareable Live Status Card
        from src.handlers.stats import get_system_metrics, get_db_metrics
        sys_m = get_system_metrics()
        results.append(
            InlineQueryResultArticle(
                id="guide_status",
                title="📊 Status do Bot em Tempo Real",
                description=f"Status: 🟢 Operacional | Uptime: {sys_m['uptime']}",
                input_message_content=InputTextMessageContent(
                    message_text=(
                        f"📊 <b>Status Operacional — TMCB (@{bot_username})</b>\n\n"
                        f"🟢 <b>Status:</b> <code>100% Operacional</code>\n"
                        f"⏱️ <b>Uptime:</b> <code>{sys_m['uptime']}</code>\n"
                        f"⚡ <b>Velocidade & API:</b> <code>Alta Performance (Local API)</code>\n"
                        f"🛡️ <b>Proteção Anti-Spam:</b> <code>Ativa (Taxa Suave)</code>\n\n"
                        f"✨ <i>Envie links diretamente para @{bot_username} para downloads instantâneos!</i>"
                    ),
                    parse_mode="HTML"
                ),
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                    InlineKeyboardButton(text="📥 Abrir Bot", url=f"https://t.me/{bot_username}", style="primary")
                ]])
            )
        )

        # Card 3: Supported Platforms
        results.append(
            InlineQueryResultArticle(
                id="guide_platforms",
                title="🌐 Plataformas Suportadas",
                description="Instagram, TikTok, YouTube, Twitter/X, Bluesky, Spotify, Reddit, etc.",
                input_message_content=InputTextMessageContent(
                    message_text=(
                        f"🌐 <b>Plataformas Compatíveis com o TMCB</b>\n\n"
                        f"📸 <b>Instagram:</b> Reels, Vídeos, Carrosséis e Fotos\n"
                        f"🎵 <b>TikTok:</b> Vídeos sem marca d'água\n"
                        f"🎬 <b>YouTube:</b> Vídeos, Shorts e Áudio (MP3)\n"
                        f"🐦 <b>Twitter / X:</b> Vídeos e GIFs em alta definição\n"
                        f"🦋 <b>Bluesky:</b> Vídeos e imagens completas\n"
                        f"🎧 <b>Spotify & Apple Music:</b> Extração de faixas e metadados\n"
                        f"📘 <b>Facebook & Reddit:</b> Mídias públicas e postagens\n\n"
                        f"🤖 <b>Bot Oficial:</b> @{bot_username}"
                    ),
                    parse_mode="HTML"
                ),
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                    InlineKeyboardButton(text="🚀 Começar a Usar", url=f"https://t.me/{bot_username}?start=inline_guide", style="primary")
                ]])
            )
        )

        await inline_query.answer(results, button=pm_button, cache_time=1)
        return

    # CASE 2: Special Keywords (status, stats, help, ping)
    kw_query = raw_query.lower()
    if kw_query in ["status", "stats", "uptime"]:
        from src.handlers.stats import get_system_metrics, get_db_metrics
        sys_m = get_system_metrics()
        db_m = await get_db_metrics()

        results.append(
            InlineQueryResultArticle(
                id="kw_status",
                title="📊 Status em Tempo Real do TMCB",
                description=f"Uptime: {sys_m['uptime']} | Downloads: {db_m['completed_events']}",
                input_message_content=InputTextMessageContent(
                    message_text=(
                        f"📊 <b>Relatório de Status — TMCB (@{bot_username})</b>\n\n"
                        f"🟢 <b>Status:</b> <code>100% Operacional</code>\n"
                        f"📦 <b>Downloads Concluídos:</b> <code>{db_m['completed_events']}</code>\n"
                        f"🎯 <b>Taxa de Sucesso:</b> <code>{db_m['success_rate']:.1f}%</code>\n"
                        f"⏱️ <b>Uptime do Sistema:</b> <code>{sys_m['uptime']}</code>\n"
                        f"🛡️ <b>Anti-Spam Scheduler:</b> <code>🟢 Ativo</code>\n\n"
                        f"🤖 Use @{bot_username} para baixar qualquer vídeo ou áudio."
                    ),
                    parse_mode="HTML"
                ),
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                    InlineKeyboardButton(text="📥 Abrir Bot", url=f"https://t.me/{bot_username}", style="primary")
                ]])
            )
        )
        await inline_query.answer(results, button=pm_button, cache_time=1)
        return

    elif kw_query in ["help", "ajuda", "comandos"]:
        results.append(
            InlineQueryResultArticle(
                id="kw_help",
                title="ℹ️ Guia de Ajuda do TMCB",
                description="Como usar comandos e recursos de download.",
                input_message_content=InputTextMessageContent(
                    message_text=(
                        f"ℹ️ <b>Guia Rápido — TMCB (@{bot_username})</b>\n\n"
                        f"• <b>Download Direto:</b> Basta enviar o link no chat do bot.\n"
                        f"• <b>Áudio Apenas:</b> Use <code>/audio &lt;link&gt;</code> ou <code>/mp3 &lt;link&gt;</code>.\n"
                        f"• <b>Status do Sistema:</b> Envie <code>/status</code> ou <code>/stats</code>.\n"
                        f"• <b>Cookies Próprios:</b> Use <code>/usecookies</code> para posts privados.\n"
                        f"• <b>Modo Inline:</b> Digite <code>@{bot_username} &lt;link&gt;</code> em qualquer chat.\n"
                    ),
                    parse_mode="HTML"
                ),
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                    InlineKeyboardButton(text="🚀 Abrir Bot", url=f"https://t.me/{bot_username}", style="primary")
                ]])
            )
        )
        await inline_query.answer(results, button=pm_button, cache_time=1)
        return

    elif kw_query in ["ping", "latencia"]:
        results.append(
            InlineQueryResultArticle(
                id="kw_ping",
                title="⚡ Teste de Latência (Pong!)",
                description="Servidor ativo com alta velocidade.",
                input_message_content=InputTextMessageContent(
                    message_text=(
                        f"🏓 <b>Pong!</b>\n\n"
                        f"⚡ <b>Status:</b> Conexão com Telegram ativa.\n"
                        f"🚀 <b>Motor:</b> Telegram Local Bot API Server.\n"
                        f"🤖 <b>Bot:</b> @{bot_username}"
                    ),
                    parse_mode="HTML"
                ),
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                    InlineKeyboardButton(text="📥 Abrir Bot", url=f"https://t.me/{bot_username}", style="primary")
                ]])
            )
        )
        await inline_query.answer(results, button=pm_button, cache_time=1)
        return

    # CASE 3: URL Detection and Processing
    cleaned_urls = clean_and_split_urls(raw_query)
    urls = cleaned_urls if cleaned_urls else URL_REGEX.findall(raw_query)

    if not urls:
        # User typed search query or unknown text: provide helpful suggestion
        results.append(
            InlineQueryResultArticle(
                id="search_hint",
                title=f"🔍 Link não reconhecido: '{raw_query[:30]}...'",
                description="Cole um link válido (ex: https://instagram.com/reel/...) para baixar.",
                input_message_content=InputTextMessageContent(
                    message_text=(
                        f"⚠️ O texto informado não contém um link válido de mídia.\n\n"
                        f"Por favor, cole um link completo começando com <code>http://</code> ou <code>https://</code>.\n\n"
                        f"🤖 @{bot_username}"
                    ),
                    parse_mode="HTML"
                ),
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                    InlineKeyboardButton(text="📥 Abrir Bot no Privado", url=f"https://t.me/{bot_username}", style="primary")
                ]])
            )
        )
        await inline_query.answer(results, button=pm_button, cache_time=1)
        return

    url = urls[0]
    icon, platform_name = detect_platform_badge(url)
    safe_display_url = url.replace("https://", "").replace("http://", "")
    if len(safe_display_url) > 40:
        safe_display_url = safe_display_url[:37] + "..."

    from src.utils.cache import get_cached_file_id, set_cached_file_id

    video_file_id, video_title, video_desc = await get_cached_file_id(url, "video")
    audio_file_id, audio_title, audio_desc = await get_cached_file_id(url, "audio")

    short_id = uuid.uuid4().hex[:16]
    await set_cached_file_id(f"inline_{short_id}", "inline_url", url)

    # 1. Video Result
    if video_file_id:
        results.append(
            InlineQueryResultCachedVideo(
                id=hashlib.md5(f"video_{url}".encode()).hexdigest(),
                video_file_id=video_file_id,
                title=f"{icon} {video_title or 'Vídeo (' + platform_name + ')'}",
                description=video_desc or f"Vídeo pronto do {platform_name}",
                caption=f"🎬 <b>{video_title or 'Vídeo'}</b>\n\n🔗 <i>{platform_name}</i>\n🤖 @{bot_username}",
                parse_mode="HTML"
            )
        )
    else:
        results.append(
            InlineQueryResultArticle(
                id=hashlib.md5(f"article_vid_{url}".encode()).hexdigest(),
                title=f"{icon} Baixar Vídeo ({platform_name})",
                description=f"Baixar {safe_display_url} em MP4 alta qualidade",
                input_message_content=InputTextMessageContent(
                    message_text=(
                        f"{icon} <b>Mídia do {platform_name}</b>\n\n"
                        f"🔗 <b>Link:</b> <code>{url}</code>\n\n"
                        f"Clique no botão abaixo para iniciar o download do vídeo em alta resolução!\n\n"
                        f"🤖 <b>via @{bot_username}</b>"
                    ),
                    parse_mode="HTML"
                ),
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                    InlineKeyboardButton(
                        text=f"🎬 Baixar Vídeo ({platform_name})",
                        url=f"https://t.me/{bot_username}?start=dl_{short_id}",
                        style="primary"
                    )
                ]])
            )
        )

    # 2. Audio Result
    if audio_file_id:
        results.append(
            InlineQueryResultCachedAudio(
                id=hashlib.md5(f"audio_{url}".encode()).hexdigest(),
                audio_file_id=audio_file_id,
                caption=f"🎧 <b>{audio_title or 'Áudio'}</b>\n\n🔗 <i>{platform_name}</i>\n🤖 @{bot_username}",
                parse_mode="HTML"
            )
        )
    else:
        results.append(
            InlineQueryResultArticle(
                id=hashlib.md5(f"article_aud_{url}".encode()).hexdigest(),
                title=f"🎧 Extrair Áudio MP3 ({platform_name})",
                description=f"Extrair a faixa de áudio em MP3 de {safe_display_url}",
                input_message_content=InputTextMessageContent(
                    message_text=(
                        f"🎧 <b>Áudio do {platform_name}</b>\n\n"
                        f"🔗 <b>Link:</b> <code>{url}</code>\n\n"
                        f"Clique no botão abaixo para extrair a faixa de áudio em MP3!\n\n"
                        f"🤖 <b>via @{bot_username}</b>"
                    ),
                    parse_mode="HTML"
                ),
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                    InlineKeyboardButton(
                        text=f"🎧 Baixar Áudio MP3",
                        url=f"https://t.me/{bot_username}?start=audio_{short_id}",
                        style="primary"
                    )
                ]])
            )
        )

    await inline_query.answer(results, button=pm_button, cache_time=1)
