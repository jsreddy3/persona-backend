from typing import Optional, Dict, List
from sqlalchemy.orm import Session
from repositories.user_repository import UserRepository
from repositories.character_repository import CharacterRepository
from database.models import User

class UserService:
    def __init__(self, db: Session):
        self.user_repository = UserRepository(db)
        self.character_repository = CharacterRepository(db)
        self.db = db
        
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
        - Tokens redeemed and messages received (for token calculations)
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
            "tokens_redeemed": user.tokens_redeemed,
            "character_messages_received": user.character_messages_received,
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

    def update_user(self, user_id: int, update_data: dict) -> User:
        """
        Update user profile
        """
        try:
            user = self.db.query(User).filter(User.id == user_id).first()
            if not user:
                raise ValueError("User not found")
                
            # Update user fields
            for key, value in update_data.items():
                if hasattr(user, key):
                    setattr(user, key, value)
            
            self.db.commit()
            self.db.refresh(user)
            return user
            
        except Exception as e:
            self.db.rollback()
            raise e

    def get_users_by_language(self, db: Session) -> dict:
        """
        Get a breakdown of users by their language preference.
        
        Returns:
            A dictionary where keys are language codes and values are the count of users.
            Example: {'en': 120, 'es': 45, 'fr': 22, ...}
        """
        from sqlalchemy import func
        from database.models import User
        
        # Query to count users grouped by language
        result = db.query(
            User.language,
            func.count(User.id).label('user_count')
        ).group_by(
            User.language
        ).order_by(
            func.count(User.id).desc()
        ).all()
        
        # Convert the result to a dictionary
        language_counts = {lang: count for lang, count in result}
        
        return language_counts
