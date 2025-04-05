from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session

from database.models import Payment, User
from database.database import SessionLocal

class PaymentRepository:
    """Repository for handling Payment database operations"""
    
    @staticmethod
    def create_payment(
        user_id: int,
        reference: str,
        credits_amount: int,
        token_type: str,
        token_decimal_places: int,
        recipient_address: str
    ) -> Payment:
        """Create a new payment record"""
        db = SessionLocal()
        try:
            payment = Payment(
                reference=reference,
                user_id=user_id,
                status="pending",
                credits_amount=credits_amount,
                token_type=token_type,
                token_decimal_places=token_decimal_places,
                recipient_address=recipient_address
            )
            
            db.add(payment)
            db.commit()
            db.refresh(payment)
            
            return payment
        finally:
            db.close()
    
    @staticmethod
    def get_payment_by_reference(reference: str) -> Optional[Payment]:
        """Get payment by reference ID"""
        db = SessionLocal()
        try:
            payment = db.query(Payment).filter(
                Payment.reference == reference
            ).first()
            
            return payment
        finally:
            db.close()
    
    @staticmethod
    def update_payment_status(
        reference: str, 
        status: str, 
        transaction_details: Dict[str, Any] = None
    ) -> Optional[Payment]:
        """Update payment status and transaction details"""
        db = SessionLocal()
        try:
            payment = db.query(Payment).filter(
                Payment.reference == reference
            ).first()
            
            if not payment:
                return None
                
            # Update status
            payment.status = status
            
            # Update transaction details if provided
            if transaction_details:
                if "transaction_id" in transaction_details:
                    payment.transaction_id = transaction_details["transaction_id"]
                if "transaction_hash" in transaction_details:
                    payment.transaction_hash = transaction_details["transaction_hash"]
                if "chain" in transaction_details:
                    payment.chain = transaction_details["chain"]
                if "sender_address" in transaction_details:
                    payment.sender_address = transaction_details["sender_address"]
                if "token_amount" in transaction_details:
                    payment.token_amount = transaction_details["token_amount"]
                if "token_type" in transaction_details:
                    payment.token_type = transaction_details["token_type"]
            
            db.commit()
            db.refresh(payment)
            
            return payment
        finally:
            db.close()
    
    @staticmethod
    def add_credits_to_user(user_id: int, credits: int) -> Optional[User]:
        """Add credits to user account"""
        db = SessionLocal()
        try:
            user = db.query(User).get(user_id)
            
            if not user:
                return None
                
            user.credits += credits
            db.commit()
            db.refresh(user)
            
            return user
        finally:
            db.close()
    
    @staticmethod
    def get_user_credits(user_id: int) -> Optional[int]:
        """Get user's current credit balance"""
        db = SessionLocal()
        try:
            user = db.query(User).get(user_id)
            
            if not user:
                return None
                
            return user.credits
        finally:
            db.close()
    
    @staticmethod
    def get_user_payments(user_id: int, status: Optional[str] = None) -> List[Payment]:
        """Get all payments for a user, optionally filtered by status"""
        db = SessionLocal()
        try:
            query = db.query(Payment).filter(Payment.user_id == user_id)
            
            if status:
                query = query.filter(Payment.status == status)
                
            payments = query.order_by(Payment.created_at.desc()).all()
            
            return payments
        finally:
            db.close()
