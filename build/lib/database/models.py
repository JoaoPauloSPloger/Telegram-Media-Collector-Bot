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
