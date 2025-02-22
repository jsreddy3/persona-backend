from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session
from typing import Optional
from pydantic import BaseModel
from datetime import datetime
import json
import logging
from database.database import get_db
from database.models import User, WorldIDVerification

logger = logging.getLogger(__name__)

class WorldIDCredentials(BaseModel):
    nullifier_hash: str
    merkle_root: str
    proof: str
    verification_level: str

async def get_current_user(
    request: Request,
    db: Session = Depends(get_db)
) -> User:
    """Verify World ID credentials and return current user"""    
    logger.info("Verifying World ID credentials")
    
    credentials = request.headers.get('X-WorldID-Credentials')
    if not credentials:
        raise HTTPException(status_code=401, detail="No World ID credentials found")
        
    try:
        creds = json.loads(credentials)
        
        # Check for existing verification
        verification = db.query(WorldIDVerification).filter(
            WorldIDVerification.nullifier_hash == creds["nullifier_hash"]
        ).first()
        
        if not verification:
            raise HTTPException(status_code=401, detail="Invalid World ID verification")
        
        # Get and update user
        user = db.query(User).filter(
            User.world_id == creds["nullifier_hash"]
        ).first()
        
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
            
        user.last_active = datetime.utcnow()
        db.commit()
            
        return user
        
    except (json.JSONDecodeError, KeyError) as e:
        logger.error(f"Error parsing credentials: {str(e)}")
        raise HTTPException(status_code=400, detail="Invalid credential format")
