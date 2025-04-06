from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel
from database.database import get_db, SessionLocal
from database.models import User, Message
from services.conversation_service import ConversationService
from services.llm_service import LLMService
from dependencies.auth import get_current_user
from .character_routes import CharacterResponse
import logging
import time
from datetime import datetime
from sse_starlette.sse import EventSourceResponse

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = APIRouter(tags=["conversations"])

class ConversationCreate(BaseModel):
    character_id: int
    language: str = "EN"  # Optional, defaults to English

class MessageCreate(BaseModel):
    content: str

class MessageResponse(BaseModel):
    id: int
    role: str
    content: str
    
    class Config:
        orm_mode = True  # Use orm_mode in v1 instead of from_attributes

class ConversationResponse(BaseModel):
    id: int
    character_id: int
    created_at: str
    last_chatted_with: Optional[str] = None
    character: CharacterResponse
    message_preview: Optional[str] = ""

    class Config:
        orm_mode = True

    @classmethod
    def from_orm(cls, obj):
        # Convert datetime to string in ISO format
        if isinstance(obj.created_at, datetime):
            obj.created_at = obj.created_at.isoformat()
        if isinstance(obj.last_chatted_with, datetime):
            obj.last_chatted_with = obj.last_chatted_with.isoformat()
        return super().from_orm(obj)

