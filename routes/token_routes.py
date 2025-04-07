from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, Dict, Any
from database.models import User
from database.database import get_db
from dependencies.auth import get_current_user
from services.token_service import TokenService
import logging

logger = logging.getLogger(__name__)
router = APIRouter(tags=["tokens"])

class RedemptionResponse(BaseModel):
    redemption_id: int
    user_address: str
    amount: int
    amount_in_wei: str
    nonce: str
    signature: str
    contract_address: str

class RedemptionStatusUpdate(BaseModel):
    redemption_id: int
    status: str
    transaction_hash: Optional[str] = None

@router.get("/redeemable-tokens", response_model=Dict[str, Any])
async def get_redeemable_tokens(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get the number of tokens that a user can redeem based on chat popularity
    """
    try:
        # Initialize token service
        token_service = TokenService()
        
        # Calculate redeemable tokens
        redeemable_tokens = token_service.calculate_redeemable_tokens(current_user)
        
        # Get total earned tokens
        total_earned = current_user.character_messages_received * 10
        
        return {
            "redeemable_tokens": redeemable_tokens,
            "total_earned": total_earned,
            "already_redeemed": current_user.tokens_redeemed,
            "character_messages_received": current_user.character_messages_received
        }
    except Exception as e:
        logger.error(f"Failed to calculate redeemable tokens: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/redeem-tokens", response_model=RedemptionResponse)
async def redeem_tokens(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Redeem tokens based on chat popularity.
    This endpoint:
    1. Calculates redeemable tokens based on (character_messages_received * 10) - already_redeemed_tokens
    2. Generates a signature for minting these tokens
    3. Records the redemption in the database
    4. Returns all necessary data for the frontend to mint the tokens using MiniKit
    """
    try:
        # Validate user has a wallet address
        if not current_user.wallet_address:
            raise HTTPException(
                status_code=400,
                detail="No wallet address associated with your account. Please add a wallet address first."
            )
            
        # Initialize token service
        token_service = TokenService()
        
        # Calculate redeemable tokens
        redeemable_tokens = token_service.calculate_redeemable_tokens(current_user)
        
        # Validate user has tokens to redeem
        if redeemable_tokens <= 0:
            raise HTTPException(
                status_code=400,
                detail="You don't have any tokens to redeem at the moment."
            )
            
        # Create redemption record and get signature
        redemption_data = token_service.create_redemption(
            user_id=current_user.id,
            user_address=current_user.wallet_address,
            amount=redeemable_tokens
        )
        
        return redemption_data
    
    except Exception as e:
        logger.error(f"Failed to redeem tokens: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/update-redemption-status", response_model=Dict[str, Any])
async def update_redemption_status(
    status_update: RedemptionStatusUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Update the status of a token redemption after minting
    """
    try:
        # Initialize token service
        token_service = TokenService()
        
        # Update redemption status
        success = token_service.update_redemption_status(
            redemption_id=status_update.redemption_id,
            status=status_update.status,
            transaction_hash=status_update.transaction_hash
        )

        if not success:
            raise HTTPException(
                status_code=404,
                detail=f"Redemption with ID {status_update.redemption_id} not found"
            )
            
        return {
            "success": True,
            "status": status_update.status,
            "message": f"Redemption status updated to {status_update.status}"
        }
    
    except Exception as e:
        logger.error(f"Failed to update redemption status: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))