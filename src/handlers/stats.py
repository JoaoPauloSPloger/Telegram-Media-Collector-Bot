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
try:
    import psutil
except ImportError:
    psutil = None

import time
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.exceptions import TelegramAPIError
from src.database.db import AsyncSessionLocal, User, Event
from sqlalchemy import select, func
from src.utils.scheduler import telegram_scheduler
from src.utils.queue_manager import queue_manager

router = Router()
start_time = time.time()

active_panels = {}
panel_tabs = {}  # msg_id -> current_tab ("overview", "sys", "db", "queue")

def get_gauge_bar(percentage: float, length: int = 10) -> str:
    """Renders a smooth visual progress gauge."""
    percentage = max(0.0, min(100.0, percentage))
    filled = int(round((percentage / 100.0) * length))
    filled = max(0, min(length, filled))
    empty = length - filled
    return "▰" * filled + "▱" * empty

def get_status_indicator(percentage: float) -> str:
    """Returns a color indicator based on load percentage."""
    if percentage < 60.0:
        return "🟢"
    elif percentage < 85.0:
        return "🟡"
    return "🔴"

def format_uptime(seconds: int) -> str:
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    d, h = divmod(h, 24)
    if d > 0:
        return f"{d}d {h}h {m}m"
    elif h > 0:
        return f"{h}h {m}m {s}s"
    return f"{m}m {s}s"

def get_system_metrics():
    """Retrieves comprehensive hardware and operating system metrics."""
    if not psutil:
        return {
            "cpu": 0.0,
            "cpu_count": 1,
            "ram_pct": 0.0,
            "ram_used_gb": 0.0,
            "ram_total_gb": 1.0,
            "disk_pct": 0.0,
            "disk_free_gb": 1.0,
            "disk_total_gb": 1.0,
            "net_sent_mb": 0.0,
            "net_recv_mb": 0.0,
            "uptime": format_uptime(int(time.time() - start_time))
        }

    cpu = psutil.cpu_percent(interval=None)
    cpu_count = psutil.cpu_count(logical=True) or 1
    
    vm = psutil.virtual_memory()
    ram_pct = vm.percent
    ram_used_gb = vm.used / (1024 ** 3)
    ram_total_gb = vm.total / (1024 ** 3)
    
    disk = psutil.disk_usage('/')
    disk_pct = disk.percent
    disk_free_gb = disk.free / (1024 ** 3)
    disk_total_gb = disk.total / (1024 ** 3)
    
    net = psutil.net_io_counters()
    net_sent_mb = net.bytes_sent / (1024 * 1024)
    net_recv_mb = net.bytes_recv / (1024 * 1024)
    
    uptime = format_uptime(int(time.time() - start_time))
    
    return {
        "cpu": cpu,
        "cpu_count": cpu_count,
        "ram_pct": ram_pct,
        "ram_used_gb": ram_used_gb,
        "ram_total_gb": ram_total_gb,
        "disk_pct": disk_pct,
        "disk_free_gb": disk_free_gb,
        "disk_total_gb": disk_total_gb,
        "net_sent_mb": net_sent_mb,
        "net_recv_mb": net_recv_mb,
        "uptime": uptime
    }

async def get_db_metrics():
    """Retrieves database counts and download performance metrics."""
    async with AsyncSessionLocal() as session:
        users_count = await session.scalar(select(func.count()).select_from(User)) or 0
        total_events = await session.scalar(select(func.count()).select_from(Event)) or 0
        completed_events = await session.scalar(
            select(func.count()).select_from(Event).where(Event.status == 'completed')
        ) or 0
        failed_events = await session.scalar(
            select(func.count()).select_from(Event).where(Event.status == 'failed')
        ) or 0
        
        success_rate = (completed_events / total_events * 100) if total_events > 0 else 100.0
        
        return {
            "users_count": users_count,
            "total_events": total_events,
            "completed_events": completed_events,
            "failed_events": failed_events,
            "success_rate": success_rate
        }

