from sqlalchemy.orm import Session, joinedload
from typing import List, Optional
from .base import BaseRepository
from database.models import Conversation, Message, Character
from datetime import datetime

class ConversationRepository(BaseRepository[Conversation]):
    def __init__(self, db: Session):
        super().__init__(Conversation, db)
    
    def get_messages(self, conversation_id: int) -> List[Message]:
        conversation = self.get_by_id(conversation_id)
        if not conversation:
            return []
        return conversation.messages

    def update_last_chatted_with(self, conversation_id: int) -> Optional[Conversation]:
        conversation = self.get_by_id(conversation_id)
        if not conversation:
            return None
        conversation.last_chatted_with = datetime.utcnow()
        self.db.commit()
        self.db.refresh(conversation)
        return conversation
        
    def add_message(self, conversation_id: int, role: str, content: str) -> Optional[Message]:
        conversation = self.get_by_id(conversation_id)
        if not conversation:
            return None
        
        message = Message(
            conversation_id=conversation_id,
            role=role,
            content=content
        )
        self.db.add(message)
        
        # Update character message count if it's an assistant message
        if role == "assistant" and conversation.character:
            conversation.character.num_messages += 1
        
        self.db.commit()
        self.db.refresh(message)
        return message
    
    def get_by_participant(self, user_id: int) -> List[Conversation]:
        return self.db.query(Conversation)\
            .join(Conversation.participants)\
            .filter(user_id == user_id)\
            .all()

    def get_by_user_id(self, user_id: int) -> List[Conversation]:
        """Get all conversations for a user"""
        return self.db.query(Conversation)\
            .filter(Conversation.creator_id == user_id)\
            .order_by(Conversation.created_at.desc())\
            .all()

    def get_by_user_id_with_characters(self, user_id: int):
        """Get all conversations for a user with character details included"""
        return self.db.query(Conversation)\
            .options(joinedload(Conversation.character))\
            .filter(Conversation.creator_id == user_id)\
            .order_by(Conversation.last_chatted_with.desc().nullsfirst(), Conversation.created_at.desc())\
            .all()

    def update_message(self, message_id: int, content: str) -> Optional[Message]:
        """Update a message's content"""
        message = self.db.query(Message).filter(Message.id == message_id).first()
        if not message:
            return None
            
        message.content = content
        
        # Create a preview from the content
        preview = content[0:30] + "..." if len(content) > 30 else content
        
        # Update the conversation's message preview
        conversation = self.get_by_id(message.conversation_id)
        if conversation:
            conversation.message_preview = preview
        
        self.db.commit()
        self.db.refresh(message)
        return message
