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
    try:
        with open('config.json', 'r') as f:
            c = json.load(f)
    except FileNotFoundError:
        c = {}
    except json.decoder.JSONDecodeError as e:
        print(f"WARNING: config.json is malformed ({e}). Falling back to environment variables.")
        c = {}

    # Override with environment variables if present
    c['bot_token'] = os.getenv('BOT_TOKEN', c.get('bot_token'))
    c['bot_username'] = os.getenv('BOT_USERNAME', c.get('bot_username'))
    c['aes_key'] = os.getenv('AES_KEY', c.get('aes_key', ''))
    c['local_api_server'] = os.getenv('LOCAL_API_SERVER', c.get('local_api_server'))
    # Use the mounted volume directory by default if running in Docker, otherwise it creates a local 'database' folder
    c['db_url'] = os.getenv('DB_URL', c.get('db_url', 'sqlite+aiosqlite:///database/bot_database.db'))

    c['sys_logging_channel_id'] = os.getenv('SYS_LOGGING_CHANNEL_ID', c.get('sys_logging_channel_id'))
    c['media_logging_channel_id'] = os.getenv('MEDIA_LOGGING_CHANNEL_ID', c.get('media_logging_channel_id'))

    return c

config = load_config()

# Ensure the database directory exists to prevent local crash without Docker
if config['db_url'].startswith('sqlite+aiosqlite:///database/'):
    os.makedirs('database', exist_ok=True)

# Database setup
engine = create_async_engine(config['db_url'], echo=False)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

        # Simple migration for existing DBs
        from sqlalchemy import text
        try:
            # Check if the column exists by trying to add it
            await conn.execute(text("ALTER TABLE events ADD COLUMN error_msg VARCHAR"))
        except Exception:
            # Column already exists or table doesn't exist yet
            pass

        try:
            # Force creation of cache table if it wasn't caught by create_all due to DB existing
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

# Encryption setup
# The key needs to be a 32-byte url-safe base64-encoded string.
# If the user put a dummy string, we should handle it or fail gracefully.
try:
    if not config.get('aes_key'):
        raise ValueError("No AES key provided")
    cipher_suite = Fernet(config['aes_key'].encode())
except ValueError:
    print("WARNING: Invalid AES key in config.json. Using a temporary key for this session.")
    temp_key = Fernet.generate_key()
    cipher_suite = Fernet(temp_key)

def encrypt_data(data: str) -> str:
    if not data:
        return None
    return cipher_suite.encrypt(data.encode()).decode()

def decrypt_data(encrypted_data: str) -> str:
    if not encrypted_data:
        return None
    return cipher_suite.decrypt(encrypted_data.encode()).decode()

async def get_user(session, user_id):
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload
    result = await session.execute(select(User).options(selectinload(User.groups)).where(User.id == user_id))
    return result.scalar_one_or_none()

async def create_user(session, user_id, name, username, language_code):
    user = User(id=user_id, name=name, username=username, language_code=language_code)
    session.add(user)
    await session.commit()
    return user

async def get_group(session, group_id):
    from sqlalchemy import select
    result = await session.execute(select(Group).where(Group.id == group_id))
    return result.scalar_one_or_none()

async def update_group_telemetry(session, user, chat):
    """
    Called when a user interacts in a group or supergroup.
    Updates the group info and links the user to the group if not already linked.
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
        # Update details if changed
        group.title = chat.title
        group.description = chat.description if hasattr(chat, 'description') else group.description
        
    # Link user to group if not already linked
    if group not in user.groups:
        user.groups.append(group)
        
    await session.commit()
