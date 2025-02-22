from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List
from pydantic import BaseModel
from database.database import get_db
from database.models import User
from services.conversation_service import ConversationService
from dependencies.auth import get_current_user
import logging
import time
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

@router.get("/")
async def get_conversations(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get all conversations for the current user"""
    try:
        service = ConversationService(db)
        conversations = service.repository.get_by_user_id(current_user.id)
        logger.info(f"Getting all conversations for user {current_user.id}. Gotten this many: {len(conversations)}")
        return [
            {
                "id": conv.id,
                "character_id": conv.character_id,
                "created_at": conv.created_at
            }
            for conv in conversations
        ]
    except Exception as e:
        logger.error(f"Error getting conversations: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/", response_model=int)
async def create_conversation(
    conversation: ConversationCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    try:
        service = ConversationService(db)
        conv = service.create_conversation(
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