from sqlalchemy import Table, Column, Integer, String, ForeignKey, DateTime, Float, Text, JSON
from sqlalchemy.orm import relationship
from datetime import datetime
from .database import Base

# Association table for User-Conversation (for conversations a user participates in)
user_conversations = Table(
    'user_conversations',
    Base.metadata,
    Column('user_id', Integer, ForeignKey('users.id')),
    Column('conversation_id', Integer, ForeignKey('conversations.id'))
)

class Message(Base):
    __tablename__ = "messages"
    
    id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(Integer, ForeignKey('conversations.id'))
    role = Column(String, nullable=False)  # 'user' or 'assistant'
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    conversation = relationship("Conversation", back_populates="messages")

class Conversation(Base):
    __tablename__ = "conversations"
    
    id = Column(Integer, primary_key=True, index=True)
    character_id = Column(Integer, ForeignKey('characters.id'))
    creator_id = Column(Integer, ForeignKey('users.id'))
    system_message = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    character = relationship("Character", back_populates="conversations")
    creator = relationship("User", back_populates="created_conversations")
    participants = relationship("User", secondary=user_conversations, back_populates="participated_conversations")
    messages = relationship("Message", back_populates="conversation", order_by="Message.created_at")

class Character(Base):
    __tablename__ = "characters"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    system_prompt = Column(Text, nullable=False)
    greeting = Column(Text, nullable=False)  # Character's initial greeting message
    tagline = Column(String)
    photo_url = Column(String)
    creator_id = Column(Integer, ForeignKey('users.id'))
    num_chats_created = Column(Integer, default=0)
    num_messages = Column(Integer, default=0)  # Combined sent/received
    rating = Column(Float, default=0.0)
    attributes = Column(JSON, default=list)  # Store attributes as JSON array
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    creator = relationship("User", back_populates="created_characters")
    conversations = relationship("Conversation", back_populates="character")

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    email = Column(String, unique=True, index=True)
    credits = Column(Integer, default=100)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    created_characters = relationship("Character", back_populates="creator")
    created_conversations = relationship("Conversation", back_populates="creator")
    participated_conversations = relationship("Conversation", secondary=user_conversations, back_populates="participants")
