from fastapi import APIRouter, Depends, HTTPException
from typing import Optional, List, Dict, Any
from pydantic import BaseModel

from database.models import User
from dependencies.auth import get_current_user
from services.payment_service import PaymentService, SUPPORTED_TOKENS

router = APIRouter(tags=["payments"])  # Remove prefix, it's added in main.py

class TokenAmount(BaseModel):
    token_type: str
    human_readable_amount: float
    raw_amount: str

class PaymentInitResponse(BaseModel):
    reference: str
    recipient: str
    credits_amount: int
    token_type: str
    token_amounts: Dict[str, TokenAmount] = None

class PaymentConfirmRequest(BaseModel):
    reference: str
    payload: dict  # World ID transaction payload

class PaymentStatusResponse(BaseModel):
    success: bool
    status: str
    credits: Optional[int] = None
    reference: str

class PaymentHistoryResponse(BaseModel):
    payments: List[Dict[str, Any]]

@router.get("/tokens")
async def get_supported_tokens():
    """Get list of supported tokens for payment"""
    return {"tokens": SUPPORTED_TOKENS}

@router.get("/price")
async def get_token_prices(
    tokens: Optional[List[str]] = None,
    currencies: Optional[List[str]] = ["USD"]
):
    """Get current prices for tokens in specified currencies"""
    if not tokens:
        tokens = SUPPORTED_TOKENS
        
    # Validate tokens
    for token in tokens:
        if token not in SUPPORTED_TOKENS:
            raise HTTPException(status_code=400, detail=f"Unsupported token: {token}")
    
    try:
        prices = await PaymentService.get_token_prices(tokens, currencies)
        return prices
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/calculate")
async def calculate_payment(
    credits: int,
    token_type: str = "WLD"
):
    """Calculate token amount needed for purchasing credits"""
    if token_type not in SUPPORTED_TOKENS:
        raise HTTPException(status_code=400, detail=f"Unsupported token: {token_type}")
        
    if credits < 1:
        raise HTTPException(status_code=400, detail="Must purchase at least 1 credit")
        
    try:
        human_readable_amount, raw_amount = await PaymentService.calculate_token_amount(credits, token_type)
        
        return {
            "credits": credits,
            "token_type": token_type,
            "amount": human_readable_amount,
            "raw_amount": str(raw_amount)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/initiate", response_model=PaymentInitResponse)
async def initiate_payment(
    credits: int,
    token_type: str = "WLD",
    current_user: User = Depends(get_current_user)
):
    """Initialize a payment for message credits"""
    if token_type not in SUPPORTED_TOKENS:
        raise HTTPException(status_code=400, detail=f"Unsupported token: {token_type}")
        
    if credits < 1:
        raise HTTPException(status_code=400, detail="Must purchase at least 1 credit")
        
    try:
        # Initialize payment
        payment_details = PaymentService.initiate_payment(
            user_id=current_user.id,
            credits=credits,
            token_type=token_type
        )
        
        # If we need token amounts for multiple tokens, calculate them
        token_amounts = {}
        if token_type in SUPPORTED_TOKENS:
            human_readable_amount, raw_amount = await PaymentService.calculate_token_amount(credits, token_type)
            token_amounts[token_type] = TokenAmount(
                token_type=token_type,
                human_readable_amount=human_readable_amount,
                raw_amount=str(raw_amount)
            )
        
        # Return payment details
        return PaymentInitResponse(
            reference=payment_details["reference"],
            recipient=payment_details["recipient"],
            credits_amount=credits,
            token_type=token_type,
            token_amounts=token_amounts
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/confirm", response_model=PaymentStatusResponse)
async def confirm_payment(
    request: PaymentConfirmRequest
):
    """Confirm a payment using World ID API"""
    try:
        result = await PaymentService.verify_transaction(
            reference=request.reference,
            transaction_payload=request.payload
        )
        
        # Convert to proper response model
        response = PaymentStatusResponse(
            success=result.get("success", False),
            status=result.get("status", "unknown"),
            reference=request.reference
        )
        
        # Add credits if available
        if "credits" in result:
            response.credits = result["credits"]
            
        return response
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/status/{reference}", response_model=PaymentStatusResponse)
async def get_payment_status(
    reference: str
):
    """Get the current status of a payment"""
    try:
        result = await PaymentService.get_transaction_status(reference)
        
        # Convert to proper response model
        response = PaymentStatusResponse(
            success=result.get("success", False),
            status=result.get("status", "unknown"),
            reference=reference
        )
        
        # Add credits if available
        if "credits" in result:
            response.credits = result["credits"]
            
        return response
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/history", response_model=PaymentHistoryResponse)
async def get_payment_history(
    status: Optional[str] = None,
    current_user: User = Depends(get_current_user)
):
    """Get payment history for the current user"""
    try:
        payments = PaymentService.get_user_payments(
            user_id=current_user.id,
            status=status
        )
        
        return {"payments": payments}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
