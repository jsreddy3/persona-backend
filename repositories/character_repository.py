from sqlalchemy.orm import Session
from sqlalchemy import desc, func, or_
from typing import List, Optional, Dict, Any
from .base import BaseRepository
from database.models import Character, User

# try to force some rest

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

    def get_grouped_by_type(self, language: str = "en", limit_per_type: int = 10) -> Dict[str, List[Character]]:
        """Get characters grouped by their primary type"""
        # All 8 character types in the system
        character_types = [
            "fictional_character", "myself", "celebrity", "regular_person", 
            "robot", "anime", "invention", "spicy"
        ]
        
        result = {}
        
        # First get all characters in the specified language
        all_characters = self.db.query(Character)\
            .filter(Character.language == language)\
            .order_by(desc(Character.num_messages))\
            .all()
        
        # Track characters that have already been assigned to a category
        assigned_character_ids = set()
            
        # Then filter them in Python by character type
        for char_type in character_types:
            chars = []
            for char in all_characters:
                # Skip if this character is already in another category
                if char.id in assigned_character_ids:
                    continue
                    
                # Check if this character type is in the list
                if char.character_types and char_type in char.character_types:
                    chars.append(char)
                    # Mark this character as assigned
                    assigned_character_ids.add(char.id)
                    
                    # Stop once we have enough characters
                    if len(chars) >= limit_per_type:
                        break
            
            # Only include types that have characters
            if chars:
                result[char_type] = chars
        
        return result
