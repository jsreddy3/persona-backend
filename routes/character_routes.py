from fastapi import APIRouter, Depends, HTTPException, File, UploadFile
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel
from database.database import get_db
from database.models import User
from services.character_service import CharacterService
from services.image_service import ImageService  # Comment out for now
from dependencies.auth import get_current_user
import logging

logger = logging.getLogger(__name__)

router = APIRouter(tags=["characters"])  # Remove prefix, it's added in main.py

# Print routes being registered
logger.info("Registering character routes:")
for route in router.routes:
    logger.info(f"Character route: {route.path} [{','.join(route.methods)}]")

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
    tagline: Optional[str] = ""  # Make optional with default
    photo_url: Optional[str] = ""  # Make optional with default
    num_chats_created: int = 0  # Add default
    num_messages: int = 0  # Add default
    rating: float = 0.0  # Add default
    attributes: List[str] = []  # Add default
    
    class Config:
        orm_mode = True  # Use orm_mode in v1 instead of from_attributes

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

@router.get("/list/popular", response_model=List[CharacterResponse])
async def get_popular_characters(
    db: Session = Depends(get_db)
):
    """Get list of popular characters"""
    try:
        service = CharacterService(db)
        return service.get_popular_characters()
    except Exception as e:
        logger.error(f"Error getting popular characters: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/detail/{character_id}", response_model=CharacterResponse)
async def get_character(
    character_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get character details by ID"""
    try:
        service = CharacterService(db)
        character = service.get_character(character_id)  
        if not character:
            raise HTTPException(status_code=404, detail="Character not found")
        return character
    except Exception as e:
        logger.error(f"Error getting character {character_id}: {str(e)}")
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

@router.post("/{character_id}/image")
async def upload_character_image(
    character_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Upload a character's image"""
    try:
        # Print debug info
        print(f"Received file: {file.filename}")
        
        # Read file
        contents = await file.read()
        print(f"Read {len(contents)} bytes")
        
        # Upload image
        image_service = ImageService()
        url = image_service.upload_character_image(contents, character_id)
        if not url:
            raise HTTPException(status_code=400, detail="Failed to upload image")
            
        # Update character
        service = CharacterService(db)
        character = service.update_character_image(character_id, url)
        if not character:
            raise HTTPException(status_code=400, detail="Failed to update character")
            
        return {"photo_url": url}
        
    except Exception as e:
        logger.error(f"Error uploading character image: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
