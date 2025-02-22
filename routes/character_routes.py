from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel
from database.database import get_db
from database.models import User
from services.character_service import CharacterService
from dependencies.auth import get_current_user
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/characters", tags=["characters"])

class CharacterCreate(BaseModel):
    name: str
    system_prompt: str
    greeting: str  # Character's initial greeting message
    tagline: Optional[str] = None
    photo_url: Optional[str] = None
    attributes: List[str] = []

class CharacterResponse(BaseModel):
    id: int
    name: str
    greeting: str  # Character's initial greeting message
    tagline: str
    photo_url: str
    num_chats_created: int
    num_messages: int
    rating: float
    attributes: List[str]
    
    class Config:
        from_attributes = True

@router.post("/", response_model=CharacterResponse)
async def create_character(
    character: CharacterCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create a new character"""
    try:
        service = CharacterService(db)
        char = service.create_character(
            name=character.name,
            system_prompt=character.system_prompt,
            greeting=character.greeting,
            tagline=character.tagline,
            photo_url=character.photo_url,
            attributes=character.attributes,
            creator_id=current_user.id
        )
        return char
    except Exception as e:
        logger.error(f"Error creating character: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/popular", response_model=List[CharacterResponse])
async def get_popular_characters(
    page: int = 1,
    per_page: int = 10,
    db: Session = Depends(get_db)
):
    """Get popular characters"""
    try:
        service = CharacterService(db)
        characters = service.get_popular_characters(page=page, per_page=per_page)
        return characters
    except Exception as e:
        logger.error(f"Error getting popular characters: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{character_id}", response_model=CharacterResponse)
async def get_character(
    character_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get a character by ID"""
    try:
        service = CharacterService(db)
        character = service.get_character_details(character_id)  
        if not character:
            raise HTTPException(status_code=404, detail="Character not found")
        return character
    except Exception as e:
        logger.error(f"Error getting character: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{character_id}/stats")
async def get_character_stats(
    character_id: int,
    db: Session = Depends(get_db)
):
    """Get character stats"""
    try:
        service = CharacterService(db)
        stats = service.get_character_stats(character_id)
        return stats
    except Exception as e:
        logger.error(f"Error getting character stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))
