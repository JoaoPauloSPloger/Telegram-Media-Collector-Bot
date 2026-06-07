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

"""
Database models definition using SQLAlchemy declarative base.
"""

from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, Table
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()

user_groups = Table(
    'user_groups',
    Base.metadata,
    Column('user_id', Integer, ForeignKey('users.id'), primary_key=True),
    Column('group_id', Integer, ForeignKey('groups.id'), primary_key=True)
)

class User(Base):
    """
    Represents a Telegram user, storing preferences, cookie settings, and administrative privileges.
    """
    __tablename__ = 'users'

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=True)
    username = Column(String, nullable=True)
    eula_agreed = Column(Boolean, default=False)
    user_dc = Column(Integer, nullable=True)
    language_code = Column(String, nullable=True)
    use_cookies = Column(Boolean, default=False)
    encrypted_cookies = Column(String, nullable=True)
    admin_level = Column(Integer, default=0)
    admin_password = Column(String, nullable=True)
    
    groups = relationship('Group', secondary=user_groups, back_populates='members')

class Group(Base):
    """
    Represents a Telegram group or supergroup linked to users for telemetry.
    """
    __tablename__ = 'groups'

    id = Column(Integer, primary_key=True)
    title = Column(String, nullable=True)
    description = Column(String, nullable=True)
    dc_id = Column(Integer, nullable=True)
    
    members = relationship('User', secondary=user_groups, back_populates='groups')

class Event(Base):
    """
    Represents a download event trackable for logging and queuing purposes.
    """
    __tablename__ = 'events'

    event_id = Column(String, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    url = Column(String, nullable=False)
    status = Column(String, nullable=False)
    error_msg = Column(String, nullable=True)

class Cache(Base):
    """
    Caches previously downloaded file IDs from Telegram to allow direct inline delivery.
    """
    __tablename__ = 'cache'

    url = Column(String, primary_key=True)
    media_type = Column(String, primary_key=True)
    file_id = Column(String, nullable=False)
    title = Column(String, nullable=True)
    description = Column(String, nullable=True)
