from typing import List, Optional, Tuple
from sqlalchemy.orm import Session
from repositories.conversation_repository import ConversationRepository
from repositories.user_repository import UserRepository
from repositories.character_repository import CharacterRepository
from services.llm_service import LLMService
from database.models import Conversation, Message, User
from services.timing import time_db_operation, time_llm_operation, time_network_operation
import yaml
import os
import logging

# Set up logger
logger = logging.getLogger(__name__)

class ConversationService:
    def __init__(self, db: Session):
        self.db = db  # Store db reference for transactions
        self.repository = ConversationRepository(db)
        self.user_repository = UserRepository(db)
        self.character_repository = CharacterRepository(db)
        self.llm_service = LLMService()
        
        # Load prompts
        prompts_path = os.path.join(os.path.dirname(__file__), 'prompts.yaml')
        with open(prompts_path, 'r') as f:
            self.prompts = yaml.safe_load(f)
        
        # Define supported languages
        self.supported_languages = [
            "en",  # English
            "es",  # Spanish
            "pt",  # Portuguese
            "ko",  # Korean
            "ja",  # Japanese
            "id",  # Indonesian
            "fr",  # French
            "de",  # German
            "zh"   # Chinese
        ]
    
    @time_db_operation
    async def create_conversation(self, character_id: int, user_id: int, language: str = "en") -> Conversation:
        """
        Create a new conversation with initial greeting messages
        """
        # Get character
        character = self.character_repository.get_by_id(character_id)
        if not character:
            raise ValueError("Character not found")
        
        # Normalize language code
        language = language.lower().strip()
        # Extract primary language code if it's in format like 'en-US'
        if '-' in language:
            language = language.split('-')[0]
        
        # Get system prompt template based on language
        logger.info(f"Creating conversation with language: {language}")
        
        if language in self.supported_languages:
            prompt_key = f"CONVERSATION_SYSTEM_PROMPT_{language.upper()}"
            system_prompt = self.prompts.get(prompt_key)
            
            # If prompt exists for this language, use it
            if system_prompt:
                logger.info(f"Using specific prompt for language: {language}")
                system_prompt = system_prompt.format(character_description=character.character_description)
            else:
                # This shouldn't happen if the YAML is properly configured
                logger.warning(f"Prompt key {prompt_key} not found despite language being supported")
                system_prompt = self.prompts["CONVERSATION_SYSTEM_PROMPT_EN"].format(
                    character_description=character.character_description
                )
        else:
            # Fallback for unsupported languages
            logger.info(f"Using fallback prompt for unsupported language: {language}")
            system_prompt = self.prompts["CONVERSATION_SYSTEM_PROMPT_REST"].format(
                character_description=character.character_description, 
                language=language
            )
        
        # Create conversation
        conversation = self.repository.create({
            "character_id": character_id,
            "creator_id": user_id,
            "system_message": system_prompt
        })
        
        # Add initial user greeting (needed for LLM context)
        user_content = f"{character.name}!"
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
    
    @time_db_operation
    async def process_user_message(self, user_id: int, conversation_id: int, message_content: str) -> Tuple[Message, Message]:
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
        
        # Check user credits
        user = self.user_repository.get_by_id(user_id)
        if user.credits < 1:
            raise ValueError("Insufficient credits. Please purchase more credits to continue chatting.")
        
        try:
            # Get conversation history before adding new message
            history = self.get_conversation_messages(conversation_id)
            
            # Get AI response using LLM service first
            ai_response = await self._generate_ai_response(
                conversation.system_message,
                history,
                message_content
            )
            
            # Only after successful LLM response, add both messages in a transaction
            user_message = self.repository.add_message(
                conversation_id=conversation_id,
                role="user",
                content=message_content
            )
            
            ai_message = self.repository.add_message(
                conversation_id=conversation_id,
                role="assistant",
                content=ai_response
            )
            
            # Deduct credit after successful message exchange
            user.credits -= 1
            
            # Commit the transaction
            self.db.commit()
            
            return user_message, ai_message
            
        except Exception as e:
            # Rollback on error
            self.db.rollback()
            raise ValueError(f"Failed to process message: {str(e)}")
    
    @time_llm_operation
    async def _generate_ai_response(self, system_message: str, history: List[Message], user_message: str) -> str:
        """Internal method to generate AI response, wrapped with timing decorator"""
        return await self.llm_service.process_message(system_message, history, user_message)
    
    @time_db_operation
    async def stream_user_message(self, user_id: int, conversation_id: int, message_content: str):
        """
        Stream process a user message and generate AI response token by token
        Yields tokens from the AI response
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
        
        # Check user credits
        user = self.user_repository.get_by_id(user_id)
        if user.credits < 1:
            raise ValueError("Insufficient credits. Please purchase more credits to continue chatting.")
        
        try:
            # Get conversation history
            history = self.get_conversation_messages(conversation_id)
            
            # Save user message first
            user_message = self.repository.add_message(
                conversation_id=conversation_id,
                role="user",
                content=message_content
            )
            
            # Initialize empty AI message
            ai_message = self.repository.add_message(
                conversation_id=conversation_id,
                role="assistant",
                content=""
            )
            
            # Stream AI response and accumulate content
            accumulated_content = ""
            async for token in self._stream_ai_response(
                conversation.system_message,
                history,
                message_content
            ):
                accumulated_content += token
                # Update AI message content
                ai_message.content = accumulated_content
                yield token
            
            # Update final AI message and deduct credit
            self.repository.update_message(ai_message.id, accumulated_content)
            # Update message in memory too since we're still using it
            ai_message.content = accumulated_content
            user.credits -= 1
            self.db.commit()
            
        except Exception as e:
            # Rollback on error
            self.db.rollback()
            raise ValueError(f"Failed to process message: {str(e)}")
    
    @time_llm_operation
    async def _stream_ai_response(self, system_message: str, history: List[Message], user_message: str):
        """Internal method to stream AI response, wrapped with timing decorator"""
        async for token in self.llm_service.stream_message(system_message, history, user_message):
            yield token
    
    @time_db_operation
    def get_conversation_messages(self, conversation_id: int) -> List[Message]:
        """Get all messages in a conversation except the initial user greeting"""
        messages = self.repository.get_messages(conversation_id)
        # Filter out the first message (user's "hello")
        return messages[1:] if messages else []
    
    @time_db_operation
    def get_user_conversations(self, user_id: int) -> List[Conversation]:
        return self.repository.get_by_participant(user_id)
    
    @time_db_operation
    def get_conversations_with_characters(self, user_id: int):
        """Get all conversations for a user with character details included"""
        conversations = self.repository.get_by_user_id_with_characters(user_id)
        return conversations
