import json
import base64
from cryptography.fernet import Fernet
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from src.database.models import Base, User, Group, Event

def load_config():
    with open('config.json', 'r') as f:
        return json.load(f)

config = load_config()

# Database setup
engine = create_async_engine(config['db_url'], echo=False)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

# Encryption setup
# The key needs to be a 32-byte url-safe base64-encoded string.
# If the user put a dummy string, we should handle it or fail gracefully.
try:
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
