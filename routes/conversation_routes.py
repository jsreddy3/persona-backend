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
from database.db_utils import batch_update, increment_counter, deduct_user_credits
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
    
    Optimized for global distribution with reduced database roundtrips
    """
    try:
        user_id = current_user.id
        message_content = message.content
        
        # STEP 1: Comprehensive database session for preparation
        db_read = next(get_db())
        
        conversation = None
        character_creator_id = None
        system_message = None
        detached_history = []
        user_message_id = None
        
        try:
            # Get conversation with all needed data in a single query
            service = ConversationService(db_read)
            conversation = service.repository.get_by_id(conversation_id)
            
            if not conversation:
                raise ValueError("Conversation not found")
                
            if conversation.creator_id != user_id and user_id not in [p.id for p in conversation.participants]:
                raise ValueError("User does not have access to this conversation")
            
            # Store character creator ID for later counter increment
            character_creator_id = conversation.character.creator_id
            
            # Check user credits
            user = service.user_repository.get_by_id(user_id)
            if user.credits < 1:
                raise ValueError("Insufficient credits. Please purchase more credits to continue chatting.")
            
            # Get conversation history and system message
            system_message = conversation.system_message
            history = service.get_conversation_messages(conversation_id)
            
            # Create detached copies to avoid database session issues
            for msg in history:
                detached_history.append({
                    "role": msg.role,
                    "content": msg.content
                })
            
            # Add user message
            user_message = service.repository.add_message(
                conversation_id=conversation_id,
                role="user",
                content=message_content
            )
            user_message_id = user_message.id
            
            # Commit the user message
            db_read.commit()
        except Exception as setup_error:
            db_read.rollback()
            logger.error(f"Error in send message setup: {str(setup_error)}")
            raise setup_error
        finally:
            # Close the DB connection before API call
            db_read.close()
        
        # STEP 2: Call LLM API without holding any DB connection
        llm_service = LLMService()
        ai_response = await llm_service.process_message(system_message, detached_history, message_content)
        
        # STEP 3: Single database session for all updates
        db_write = next(get_db())
        try:
            # Use a single transaction for all updates to minimize roundtrips
            service = ConversationService(db_write)
            
            # Add AI response message
            ai_message = service.repository.add_message(
                conversation_id=conversation_id,
                role="assistant",
                content=ai_response
            )
            
            # Use batch updates for the rest of the changes
            updates = [
                # Update conversation timestamp
                (
                    "UPDATE conversations SET last_chatted_with = NOW() WHERE id = :id",
                    {"id": conversation_id}
                ),
                # Deduct user credit (atomic operation)
                (
                    "UPDATE users SET credits = credits - 1 WHERE id = :id AND credits >= 1",
                    {"id": user_id}
                ),
                # Increment character creator's message counter (atomic operation)
                (
                    "UPDATE users SET character_messages_received = character_messages_received + 1 WHERE id = :id",
                    {"id": character_creator_id}
                )
            ]
            
            # Execute the batch updates
            batch_update(db_write, updates)
            
            # Get the messages to return
            user_message_obj = service.repository.get_message_by_id(user_message_id)
            ai_message_obj = ai_message
            
            db_write.commit()
            
            # Return both messages
            return [
                MessageResponse(
                    id=user_message_obj.id,
                    role=user_message_obj.role,
                    content=user_message_obj.content
                ),
                MessageResponse(
                    id=ai_message_obj.id,
                    role=ai_message_obj.role,
                    content=ai_message_obj.content
                )
            ]
        except Exception as db_error:
            db_write.rollback()
            logger.error(f"Error in message response handling: {str(db_error)}")
            raise HTTPException(status_code=500, detail=str(db_error))
        finally:
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
    current_user: User = Depends(get_current_user)
):
    """
    Get all messages for a conversation
    
    Optimized for global distribution with reduced database roundtrips
    """
    try:
        user_id = current_user.id
        
        # Use a short-lived database connection
        db = next(get_db())
        try:
            # Verify access and get messages in one efficient query
            service = ConversationService(db)
            
            # First verify the user has access to this conversation
            conversation = service.repository.get_by_id(conversation_id)
            if not conversation:
                raise HTTPException(status_code=404, detail="Conversation not found")
                
            if conversation.creator_id != user_id and user_id not in [p.id for p in conversation.participants]:
                raise HTTPException(status_code=403, detail="User does not have access to this conversation")
            
            # Get messages using an optimized query
            messages = service.get_conversation_messages(conversation_id)
            
            # Detach messages from the session to avoid serialization issues
            for message in messages:
                db.expunge(message)
                
            return messages
        finally:
            # Ensure connection is closed
            db.close()
    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        logger.error(f"Error getting conversation messages: {str(e)}")
        logger.exception("Full traceback:")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/", response_model=List[ConversationResponse])
async def get_conversations(
    current_user: User = Depends(get_current_user)
):
    """Get all conversations for the current user with character details
    
    Optimized for global distribution with reduced database roundtrips"""
    try:
        user_id = current_user.id
        
        # Use a single short-lived database connection
        db = next(get_db())
        try:
            service = ConversationService(db)
            
            # Use a more efficient query to get only the necessary data
            conversations = service.get_conversations_with_characters(user_id)
            
            # Detach the objects from the session to avoid serialization issues
            # This allows the session to be closed earlier
            detached_convos = []
            for convo in conversations:
                # Add message preview if not already present
                if not convo.message_preview and hasattr(convo, 'messages') and convo.messages:
                    last_message = next((m for m in convo.messages if m.role == 'assistant'), None)
                    if last_message:
                        preview = last_message.content[:50] + ("..." if len(last_message.content) > 50 else "")
                        convo.message_preview = preview
                
                # Make a copy to detach from session
                db.expunge(convo)
            
            return conversations
        finally:
            # Ensure connection is closed
            db.close()
    except Exception as e:
        logger.error(f"Error getting conversations: {str(e)}")
        logger.exception("Full traceback:")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/", response_model=int)
async def create_conversation(
    conversation: ConversationCreate,
    current_user: User = Depends(get_current_user)
):
    """
    Create a new conversation
    
    Optimized for global distribution with reduced database roundtrips
    """
    try:
        user_id = current_user.id
        character_id = conversation.character_id
        language = conversation.language
        
        # Use a short-lived database connection
        db = next(get_db())
        try:
            service = ConversationService(db)
            
            # Verify character exists
            character_service = CharacterService(db)
            character = character_service.get_character_by_id(character_id)
            if not character:
                raise ValueError(f"Character with ID {character_id} not found")
            
            # Create the conversation with all data in a single transaction
            conv = await service.create_conversation(
                character_id=character_id,
                user_id=user_id,
                language=language
            )
            
            # Get the ID before closing the connection
            conversation_id = conv.id
            
            # Use batch_update for consistent approach with other optimized routes
            from database.db_utils import batch_update
            
            # Updates to perform in a single transaction
            updates = [
                # Update user conversation count if needed
                (
                    "UPDATE users SET conversations_count = conversations_count + 1 WHERE id = :user_id",
                    {"user_id": user_id}
                ),
                # Any other batch updates needed for conversation creation
            ]
            
            # Execute all updates in one transaction
            batch_update(db, updates)
            
            return conversation_id
        except Exception as e:
            db.rollback()
            raise e
        finally:
            # Ensure connection is closed
            db.close()
    except ValueError as e:
        logger.error(f"Error creating conversation: {str(e)}")
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error creating conversation: {str(e)}")
        logger.exception("Full traceback:")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/{conversation_id}/messages/stream")
async def stream_message(
    conversation_id: int,
    content: str,
    session_token: str = None,
    current_user: User = Depends(get_current_user)
):
    """
    Stream a message in a conversation and get the AI's response token by token
    Returns a stream of SSE events containing tokens
    
    Optimized for global distribution with reduced database roundtrips
    """
    try:
        user_id = current_user.id
        message_content = content
        
        # STEP 1: Single comprehensive database session for preparation
        # This consolidates multiple database operations into one session
        db_read = next(get_db())
        
        conversation = None
        character_creator_id = None
        system_message = None
        detached_history = []
        user_message_id = None
        ai_message_id = None
        
        try:
            # Get conversation with all needed data in a single query
            service = ConversationService(db_read)
            conversation = service.repository.get_by_id(conversation_id)
            
            if not conversation:
                raise ValueError("Conversation not found")
                
            # Check if user has access to this conversation
            if conversation.creator_id != user_id and user_id not in [p.id for p in conversation.participants]:
                raise ValueError("User does not have access to this conversation")
            
            # Get user for credit check (access pattern optimized)
            user = service.user_repository.get_by_id(user_id)
            if user.credits < 1:
                raise ValueError("Insufficient credits. Please purchase more credits to continue chatting.")
            
            # Store essential data needed during streaming
            character_creator_id = conversation.character.creator_id
            system_message = conversation.system_message
            
            # Get conversation history and create detached copies to avoid DB dependency
            history = service.get_conversation_messages(conversation_id)
            for msg in history:
                # Create simplified dict representations instead of ORM objects
                detached_history.append({
                    "role": msg.role,
                    "content": msg.content
                })
            
            # Add user message - this now uses a direct repository call
            user_message = service.repository.add_message(
                conversation_id=conversation_id,
                role="user",
                content=message_content
            )
            user_message_id = user_message.id
            
            # Initialize empty AI message
            ai_message = service.repository.add_message(
                conversation_id=conversation_id,
                role="assistant",
                content=""
            )
            ai_message_id = ai_message.id
            
            # Perform all database writes in a single commit
            db_read.commit()
        except Exception as setup_error:
            db_read.rollback()
            logger.error(f"Error in stream message setup: {str(setup_error)}")
            raise setup_error
        finally:
            # Close the DB connection before starting streaming
            db_read.close()
        
        # STEP 2: Set up LLM service for streaming (no DB connection held)
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
                
                # STEP 3: Final database updates in a SINGLE transaction
                # This consolidates multiple updates into one database session with minimal operations
                db_update = next(get_db())
                try:
                    # Use batch update to perform all database changes in one transaction
                    # This significantly reduces roundtrips for global deployments
                    updates = [
                        # Update message content
                        (
                            "UPDATE messages SET content = :content WHERE id = :id",
                            {"content": accumulated_content, "id": ai_message_id}
                        ),
                        # Update conversation timestamp
                        (
                            "UPDATE conversations SET last_chatted_with = NOW() WHERE id = :id",
                            {"id": conversation_id}
                        ),
                        # Deduct user credit (atomic operation)
                        (
                            "UPDATE users SET credits = credits - 1 WHERE id = :id AND credits >= 1",
                            {"id": user_id}
                        ),
                        # Increment character creator's message counter (atomic operation)
                        (
                            "UPDATE users SET character_messages_received = character_messages_received + 1 WHERE id = :id",
                            {"id": character_creator_id}
                        )
                    ]
                    
                    # Execute all updates in one transaction
                    batch_update(db_update, updates)
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