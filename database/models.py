from sqlalchemy import Table, Column, Integer, String, ForeignKey, DateTime, Float, Text, JSON, Boolean
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
    last_chatted_with = Column(DateTime, nullable=True)
    message_preview = Column(String, nullable=True)
    
    # Relationships
    character = relationship("Character", back_populates="conversations")
    creator = relationship("User", back_populates="created_conversations")
    participants = relationship("User", secondary=user_conversations, back_populates="participated_conversations")
    messages = relationship("Message", back_populates="conversation", order_by="Message.created_at")

class Character(Base):
    __tablename__ = "characters"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    character_description = Column(Text, nullable=False)  # Character's description
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
    language = Column(String, default="es")
    types = Column(JSON, default=list)
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
    wallet_address = Column(String, unique=True, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_active = Column(DateTime, default=datetime.utcnow)
    photo_url = Column(String, nullable=True)
    credits_spent = Column(Integer, default=0)
  
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

class RequestLog(Base):
    __tablename__ = "request_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    request_id = Column(String, nullable=False, index=True)
    endpoint = Column(String, nullable=False, index=True)
    method = Column(String, nullable=False)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    total_time_ms = Column(Float, nullable=False)
    llm_time_ms = Column(Float, default=0.0)
    db_time_ms = Column(Float, default=0.0)
    db_operations = Column(Integer, default=0)
    network_time_ms = Column(Float, default=0.0)
    app_time_ms = Column(Float, default=0.0)
    markers = Column(JSON, default=dict)
    
    def to_dict(self):
        return {
            "id": self.id,
            "request_id": self.request_id,
            "endpoint": self.endpoint,
            "method": self.method,
            "user_id": self.user_id,
            "timestamp": self.timestamp.isoformat(),
            "total_time_ms": self.total_time_ms,
            "llm_time_ms": self.llm_time_ms,
            "db_time_ms": self.db_time_ms,
            "db_operations": self.db_operations,
            "network_time_ms": self.network_time_ms,
            "app_time_ms": self.app_time_ms,
            "markers": self.markers
        }
