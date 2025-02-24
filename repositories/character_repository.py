from sqlalchemy.orm import Session
from sqlalchemy import desc, func, or_
from typing import List, Optional, Dict, Any
from .base import BaseRepository
from database.models import Character, User

class CharacterRepository(BaseRepository[Character]):
    def __init__(self, db: Session):
        super().__init__(Character, db)
    
    def get_by_popularity(self, skip: int = 0, limit: int = 10, language: str = "en") -> List[Character]:
        """Get characters ordered by number of messages"""
        return self.db.query(Character)\
            .filter(Character.language == language)\
            .order_by(desc(Character.num_messages))\
            .offset(skip)\
            .limit(limit)\
            .all()
    
    def get_by_creator(self, creator_id: int, language: str = "en") -> List[Character]:
        """Get all characters created by a user"""
        return self.db.query(Character)\
            .filter(Character.creator_id == creator_id)\
            .filter(Character.language == language)\
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

    def search(self, query: str, skip: int = 0, limit: int = 10, language: str = "en") -> List[Character]:
        """Search characters by name or description"""
        return self.db.query(Character)\
            .filter(
                or_(
                    Character.name.ilike(f"%{query}%"),
                    Character.character_description.ilike(f"%{query}%"),
                    Character.tagline.ilike(f"%{query}%")
                )
            )\
            .filter(Character.language == language)\
            .offset(skip)\
            .limit(limit)\
            .all()
