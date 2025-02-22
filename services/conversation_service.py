from typing import List, Optional, Tuple
from sqlalchemy.orm import Session
from repositories.conversation_repository import ConversationRepository
from repositories.user_repository import UserRepository
from repositories.character_repository import CharacterRepository
from services.llm_service import LLMService
from database.models import Conversation, Message, User
import yaml
import os

class ConversationService:
    def __init__(self, db: Session):
        self.repository = ConversationRepository(db)
        self.user_repository = UserRepository(db)
        self.character_repository = CharacterRepository(db)
        self.llm_service = LLMService()
        
        # Load prompts
        prompts_path = os.path.join(os.path.dirname(__file__), 'prompts.yaml')
        with open(prompts_path, 'r') as f:
            self.prompts = yaml.safe_load(f)
    
    def create_conversation(self, character_id: int, user_id: int, language: str = "EN") -> Conversation:
        """
        Create a new conversation with initial greeting messages
        """
        # Get character
        character = self.character_repository.get_by_id(character_id)
        if not character:
            raise ValueError("Character not found")
            
        # Get system prompt template
        prompt_key = f"CONVERSATION_SYSTEM_PROMPT_{language.upper()}"
        system_prompt = self.prompts.get(prompt_key, self.prompts["CONVERSATION_SYSTEM_PROMPT_EN"])
        
        # Insert character description into system prompt
        system_prompt = system_prompt.format(
            character_description=character.system_prompt
        )
        
        # Create conversation
        conversation = self.repository.create({
            "character_id": character_id,
            "creator_id": user_id,
            "system_message": system_prompt
        })
        
        # Add initial user greeting (needed for LLM context)
        user_content = f"Hello {character.name}"
        user_message = self.repository.add_message(
            conversation_id=conversation.id,
            role="user",
            content=user_content
        )
        
        # Add character's greeting from their profile
        ai_message = self.repository.add_message(
            conversation_id=conversation.id,
            role="assistant",
            content=character.greeting
        )
        
        return conversation
    
    def process_user_message(self, user_id: int, conversation_id: int, message_content: str) -> Tuple[Message, Message]:
        """
        Process a user message and generate AI response
        Returns tuple of (user_message, ai_message)
        Raises:
            ValueError: If conversation not found or user doesn't have access
            RuntimeError: If message processing fails
        """
        # Get conversation and verify user has access
        conversation = self.repository.get_by_id(conversation_id)
        if not conversation:
            raise ValueError("Conversation not found")
            
        if conversation.creator_id != user_id and user_id not in [p.id for p in conversation.participants]:
            raise ValueError("User does not have access to this conversation")
            
        # Add user message to conversation
        user_message = self.repository.add_message(
            conversation_id=conversation_id,
            role="user",
            content=message_content
        )
        
        try:
            # Get conversation history excluding the new message
            history = self.get_conversation_messages(conversation_id)
            
            # Get AI response using LLM service
            ai_response = self.llm_service.process_message(
                conversation.system_message,
                history,
                message_content
            )
            
            # Add AI response to conversation
            ai_message = self.repository.add_message(
                conversation_id=conversation_id,
                role="assistant",
                content=ai_response
            )
            
            return user_message, ai_message
            
        except Exception as e:
            # If AI processing fails, still keep the user message but raise error
            raise RuntimeError(f"Failed to process message: {str(e)}")
    
    def get_conversation_messages(self, conversation_id: int) -> List[Message]:
        """Get all messages in a conversation except the initial user greeting"""
        messages = self.repository.get_messages(conversation_id)
        # Filter out the first message (user's "hello")
        return messages[1:] if messages else []
    
    def get_user_conversations(self, user_id: int) -> List[Conversation]:
        return self.repository.get_by_participant(user_id)
