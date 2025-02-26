from typing import List, Optional
from sqlalchemy.orm import Session
from repositories.character_repository import CharacterRepository
from database.models import Character
import logging

logger = logging.getLogger(__name__)

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
        attributes: List[str] = [],
        language: str = "en"
    ) -> Character:
        """Create a new character"""
        logger.info(f"Creating character '{name}' with language: {language}")
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
            "attributes": attributes,
            "language": language
        }
        
        return self.repository.create(character_data)
    
    def get_popular_characters(self, page: int = 1, per_page: int = 10, language: str = "en") -> List[Character]:
        """Get popular characters ordered by number of messages"""
        # logger.info(f"Getting popular characters for language: {language}")
        skip = (page - 1) * per_page
        characters = self.repository.get_by_popularity(skip=skip, limit=per_page, language=language)
        # logger.info(f"Found {len(characters)} popular characters for language {language}")
        return characters
    
    def get_character(self, character_id: int, language: str = "en") -> Optional[Character]:
        """Get character details by ID"""
        # logger.info(f"Getting character with ID {character_id} for language: {language}")
        character = self.repository.get_by_id(character_id)
        if character and character.language == language:
            # logger.info(f"Found character with ID {character_id} for language {language}")
        return character
    
    def get_creator_characters(self, creator_id: int, language: str = "en") -> List[Character]:
        """Get all characters created by a user"""
        # logger.info(f"Getting characters created by user {creator_id} for language: {language}")
        characters = self.repository.get_by_creator(creator_id, language=language)
        # logger.info(f"Found {len(characters)} characters created by user {creator_id} for language {language}")
        return characters
    
    def get_stats(self, character_id: int, language: str = "en") -> Optional[dict]:
        """Get character statistics"""
        # logger.info(f"Getting statistics for character with ID {character_id} for language: {language}")
        stats = self.repository.get_character_stats(character_id)
        # if stats:
        #     logger.info(f"Found statistics for character with ID {character_id} for language {language}")
        return stats
    
    def update_character_image(self, character_id: int, photo_url: str, language: str = "en") -> Optional[Character]:
        """Update a character's photo URL"""
        # logger.info(f"Updating character with ID {character_id} for language: {language}")
        character = self.repository.get_by_id(character_id)
        if not character:
            return None
            
        return self.repository.update(character_id, {"photo_url": photo_url})

    def search_characters(self, query: str, page: int = 1, per_page: int = 10, language: str = "en") -> List[Character]:
        """Search characters by name, tagline, or description"""
        # logger.info(f"Searching characters for query '{query}' and language: {language}")
        skip = (page - 1) * per_page
        characters = self.repository.search(query, skip=skip, limit=per_page, language=language)
        # logger.info(f"Found {len(characters)} characters for query '{query}' and language {language}")
        return characters