@router.post("/{conversation_id}/stream/token")
async def get_stream_token(
    conversation_id: int,
    message: MessageCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get a temporary token for streaming"""
    return {"token": "removed"}

@router.post("/{conversation_id}/messages", response_model=List[MessageResponse])
async def send_message(
    conversation_id: int,
    message: MessageCreate,
    current_user: User = Depends(get_current_user)
):
    """
    Send a message in a conversation and get the AI's response
    Returns both the user's message and the AI's response
    
    Optimized to avoid holding database connections during API calls
    """
    try:
        user_id = current_user.id
        message_content = message.content
        
        # Step 1: Get only the necessary data with a brief DB connection
        db_read = next(get_db())
        try:
            # Create a service just to get required data
            temp_service = ConversationService(db_read)
            
            # Check if conversation exists and user has access
            conversation = temp_service.repository.get_by_id(conversation_id)
            if not conversation:
                raise ValueError("Conversation not found")
                
            if conversation.creator_id != user_id and user_id not in [p.id for p in conversation.participants]:
                raise ValueError("User does not have access to this conversation")
            
            # Check user credits
            user = temp_service.user_repository.get_by_id(user_id)
            if user.credits < 1:
                raise ValueError("Insufficient credits. Please purchase more credits to continue chatting.")
            
            # Get conversation history and system message
            system_message = conversation.system_message
            history = temp_service.get_conversation_messages(conversation_id)
        finally:
            # Close the first DB connection before external API call
            db_read.close()
        
        # Step 2: Call LLM API without holding any DB connection
        llm_service = LLMService()
        ai_response = await llm_service.process_message(system_message, history, message_content)
        
        # Step 3: Only open a new DB connection after we have the LLM response
        db_write = next(get_db())
        try:
            # Create a new service with a fresh connection for writes
            service = ConversationService(db_write)
            
            # Add both messages in a transaction
            user_message = service.repository.add_message(
                conversation_id=conversation_id,
                role="user",
                content=message_content
            )
            
            ai_message = service.repository.add_message(
                conversation_id=conversation_id,
                role="assistant",
                content=ai_response
            )
            
            # Update last chatted with timestamp
            service.repository.update_last_chatted_with(conversation_id)
            
            # Deduct credit
            user = service.user_repository.get_by_id(user_id)
            user.credits -= 1
            
            # Commit all changes at once
            db_write.commit()
            
            return [user_message, ai_message]
        except Exception as e:
            db_write.rollback()
            raise ValueError(f"Failed to save messages: {str(e)}")
        finally:
            # Make sure to close the write connection
            db_write.close()
            
    except ValueError as e:
        logger.error(f"Error sending message: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error sending message: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{conversation_id}/messages", response_model=List[MessageResponse])
async def get_conversation_messages(
    conversation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    try:
        service = ConversationService(db)
        messages = service.get_conversation_messages(conversation_id)
        if not messages:
            raise HTTPException(status_code=404, detail="Conversation not found")
        return messages
    except Exception as e:
        logger.error(f"Error getting messages: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/", response_model=List[ConversationResponse])
async def get_conversations(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get all conversations for the current user with character details"""
    try:
        # logger.info(f"Getting conversations for user {current_user.id} (email: {current_user.email})")
        service = ConversationService(db)
        conversations = service.get_conversations_with_characters(current_user.id)
        return conversations
    except Exception as e:
        logger.error(f"Error getting conversations: {str(e)}")
        logger.exception("Full traceback:")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/", response_model=int)
async def create_conversation(
    conversation: ConversationCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    try:
        service = ConversationService(db)
        conv = await service.create_conversation(
            character_id=conversation.character_id,
            user_id=current_user.id,
            language=conversation.language
        )
        return conv.id
    except ValueError as e:
        logger.error(f"Error creating conversation: {str(e)}")
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error creating conversation: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{conversation_id}/stream", response_class=EventSourceResponse)
async def stream_message(
    conversation_id: int,
    content: str,
    session_token: str = None,
    current_user: User = Depends(get_current_user)
):
    """
    Stream a message in a conversation and get the AI's response token by token
    Returns a stream of SSE events containing tokens
    
    Optimized to avoid holding database connections during API calls
    """
    try:
        user_id = current_user.id
        message_content = content
        
        # Step 1: Get only the necessary data with a brief DB connection
        db_read = next(get_db())
        try:
            # Create a service just to get required data
            temp_service = ConversationService(db_read)
            
            # Check if conversation exists and user has access
            conversation = temp_service.repository.get_by_id(conversation_id)
            if not conversation:
                raise ValueError("Conversation not found")
                
            if conversation.creator_id != user_id and user_id not in [p.id for p in conversation.participants]:
                raise ValueError("User does not have access to this conversation")
            
            # Get the character and its creator ID for later use
            character = conversation.character
            character_creator_id = character.creator_id
            
            # Check user credits
            user = temp_service.user_repository.get_by_id(user_id)
            if user.credits < 1:
                raise ValueError("Insufficient credits. Please purchase more credits to continue chatting.")
            
            # Get conversation history and system message
            system_message = conversation.system_message
            history = temp_service.get_conversation_messages(conversation_id)
            
            # Create detached Message objects to avoid database session issues
            detached_history = []
            for msg in history:
                # Create a new Message object with just the needed attributes
                detached_msg = Message(
                    id=msg.id,
                    role=msg.role,
                    content=msg.content
                )
                detached_history.append(detached_msg)
            
            # Add user message upfront, before streaming
            user_message = temp_service.repository.add_message(
                conversation_id=conversation_id,
                role="user",
                content=message_content
            )
            
            # Initialize empty AI message to be updated later
            ai_message = temp_service.repository.add_message(
                conversation_id=conversation_id,
                role="assistant",
                content=""
            )
            
            # Store necessary IDs for later
            ai_message_id = ai_message.id
            
            # Commit these changes
            db_read.commit()
        finally:
            # Close the DB connection before starting streaming
            db_read.close()
        
        # Step 2: Set up LLM service for streaming (no DB connection held)
        llm_service = LLMService()
        
        async def event_generator():
            # Stream AI response without holding a DB connection
            accumulated_content = ""
            try:
                async for token in llm_service.stream_message(system_message, detached_history, message_content):
                    accumulated_content += token
                    yield {
                        "event": "token",
                        "data": token
                    }
                
                # After streaming is complete, update the message in the database
                db_update = next(get_db())
                try:
                    update_service = ConversationService(db_update)
                    # Update message with complete content
                    update_service.repository.update_message(ai_message_id, accumulated_content)
                    # Update last_chatted_with timestamp
                    update_service.repository.update_last_chatted_with(conversation_id)
                    # Deduct credit
                    user = update_service.user_repository.get_by_id(user_id)
                    user.credits -= 1
                    
                    # Increment the character creator's message received counter
                    # Only if the message sender is not the character creator
                    if user_id != character_creator_id:
                        character_creator = update_service.user_repository.get_by_id(character_creator_id)
                        character_creator.character_messages_received += 1
                    
                    db_update.commit()
                except Exception as db_error:
                    db_update.rollback()
                    logger.error(f"Error updating message after streaming: {str(db_error)}")
                finally:
                    db_update.close()
                
                # Send done event when streaming completes successfully
                yield {
                    "event": "done",
                    "data": ""
                }
            except Exception as stream_error:
                logger.error(f"Error during streaming: {str(stream_error)}")
                yield {
                    "event": "error",
                    "data": str(stream_error)
                }
        
        return EventSourceResponse(event_generator())
        
    except ValueError as e:
        logger.error(f"Error streaming message: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error streaming message: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))