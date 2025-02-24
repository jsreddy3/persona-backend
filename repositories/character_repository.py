from sqlalchemy.orm import Session
from sqlalchemy import desc, func
from typing import List, Optional, Dict, Any
from .base import BaseRepository
from database.models import Character, User

class CharacterRepository(BaseRepository[Character]):
    def __init__(self, db: Session):
        super().__init__(Character, db)
    
    def get_by_popularity(self, skip: int = 0, limit: int = 10) -> List[Character]:
        return self.db.query(Character)\
            .order_by(desc(Character.num_messages))\
            .offset(skip)\
            .limit(limit)\
            .all()
    
    def get_by_creator(self, creator_id: int) -> List[Character]:
        return self.db.query(Character)\
            .filter(Character.creator_id == creator_id)\
            .all()
    
    def get_character_stats(self, character_id: int):
        character = self.get_by_id(character_id)
        if not character:
            return None
        
        return {
            "id": character.id,
            "name": character.name,
            "num_chats": character.num_chats_created,
            "num_messages": character.num_messages,
            "rating": character.rating
        }
    
    def update_stats(self, character_id: int, *, 
                    increment_chats: bool = False,
                    increment_messages: bool = False):
        character = self.get_by_id(character_id)
        if not character:
            return None
        
        if increment_chats:
            character.num_chats_created += 1
        if increment_messages:
            character.num_messages += 1
            
        self.db.commit()
        self.db.refresh(character)
        return character

    def search(self, query: str, skip: int = 0, limit: int = 10) -> List[Character]:
        """Search characters by name, tagline, or description"""
        search_term = f"%{query}%"
        return (
            self.db.query(Character)
            .filter(
                # Search across multiple fields
                (Character.name.ilike(search_term)) |
                (Character.tagline.ilike(search_term)) |
                (Character.character_description.ilike(search_term))
            )
            .order_by(desc(Character.num_messages))  # Order by popularity
            .offset(skip)
            .limit(limit)
            .all()
        )
