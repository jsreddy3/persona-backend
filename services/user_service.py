from typing import Optional, Dict, List
from sqlalchemy.orm import Session
from repositories.user_repository import UserRepository
from repositories.character_repository import CharacterRepository
from database.models import User

class UserService:
    def __init__(self, db: Session):
        self.user_repository = UserRepository(db)
        self.character_repository = CharacterRepository(db)
        
    def consume_credits(self, user_id: int, amount: int) -> Optional[User]:
        """
        Attempt to consume credits from user
        Returns None if user not found or has insufficient credits
        """
        return self.user_repository.update_credits(user_id, -amount)
    
    def add_credits(self, user_id: int, amount: int) -> Optional[User]:
        """Add credits to user account"""
        if amount <= 0:
            raise ValueError("Amount must be positive")
        return self.user_repository.update_credits(user_id, amount)
    
    def get_user_stats(self, user_id: int) -> Optional[Dict]:
        """
        Get comprehensive user statistics including:
        - Total credits
        - All characters created with their stats
        - Total messages across all characters
        - Average character rating
        """
        user = self.user_repository.get_with_characters(user_id)
        if not user:
            return None
            
        characters_stats = []
        total_messages = 0
        total_rating = 0
        
        for character in user.created_characters:
            char_stats = self.character_repository.get_character_stats(character.id)
            if char_stats:
                characters_stats.append(char_stats)
                total_messages += char_stats["num_messages"]
                total_rating += char_stats["rating"]
        
        avg_rating = total_rating / len(characters_stats) if characters_stats else 0
        
        return {
            "user_id": user.id,
            "credits_remaining": user.credits,
            "total_characters": len(characters_stats),
            "total_messages": total_messages,
            "average_character_rating": round(avg_rating, 2),
            "characters": characters_stats
        }
    
    def purchase_credits(self, user_id: int, package: str) -> Optional[User]:
        """
        Handle credit purchase (example business logic)
        In reality, this would integrate with a payment service
        """
        credit_packages = {
            "small": 100,
            "medium": 300,
            "large": 1000
        }
        
        if package not in credit_packages:
            raise ValueError("Invalid credit package")
            
        # Here you'd typically:
        # 1. Process payment
        # 2. Record transaction
        # 3. Add credits if payment successful
        
        return self.add_credits(user_id, credit_packages[package])
