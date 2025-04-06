from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session

from database.models import TokenRedemption, User
from database.database import SessionLocal

class TokenRedemptionRepository:
    """Repository for handling TokenRedemption database operations"""
    
    @staticmethod
    def create_redemption(
        user_id: int,
        amount: int,
        signature: str,
        nonce: str
    ) -> TokenRedemption:
        """Create a new token redemption record"""
        db = SessionLocal()
        try:
            redemption = TokenRedemption(
                user_id=user_id,
                amount=amount,
                signature=signature,
                nonce=nonce,
                status="pending"
            )
            
            db.add(redemption)
            db.commit()
            db.refresh(redemption)
            
            return redemption
        finally:
            db.close()
    
    @staticmethod
    def update_redemption_status(
        redemption_id: int, 
        status: str, 
        transaction_hash: str = None
    ) -> Optional[TokenRedemption]:
        """Update redemption status and transaction hash if provided"""
        db = SessionLocal()
        try:
            redemption = db.query(TokenRedemption).get(redemption_id)
            
            if not redemption:
                return None
                
            # Update status
            redemption.status = status
            
            # Update transaction hash if provided
            if transaction_hash:
                redemption.transaction_hash = transaction_hash
            
            db.commit()
            db.refresh(redemption)
            
            return redemption
        finally:
            db.close()
    
    @staticmethod
    def get_user_redemptions(user_id: int, status: Optional[str] = None) -> List[TokenRedemption]:
        """Get all redemptions for a user, optionally filtered by status"""
        db = SessionLocal()
        try:
            query = db.query(TokenRedemption).filter(TokenRedemption.user_id == user_id)
            
            if status:
                query = query.filter(TokenRedemption.status == status)
                
            redemptions = query.order_by(TokenRedemption.created_at.desc()).all()
            
            return redemptions
        finally:
            db.close()
    
    @staticmethod
    def get_total_tokens_redeemed(user_id: int) -> int:
        """Get total tokens redeemed by user"""
        db = SessionLocal()
        try:
            user = db.query(User).get(user_id)
            
            if not user:
                return 0
                
            return user.tokens_redeemed
        finally:
            db.close()
    
    @staticmethod
    def update_user_tokens_redeemed(user_id: int, amount: int) -> Optional[User]:
        """Update the tokens_redeemed field for a user"""
        db = SessionLocal()
        try:
            user = db.query(User).get(user_id)
            
            if not user:
                return None
                
            user.tokens_redeemed += amount
            db.commit()
            db.refresh(user)
            
            return user
        finally:
            db.close()
    
    @staticmethod
    def get_pending_redemptions() -> List[TokenRedemption]:
        """Get all pending redemptions"""
        db = SessionLocal()
        try:
            redemptions = db.query(TokenRedemption).filter(
                TokenRedemption.status == "pending"
            ).all()
            
            return redemptions
        finally:
            db.close()