def get_admin_keyboard(current_tab: str = "overview") -> InlineKeyboardMarkup:
    """Builds colored inline keyboard with active tab indicator."""
    btn_overview = "📊 Visão Geral" if current_tab != "overview" else "🔘 Visão Geral"
    btn_sys = "🖥️ Sistema" if current_tab != "sys" else "🔘 Sistema"
    btn_db = "📈 Downloads" if current_tab != "db" else "🔘 Downloads"
    btn_queue = "⚡ Fila" if current_tab != "queue" else "🔘 Fila"

    keyboard = [
        [
            InlineKeyboardButton(text="🔄 Atualizar", callback_data="refresh_stats", style="primary"),
            InlineKeyboardButton(text=btn_overview, callback_data="stats_tab_overview", style="primary"),
        ],
        [
            InlineKeyboardButton(text=btn_sys, callback_data="stats_tab_sys", style="primary"),
            InlineKeyboardButton(text=btn_db, callback_data="stats_tab_db", style="primary"),
            InlineKeyboardButton(text=btn_queue, callback_data="stats_tab_queue", style="primary"),
        ],
        [
            InlineKeyboardButton(text="❌ Fechar Painel", callback_data="close_stats", style="danger")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def format_admin_stats(sys_m: dict, db_m: dict, current_tab: str = "overview") -> str:
    """Formats formatted HTML dashboard based on selected tab."""
    sched_stats = telegram_scheduler.get_stats()
    queue_len = len(queue_manager.active_tasks)
    
    cpu_gauge = get_gauge_bar(sys_m['cpu'])
    cpu_ind = get_status_indicator(sys_m['cpu'])
    
    ram_gauge = get_gauge_bar(sys_m['ram_pct'])
    ram_ind = get_status_indicator(sys_m['ram_pct'])
    
    disk_gauge = get_gauge_bar(sys_m['disk_pct'])
    disk_ind = get_status_indicator(sys_m['disk_pct'])

    if current_tab == "sys":
        return (
            f"🖥️ <b>Painel do Sistema — Recursos de Hardware</b>\n\n"
            f"<b>Processador (CPU):</b> {cpu_ind} {sys_m['cpu']}%\n"
            f"<code>[{cpu_gauge}]</code> ({sys_m['cpu_count']} cores virtuais)\n\n"
            f"<b>Memória RAM:</b> {ram_ind} {sys_m['ram_pct']}%\n"
            f"<code>[{ram_gauge}]</code>\n"
            f"└ Uso: <code>{sys_m['ram_used_gb']:.2f} GB</code> / <code>{sys_m['ram_total_gb']:.2f} GB</code>\n\n"
            f"<b>Armazenamento (Disco):</b> {disk_ind} {sys_m['disk_pct']}%\n"
            f"<code>[{disk_gauge}]</code>\n"
            f"└ Livre: <code>{sys_m['disk_free_gb']:.1f} GB</code> / <code>{sys_m['disk_total_gb']:.1f} GB</code>\n\n"
            f"🌐 <b>Tráfego de Rede (I/O):</b>\n"
            f"├ ⬆️ Enviado: <code>{sys_m['net_sent_mb']:.1f} MB</code>\n"
            f"└ ⬇️ Recebido: <code>{sys_m['net_recv_mb']:.1f} MB</code>\n\n"
            f"⏱️ <b>Uptime:</b> <code>{sys_m['uptime']}</code>\n"
            f"<i>Atualização contínua a cada 5s...</i>"
        )
    elif current_tab == "db":
        return (
            f"📈 <b>Painel do Sistema — Banco de Dados & Downloads</b>\n\n"
            f"👥 <b>Usuários Registrados:</b> <code>{db_m['users_count']}</code>\n"
            f"📦 <b>Downloads Totais:</b> <code>{db_m['total_events']}</code>\n"
            f"├ ✅ Concluídos: <code>{db_m['completed_events']}</code>\n"
            f"└ ❌ Falhas/Cancelados: <code>{db_m['failed_events']}</code>\n\n"
            f"🎯 <b>Taxa de Sucesso:</b> <code>{db_m['success_rate']:.1f}%</code>\n"
            f"<code>[{get_gauge_bar(db_m['success_rate'])}]</code>\n\n"
            f"⏱️ <b>Uptime do Serviço:</b> <code>{sys_m['uptime']}</code>\n"
            f"<i>Atualização contínua a cada 5s...</i>"
        )
    elif current_tab == "queue":
        pause_str = f"⏸️ Pausado ({sched_stats['remaining_pause']}s)" if sched_stats['is_paused'] else "🟢 Despacho Ativo"
        return (
            f"⚡ <b>Painel do Sistema — Fila & Scheduler Anti-Spam</b>\n\n"
            f"📥 <b>Fila de Downloads Ativos:</b> <code>{queue_len}</code> tarefa(s)\n"
            f"🛡️ <b>Telegram Anti-Spam Scheduler:</b>\n"
            f"├ Status: <b>{pause_str}</b>\n"
            f"├ Fila de Mensagens: <code>{sched_stats['queue_size']}</code> pendente(s)\n"
            f"├ Mensagens Processadas: <code>{sched_stats['total_processed']}</code>\n"
            f"├ Limite de Taxa: <code>{sched_stats['max_rate_per_sec']} msg/s</code>\n"
            f"└ Bloqueios Flood/429 Contornados: <code>{sched_stats['total_flood_waits']}</code>\n\n"
            f"⏱️ <b>Uptime do Serviço:</b> <code>{sys_m['uptime']}</code>\n"
            f"<i>Atualização contínua a cada 5s...</i>"
        )

    # Default Overview
    return (
        f"📊 <b>Painel de Controle — TMCB Live Dashboard</b>\n\n"
        f"🖥️ <b>Hardware & Recursos:</b>\n"
        f"├ CPU: {cpu_ind} <code>[{cpu_gauge}]</code> <b>{sys_m['cpu']}%</b>\n"
        f"├ RAM: {ram_ind} <code>[{ram_gauge}]</code> <b>{sys_m['ram_pct']}%</b>\n"
        f"└ Disk: {disk_ind} <code>[{disk_gauge}]</code> <b>{sys_m['disk_pct']}%</b>\n\n"
        f"🌐 <b>Rede & Conexão:</b>\n"
        f"├ ⬆️ {sys_m['net_sent_mb']:.1f} MB | ⬇️ {sys_m['net_recv_mb']:.1f} MB\n"
        f"└ Uptime: <code>{sys_m['uptime']}</code>\n\n"
        f"📈 <b>Métricas do Bot:</b>\n"
        f"├ 👥 Usuários: <code>{db_m['users_count']}</code> | 📦 Downloads: <code>{db_m['total_events']}</code>\n"
        f"├ ⚡ Fila: <code>{queue_len}</code> ativo(s) | 🎯 Sucesso: <code>{db_m['success_rate']:.1f}%</code>\n"
        f"└ 🛡️ Scheduler Anti-Spam: <b>{'🟢 Ativo' if not sched_stats['is_paused'] else '🟡 Pausado'}</b>\n\n"
        f"<i>💡 Use os botões abaixo para alternar visualizações.</i>"
    )

def get_user_status_keyboard() -> InlineKeyboardMarkup:
    """Builds colored inline keyboard for regular users."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🔄 Atualizar Status", callback_data="refresh_user_status", style="primary"),
            InlineKeyboardButton(text="📥 Enviar Link", switch_inline_query_current_chat="", style="primary")
        ],
        [
            InlineKeyboardButton(text="❌ Fechar", callback_data="close_stats", style="danger")
        ]
    ])

def format_user_status(uptime: str, total_downloads: int, active_downloads: int) -> str:
    """Formats clean, user-friendly status message for regular users."""
    return (
        f"🤖 <b>Status do Sistema — TMCB</b>\n\n"
        f"🟢 <b>Serviço:</b> <code>100% Operacional</code>\n"
        f"⚡ <b>Downloads em Andamento:</b> <code>{active_downloads}</code>\n"
        f"📦 <b>Total de Mídias Entregues:</b> <code>{total_downloads}</code>\n"
        f"⏱️ <b>Tempo Online:</b> <code>{uptime}</code>\n\n"
        f"✨ <i>Envie qualquer link de mídia (Instagram, YouTube, TikTok, X, Bluesky, Spotify) diretamente aqui para baixar!</i>"
    )

@router.message(Command("stats", "status"))
async def show_stats(message: Message, db_user):
    """
    Handle the /stats and /status commands.
    Admins get the live interactive dashboard with colored buttons.
    Regular users get service status and health statistics.
    """
    is_admin = db_user and db_user.admin_level in [1, 2, 3]

    if not is_admin:
        sys_m = get_system_metrics()
        db_m = await get_db_metrics()
        queue_len = len(queue_manager.active_tasks)
        text = format_user_status(sys_m['uptime'], db_m['completed_events'], queue_len)
        keyboard = get_user_status_keyboard()
        await message.answer(text, reply_markup=keyboard, parse_mode="HTML")
        return

    # Admin Dashboard
    sys_m = get_system_metrics()
    db_m = await get_db_metrics()
    current_tab = "overview"

    text = format_admin_stats(sys_m, db_m, current_tab)
    keyboard = get_admin_keyboard(current_tab)

    msg = await message.answer(text, reply_markup=keyboard, parse_mode="HTML")
    active_panels[msg.message_id] = True
    panel_tabs[msg.message_id] = current_tab

    async def update_panel():
        start_update = time.time()
        try:
            while active_panels.get(msg.message_id, False):
                await asyncio.sleep(5)
                if not active_panels.get(msg.message_id, False):
                    break

                if time.time() - start_update > 300:
                    try:
                        await msg.edit_text("⏳ Painel expirado por inatividade. Digite /stats para reabrir.", reply_markup=None)
                    except TelegramAPIError:
                        pass
                    break

                tab = panel_tabs.get(msg.message_id, "overview")
                sm = get_system_metrics()
                dm = await get_db_metrics()
                new_text = format_admin_stats(sm, dm, tab)
                new_kb = get_admin_keyboard(tab)

                try:
                    await msg.edit_text(new_text, reply_markup=new_kb, parse_mode="HTML")
                except TelegramAPIError as e:
                    if "message to edit not found" in str(e).lower() or "message is not modified" not in str(e).lower():
                        break
        finally:
            active_panels.pop(msg.message_id, None)
            panel_tabs.pop(msg.message_id, None)

    asyncio.create_task(update_panel())

@router.callback_query(lambda c: c.data and c.data.startswith("stats_tab_"))
async def switch_stats_tab(callback_query: CallbackQuery):
    """Handle tab navigation buttons (Overview, System, DB, Queue)."""
    tab = callback_query.data.replace("stats_tab_", "")
    msg_id = callback_query.message.message_id
    panel_tabs[msg_id] = tab

    sys_m = get_system_metrics()
    db_m = await get_db_metrics()
    new_text = format_admin_stats(sys_m, db_m, tab)
    new_kb = get_admin_keyboard(tab)

    try:
        await callback_query.message.edit_text(new_text, reply_markup=new_kb, parse_mode="HTML")
        await callback_query.answer()
    except TelegramAPIError:
        try:
            await callback_query.answer()
        except TelegramAPIError:
            pass

@router.callback_query(lambda c: c.data == "refresh_stats")
async def refresh_stats_now(callback_query: CallbackQuery):
    """Manual instant refresh button."""
    msg_id = callback_query.message.message_id
    tab = panel_tabs.get(msg_id, "overview")

    sys_m = get_system_metrics()
    db_m = await get_db_metrics()
    new_text = format_admin_stats(sys_m, db_m, tab)
    new_kb = get_admin_keyboard(tab)

    try:
        await callback_query.message.edit_text(new_text, reply_markup=new_kb, parse_mode="HTML")
        await callback_query.answer("✅ Painel atualizado!", show_alert=False)
    except TelegramAPIError as e:
        if "message is not modified" in str(e).lower():
            await callback_query.answer("✅ Já está com os dados mais recentes!", show_alert=False)
        else:
            try:
                await callback_query.answer()
            except TelegramAPIError:
                pass

@router.callback_query(lambda c: c.data == "refresh_user_status")
async def refresh_user_status_now(callback_query: CallbackQuery):
    """Manual instant refresh button for regular users."""
    sys_m = get_system_metrics()
    db_m = await get_db_metrics()
    queue_len = len(queue_manager.active_tasks)
    text = format_user_status(sys_m['uptime'], db_m['completed_events'], queue_len)
    keyboard = get_user_status_keyboard()

    try:
        await callback_query.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
        await callback_query.answer("✅ Status atualizado!")
    except TelegramAPIError:
        try:
            await callback_query.answer("✅ Já atualizado!")
        except TelegramAPIError:
            pass

@router.callback_query(lambda c: c.data == "close_stats")
async def close_stats(callback_query: CallbackQuery):
    """Handle close button for dashboard and status panels."""
    try:
        await callback_query.answer()
    except TelegramAPIError:
        pass

    msg_id = callback_query.message.message_id
    if msg_id in active_panels:
        active_panels[msg_id] = False
        active_panels.pop(msg_id, None)
    panel_tabs.pop(msg_id, None)

    try:
        await callback_query.message.edit_text("✅ Painel finalizado.")
    except TelegramAPIError:
        pass
