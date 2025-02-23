from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from database.models import User
from database.database import get_db
from dependencies.auth import get_current_user
from services.token_service import TokenService
import logging

logger = logging.getLogger(__name__)
router = APIRouter(tags=["tokens"])

class MintRequest(BaseModel):
    amount: float

@router.post("/mint", response_model=None)
async def mint_tokens(
    mint_request: MintRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Mint tokens for the current user
    Amount is in PERSONA tokens (e.g. 100 for 100 PERSONA)
    """
    try:
        # Get user's wallet address from their profile
        if not current_user.wallet_address:
            raise HTTPException(
                status_code=400,
                detail="No wallet address associated with your account. Please add a wallet address first."
            )

        # Initialize token service
        token_service = TokenService()
        
        # Mint tokens
        tx_hash = token_service.mint_tokens(
            to_address=current_user.wallet_address,
            amount=mint_request.amount
        )
        
        return {
            "status": "success",
            "transaction_hash": tx_hash,
            "amount": mint_request.amount,
            "user_address": current_user.wallet_address
        }
        
    except Exception as e:
        logger.error(f"Failed to mint tokens: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/balance", response_model=None)
async def get_balance(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get PERSONA token balance for the current user
    """
    try:
        # Get user's wallet address from their profile
        if not current_user.wallet_address:
            raise HTTPException(
                status_code=400,
                detail="No wallet address associated with your account. Please add a wallet address first."
            )

        # Initialize token service
        token_service = TokenService()
        
        # Get balance
        balance = token_service.get_balance(current_user.wallet_address)
        
        return {
            "status": "success",
            "balance": balance,
            "user_address": current_user.wallet_address
        }
        
    except Exception as e:
        logger.error(f"Failed to get token balance: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
