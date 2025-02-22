from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Dict
from database.database import get_db
from services.user_service import UserService
from pydantic import BaseModel

router = APIRouter(prefix="/users", tags=["users"])

class CreditPurchase(BaseModel):
    package: str  # "small", "medium", "large"

@router.get("/{user_id}/stats")
def get_user_stats(
    user_id: int,
    db: Session = Depends(get_db)
) -> Dict:
    service = UserService(db)
    stats = service.get_user_stats(user_id)
    if not stats:
        raise HTTPException(status_code=404, detail="User not found")
    return stats

@router.post("/{user_id}/credits/purchase")
def purchase_credits(
    user_id: int,
    purchase: CreditPurchase,
    db: Session = Depends(get_db)
):
    service = UserService(db)
    try:
        user = service.purchase_credits(user_id, purchase.package)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        return {"credits": user.credits}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
