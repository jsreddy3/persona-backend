from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from database.database import get_db
from services.character_service import CharacterService
from pydantic import BaseModel

router = APIRouter(prefix="/characters", tags=["characters"])

class CharacterCreate(BaseModel):
    name: str
    system_prompt: str
    greeting: str  # Character's initial greeting message
    tagline: str
    photo_url: str
    attributes: List[str]

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
def create_character(
    character: CharacterCreate,
    db: Session = Depends(get_db),
    # In real app, get user_id from auth token
    user_id: int = 1
):
    service = CharacterService(db)
    return service.create_character(user_id, character.model_dump())

@router.get("/popular", response_model=List[CharacterResponse])
def get_popular_characters(
    page: int = 1,
    per_page: int = 10,
    db: Session = Depends(get_db)
):
    service = CharacterService(db)
    return service.get_popular_characters(page, per_page)

@router.get("/{character_id}", response_model=CharacterResponse)
def get_character(character_id: int, db: Session = Depends(get_db)):
    service = CharacterService(db)
    character = service.get_character_details(character_id)
    if not character:
        raise HTTPException(status_code=404, detail="Character not found")
    return character

@router.get("/{character_id}/stats")
def get_character_stats(character_id: int, db: Session = Depends(get_db)):
    service = CharacterService(db)
    stats = service.get_stats(character_id)
    if not stats:
        raise HTTPException(status_code=404, detail="Character not found")
    return stats
