from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Optional
import os
import secrets
import httpx
from datetime import datetime
from pydantic import BaseModel

from database.models import User, Payment
from database.database import get_db
from dependencies.auth import get_current_user

router = APIRouter(tags=["payments"])  # Remove prefix, it's added in main.py

class PaymentInitResponse(BaseModel):
    reference: str
    recipient: str
    amount: int  # Amount in credits

class PaymentConfirmRequest(BaseModel):
    reference: str
    payload: dict  # World ID transaction payload

@router.post("/initiate", response_model=PaymentInitResponse)
async def initiate_payment(
    credits: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Initialize a payment for message credits"""
    if credits < 1:
        raise HTTPException(status_code=400, detail="Must purchase at least 1 credit")
        
    # Generate unique reference
    reference = secrets.token_hex(16)
    
    # Create pending payment
    payment = Payment(
        reference=reference,
        user_id=current_user.id,
        status="pending",
        amount=credits
    )
    db.add(payment)
    db.commit()
    
    # Return payment details
    return PaymentInitResponse(
        reference=reference,
        recipient=os.getenv("PAYMENT_RECIPIENT_ADDRESS"),
        amount=credits * int(os.getenv("CREDITS_PRICE", "1"))  # Price per credit
    )

@router.post("/confirm")
async def confirm_payment(
    request: PaymentConfirmRequest,
    db: Session = Depends(get_db)
):
    """Confirm a payment using World ID API"""
    # Get payment
    payment = db.query(Payment).filter(
        Payment.reference == request.reference
    ).first()
    
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")
        
    if payment.status == "confirmed":
        raise HTTPException(status_code=400, detail="Payment already confirmed")
    
    try:
        # Verify with World ID API
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"https://developer.worldcoin.org/api/v2/minikit/transaction/{request.payload['transaction_id']}",
                params={
                    "app_id": os.getenv("WORLD_ID_APP_ID"),
                    "type": "payment"
                },
                headers={
                    "Authorization": f"Bearer {os.getenv('DEV_PORTAL_API_KEY')}"
                }
            )
            
            transaction = response.json()
            
            if (transaction.get("reference") == request.reference and 
                transaction.get("transaction_status") != "failed"):
                # Update payment status
                payment.status = "confirmed"
                payment.transaction_id = request.payload["transaction_id"]
                
                # Add credits to user
                user = db.query(User).get(payment.user_id)
                user.credits += payment.amount
                
                db.commit()
                return {"success": True, "credits": user.credits}
            
            payment.status = "failed"
            db.commit()
            raise HTTPException(status_code=400, detail="Payment verification failed")
            
    except Exception as e:
        payment.status = "failed"
        db.commit()
        raise HTTPException(status_code=500, detail=str(e))
