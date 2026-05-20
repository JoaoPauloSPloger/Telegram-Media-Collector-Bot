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
    __tablename__ = 'users'

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=True)
    username = Column(String, nullable=True)
    eula_agreed = Column(Boolean, default=False)
    user_dc = Column(Integer, nullable=True) # or country string
    language_code = Column(String, nullable=True)
    use_cookies = Column(Boolean, default=False)
    encrypted_cookies = Column(String, nullable=True)
    
    groups = relationship('Group', secondary=user_groups, back_populates='members')

class Group(Base):
    __tablename__ = 'groups'

    id = Column(Integer, primary_key=True)
    title = Column(String, nullable=True)
    description = Column(String, nullable=True)
    dc_id = Column(Integer, nullable=True)
    
    members = relationship('User', secondary=user_groups, back_populates='groups')

class Event(Base):
    __tablename__ = 'events'

    event_id = Column(String, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    url = Column(String, nullable=False)
    status = Column(String, nullable=False) # e.g., 'started', 'completed', 'failed'
    error_msg = Column(String, nullable=True) # Full technical error

class Cache(Base):
    __tablename__ = 'cache'

    url = Column(String, primary_key=True)
    media_type = Column(String, primary_key=True)  # 'video', 'audio', 'doc', etc.
    file_id = Column(String, nullable=False)
    title = Column(String, nullable=True)
    description = Column(String, nullable=True)
