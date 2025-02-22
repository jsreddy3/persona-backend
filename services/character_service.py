from typing import List, Optional
from sqlalchemy.orm import Session
from repositories.character_repository import CharacterRepository
from database.models import Character

class CharacterService:
    def __init__(self, db: Session):
        self.repository = CharacterRepository(db)
    
    def create_character(
        self,
        name: str,
        character_description: str,
        greeting: str,
        creator_id: int,
        tagline: Optional[str] = None,
        photo_url: Optional[str] = None,
        attributes: List[str] = []
    ) -> Character:
        """Create a new character"""
        character_data = {
            "name": name,
            "character_description": character_description,
            "greeting": greeting,
            "tagline": tagline,
            "photo_url": photo_url,
            "creator_id": creator_id,
            "num_chats_created": 0,
            "num_messages": 0,
            "rating": 0.0,
            "attributes": attributes
        }
        
        return self.repository.create(character_data)
    
    def get_popular_characters(self, page: int = 1, per_page: int = 10) -> List[Character]:
        """Get popular characters ordered by number of messages"""
        skip = (page - 1) * per_page
        return self.repository.get_by_popularity(skip=skip, limit=per_page)
    
    def get_character(self, character_id: int) -> Optional[Character]:
        """Get character details by ID"""
        return self.repository.get_by_id(character_id)
    
    def get_creator_characters(self, creator_id: int) -> List[Character]:
        """Get all characters created by a user"""
        return self.repository.get_by_creator(creator_id)
    
    def get_stats(self, character_id: int) -> Optional[dict]:
        """Get character statistics"""
        return self.repository.get_character_stats(character_id)
    
    def update_character_image(self, character_id: int, photo_url: str) -> Optional[Character]:
        """Update a character's photo URL"""
        character = self.repository.get_by_id(character_id)
        if not character:
            return None
            
        return self.repository.update(character_id, {"photo_url": photo_url})
