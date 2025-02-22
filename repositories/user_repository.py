from sqlalchemy.orm import Session
from sqlalchemy import update
from typing import Optional
from .base import BaseRepository
from database.models import User

class UserRepository(BaseRepository[User]):
    def __init__(self, db: Session):
        super().__init__(User, db)
    
    def update_credits(self, user_id: int, amount: int) -> Optional[User]:
        """
        Update user credits by adding amount (can be negative)
        Returns None if user not found or if operation would result in negative credits
        """
        user = self.get_by_id(user_id)
        if not user or user.credits + amount < 0:
            return None
            
        user.credits += amount
        self.db.commit()
        self.db.refresh(user)
        return user
    
    def get_by_email(self, email: str) -> Optional[User]:
        return self.db.query(User).filter(User.email == email).first()
    
    def get_with_characters(self, user_id: int) -> Optional[User]:
        """Get user with their created characters eagerly loaded"""
        return self.db.query(User)\
            .filter(User.id == user_id)\
            .options(joinedload(User.created_characters))\
            .first()
