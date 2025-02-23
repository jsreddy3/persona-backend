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
    world_id = Column(String, unique=True, index=True)  # World ID nullifier hash
    username = Column(String, unique=True, index=True, nullable=True)  # Optional
    email = Column(String, unique=True, index=True, nullable=True)    # Optional
    language = Column(String, default="en")  # Default language
    credits = Column(Integer, default=100)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_active = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    created_characters = relationship("Character", back_populates="creator")
    created_conversations = relationship("Conversation", back_populates="creator")
    participated_conversations = relationship("Conversation", secondary=user_conversations, back_populates="participants")
    verifications = relationship("WorldIDVerification", back_populates="user")
    payments = relationship("Payment", backref="user")
    sessions = relationship("Session", back_populates="user")

class Session(Base):
    __tablename__ = "sessions"
    
    id = Column(Integer, primary_key=True, index=True)
    token = Column(String, unique=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    expires = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    user = relationship("User", back_populates="sessions")

class Payment(Base):
    __tablename__ = "payments"
    
    id = Column(Integer, primary_key=True, index=True)
    reference = Column(String, unique=True, index=True)  # Unique payment reference
    user_id = Column(Integer, ForeignKey("users.id"))
    status = Column(String)  # pending, confirmed, failed
    amount = Column(Integer)  # Amount in credits
    transaction_id = Column(String, nullable=True)  # World ID transaction ID
    created_at = Column(DateTime, default=datetime.utcnow)

class WorldIDVerification(Base):
    __tablename__ = "world_id_verifications"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    nullifier_hash = Column(String, nullable=False, index=True)
    merkle_root = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationship
    user = relationship("User", back_populates="verifications")
