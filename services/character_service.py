from typing import List, Optional
from sqlalchemy.orm import Session
from repositories.character_repository import CharacterRepository
from database.models import Character

class CharacterService:
    def __init__(self, db: Session):
        self.repository = CharacterRepository(db)
    
    def create_character(self, creator_id: int, character_data: dict) -> Character:
        # Add creator_id to character data
        character_data["creator_id"] = creator_id
        return self.repository.create(character_data)
    
    def get_popular_characters(self, page: int = 1, per_page: int = 10) -> List[Character]:
        skip = (page - 1) * per_page
        return self.repository.get_by_popularity(skip=skip, limit=per_page)
    
    def get_character_details(self, character_id: int) -> Optional[Character]:
        return self.repository.get_by_id(character_id)
    
    def get_creator_characters(self, creator_id: int) -> List[Character]:
        return self.repository.get_by_creator(creator_id)
    
    def get_stats(self, character_id: int) -> Optional[dict]:
        return self.repository.get_character_stats(character_id)
