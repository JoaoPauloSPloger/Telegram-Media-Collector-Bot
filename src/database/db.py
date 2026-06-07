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

import os
import json
import base64
from cryptography.fernet import Fernet
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from src.database.models import Base, User, Group, Event

def load_config():
    """
    Loads runtime configuration from config.json and overrides with environment variables.
    """
    try:
        with open('config.json', 'r') as f:
            c = json.load(f)
    except FileNotFoundError:
        c = {}
    except json.decoder.JSONDecodeError as e:
        print(f"WARNING: config.json is malformed ({e}). Falling back to environment variables.")
        c = {}

    c['bot_token'] = os.getenv('BOT_TOKEN', c.get('bot_token'))
    c['bot_username'] = os.getenv('BOT_USERNAME', c.get('bot_username'))
    c['aes_key'] = os.getenv('AES_KEY', c.get('aes_key', ''))
    c['local_api_server'] = os.getenv('LOCAL_API_SERVER', c.get('local_api_server'))
    c['db_url'] = os.getenv('DB_URL', c.get('db_url', 'sqlite+aiosqlite:///database/bot_database.db'))

    c['sys_logging_channel_id'] = os.getenv('SYS_LOGGING_CHANNEL_ID', c.get('sys_logging_channel_id'))
    c['media_logging_channel_id'] = os.getenv('MEDIA_LOGGING_CHANNEL_ID', c.get('media_logging_channel_id'))
    c['admin_password'] = os.getenv('ADMIN_PASSWORD', c.get('admin_password'))

    c['queue_alert_threshold'] = int(os.getenv('QUEUE_ALERT_THRESHOLD', c.get('queue_alert_threshold', 50)))
    c['max_playlist_items'] = int(os.getenv('MAX_PLAYLIST_ITEMS', c.get('max_playlist_items', 100)))

    c['llm_provider'] = os.getenv('LLM_PROVIDER', c.get('llm_provider'))
    c['llm_api_key'] = os.getenv('LLM_API_KEY', c.get('llm_api_key'))
    c['llm_local_url'] = os.getenv('LLM_LOCAL_URL', c.get('llm_local_url'))
    c['llm_model'] = os.getenv('LLM_MODEL', c.get('llm_model'))

    c['max_bandwidth'] = os.getenv('MAX_BANDWIDTH', c.get('max_bandwidth', '25M'))

    return c

config = load_config()

if config['db_url'].startswith('sqlite+aiosqlite:///database/'):
    os.makedirs('database', exist_ok=True)

engine = create_async_engine(config['db_url'], echo=False)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)

async def init_db():
    """
    Initializes database schema and handles tables creation and migrations.
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

        from sqlalchemy import text
        try:
            await conn.execute(text("ALTER TABLE events ADD COLUMN error_msg VARCHAR"))
        except Exception:
            pass

        try:
            await conn.execute(text("""
                CREATE TABLE IF NOT EXISTS cache (
                    url VARCHAR NOT NULL,
                    media_type VARCHAR NOT NULL,
                    file_id VARCHAR NOT NULL,
                    title VARCHAR,
                    description VARCHAR,
                    PRIMARY KEY (url, media_type)
                )
            """))
        except Exception:
            pass

        try:
            await conn.execute(text("ALTER TABLE cache ADD COLUMN title VARCHAR"))
            await conn.execute(text("ALTER TABLE cache ADD COLUMN description VARCHAR"))
        except Exception:
            pass

        try:
            await conn.execute(text("ALTER TABLE users ADD COLUMN admin_level INTEGER DEFAULT 0"))
        except Exception:
            pass

        try:
            await conn.execute(text("ALTER TABLE users ADD COLUMN admin_password VARCHAR"))
        except Exception:
            pass

try:
    if not config.get('aes_key'):
        raise ValueError("No AES key provided")
    cipher_suite = Fernet(config['aes_key'].encode())
except ValueError:
    print("WARNING: Invalid AES key in config.json. Using a temporary key for this session.")
    temp_key = Fernet.generate_key()
    cipher_suite = Fernet(temp_key)

def encrypt_data(data: str) -> str:
    """
    Encrypts sensitive string data using AES-256 Fernet encryption.
    """
    if not data:
        return None
    return cipher_suite.encrypt(data.encode()).decode()

def decrypt_data(encrypted_data: str) -> str:
    """
    Decrypts AES-256 Fernet encrypted data back to plain text.
    """
    if not encrypted_data:
        return None
    try:
        return cipher_suite.decrypt(encrypted_data.encode()).decode()
    except Exception:
        return None

async def get_user(session, user_id):
    """
    Fetches a User from the database by ID, eager loading their associated groups.
    """
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload
    result = await session.execute(select(User).options(selectinload(User.groups)).where(User.id == user_id))
    return result.scalar_one_or_none()

async def create_user(session, user_id, name, username, language_code):
    """
    Creates and commits a new User record in the database.
    """
    user = User(id=user_id, name=name, username=username, language_code=language_code)
    session.add(user)
    await session.commit()
    return user

async def get_group(session, group_id):
    """
    Fetches a Group record from the database by its ID.
    """
    from sqlalchemy import select
    result = await session.execute(select(Group).where(Group.id == group_id))
    return result.scalar_one_or_none()

async def update_group_telemetry(session, user, chat):
    """
    Updates group details and links the user to the group for telemetry tracking.
    """
    if chat.type not in ['group', 'supergroup']:
        return
        
    group = await get_group(session, chat.id)
    if not group:
        group = Group(
            id=chat.id,
            title=chat.title,
            description=chat.description if hasattr(chat, 'description') else None
        )
        session.add(group)
    else:
        group.title = chat.title
        group.description = chat.description if hasattr(chat, 'description') else group.description
        
    if group not in user.groups:
        user.groups.append(group)
        
    await session.commit()
