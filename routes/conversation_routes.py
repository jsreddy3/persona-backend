from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel
from database.database import get_db
from database.models import User
from services.conversation_service import ConversationService
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
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Send a message in a conversation and get the AI's response
    Returns both the user's message and the AI's response
    """
    try:
        service = ConversationService(db)
        user_msg, ai_msg = await service.process_user_message(
            user_id=current_user.id,
            conversation_id=conversation_id,
            message_content=message.content
        )
        return [user_msg, ai_msg]
    except ValueError as e:
        logger.error(f"Error sending message: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
    except RuntimeError as e:
        logger.error(f"Error sending message: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
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
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Stream a message in a conversation and get the AI's response token by token
    Returns a stream of SSE events containing tokens
    """
    try:
        service = ConversationService(db)
        
        async def event_generator():
            try:
                async for token in service.stream_user_message(
                    user_id=current_user.id,
                    conversation_id=conversation_id,
                    message_content=content
                ):
                    yield {
                        "event": "token",
                        "data": token
                    }
                # Send done event when streaming completes successfully
                yield {
                    "event": "done",
                    "data": ""
                }
            except ValueError as e:
                yield {
                    "event": "error",
                    "data": str(e)
                }
                
        return EventSourceResponse(event_generator())
        
    except Exception as e:
        logger.error(f"Error streaming message: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))