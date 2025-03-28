from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from typing import Optional
from pydantic import BaseModel, Field
from datetime import datetime
import json
import logging
import re
from database.database import get_db
from database.models import User, WorldIDVerification
from repositories.user_repository import UserRepository
from services.user_service import UserService
from services.world_id_service import WorldIDService
from dependencies.auth import get_current_user, create_session
from web3 import Web3

logger = logging.getLogger(__name__)
router = APIRouter(tags=["users"])

class CreditPurchase(BaseModel):
    package: str  # "small", "medium", "large"

class VerifyRequest(BaseModel):
    nullifier_hash: str
    merkle_root: str
    proof: str
    verification_level: str
    action: str
    language: str = Field(default="en")

class UserResponse(BaseModel):
    world_id: str
    username: str
    language: str
    credits: int

class WorldIDCredentials(BaseModel):
    nullifier_hash: str
    merkle_root: str
    proof: str
    verification_level: str

class UserUpdate(BaseModel):
    username: Optional[str] = None
    email: Optional[str] = None
    language: Optional[str] = None
    wallet_address: Optional[str] = None

def parse_accept_language(accept_language: str) -> str:
    """
    Parse the Accept-Language header and return the best language code.
    Format can be like: 'en-US,en;q=0.9,es;q=0.8,de;q=0.7'
    Returns lowercase 2-letter language code.
    """
    if not accept_language:
        return "en"  # Default to English
    
    # Parse the header to extract languages and their quality values
    languages = []
    
    # Using regex to handle various formats of Accept-Language
    pattern = re.compile(r'([a-zA-Z]{1,8}(-[a-zA-Z0-9]{1,8})?)\s*(;\s*q\s*=\s*((1(\.0)?)|0\.\d+))?')
    
    for match in pattern.finditer(accept_language):
        lang = match.group(1)
        # If quality factor is present, use it; otherwise, assume 1.0
        q = match.group(4) or "1.0"
        languages.append((lang, float(q)))
    
    # Sort by quality factor, highest first
    languages.sort(key=lambda x: x[1], reverse=True)
    
    if not languages:
        return "en"
    
    # Get the primary language code (first two letters) from the best match
    best_lang = languages[0][0].split('-')[0].lower()
    
    logger.info(f"Parsed Accept-Language header: {accept_language} -> {best_lang}")
    return best_lang

async def verify_world_id_credentials(
    request: Request,
    db: Session = Depends(get_db)
) -> Optional[WorldIDCredentials]:
    """Verify World ID credentials from header and check stored verifications"""    
    logger.info("Verifying World ID credentials from header")
    
    credentials = request.headers.get('X-WorldID-Credentials')
    if not credentials:
        logger.info("No credentials found in header")
        return None
        
    try:
        creds = json.loads(credentials)
        logger.info(f"Received credentials for nullifier_hash: {creds['nullifier_hash']}")
        
        parsed_creds = WorldIDCredentials(
            nullifier_hash=creds["nullifier_hash"],
            merkle_root=creds["merkle_root"],
            proof=creds["proof"],
            verification_level=creds["verification_level"]
        )
        
        # Check for existing verification
        verification = db.query(WorldIDVerification).filter(
            WorldIDVerification.nullifier_hash == parsed_creds.nullifier_hash
        ).first()
        
        if not verification:
            logger.error(f"No verification found for nullifier_hash: {parsed_creds.nullifier_hash}")
            return None
        
        # logger.info(f"Found verification for nullifier_hash: {parsed_creds.nullifier_hash}")
        
        # Update user's last_active timestamp
        user = db.query(User).filter(
            User.world_id == parsed_creds.nullifier_hash
        ).first()
        
        if user:
            # logger.info(f"Updating last_active for user: {user.world_id}")
            user.last_active = datetime.utcnow()
            db.commit()
        else:
            logger.error(f"No user found with world_id: {parsed_creds.nullifier_hash}")
            
        return parsed_creds
        
    except (json.JSONDecodeError, KeyError) as e:
        logger.error(f"Error parsing credentials: {str(e)}")
        return None

@router.get("/{user_id}/stats")
def get_user_stats(
    user_id: int,
    db: Session = Depends(get_db)
) -> dict:
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

@router.post("/verify", response_model=dict)
async def verify_world_id(
    request: VerifyRequest,
    req: Request,
    db: Session = Depends(get_db)
):
    """Verify a World ID proof and create/update user"""
    try:
        # logger.info(f"Verifying request: {request}")
        user_repo = UserRepository(db)
        world_id_service = WorldIDService(user_repo)
        
        # Get language from Accept-Language header
        accept_language = req.headers.get("accept-language", "en")
        language = parse_accept_language(accept_language)
        logger.info(f"Using language from header: {language}")
        
        result = await world_id_service.verify_proof(
            nullifier_hash=request.nullifier_hash,
            merkle_root=request.merkle_root,
            proof=request.proof,
            verification_level=request.verification_level,
            action=request.action,
            language=language
        )
        
        # Create session token after successful verification
        # The user is already created/updated by WorldIDService
        session_token = create_session(result["user"]["id"], db)
        
        # Return both the verification result and session token
        return {
            **result,
            "session_token": session_token
        }
        
    except ValueError as e:
        logger.error(f"Verification error: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/me", response_model=UserResponse)
async def get_current_user_info(
    current_user: User = Depends(get_current_user)
):
    """Get the current user's information"""
    if not current_user:
        raise HTTPException(status_code=401, detail="Not authenticated")
        
    return UserResponse(
        world_id=current_user.world_id,
        username=current_user.username or "Anonymous User",
        language=current_user.language,
        credits=current_user.credits
    )

@router.get("/stats")
async def get_user_stats(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get user stats"""
    try:
        # Get total conversations (created + participated)
        total_conversations = len(set(current_user.created_conversations + current_user.participated_conversations))
        
        return {
            "credits": current_user.credits,
            "conversations": total_conversations,
            "characters": len(current_user.created_characters),
            "username": current_user.username
        }
    except Exception as e:
        logger.error(f"Error getting user stats: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/update", response_model=UserResponse)
async def update_user(
    user_update: UserUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Update user profile"""
    try:
        # Validate wallet address if provided
        if user_update.wallet_address:
            if not Web3.is_address(user_update.wallet_address):
                raise HTTPException(status_code=400, detail="Invalid Ethereum address")
            # Convert to checksum address
            user_update.wallet_address = Web3.to_checksum_address(user_update.wallet_address)
            
        service = UserService(db)
        updated_user = service.update_user(
            current_user.id,
            user_update.dict(exclude_unset=True)
        )
        return updated_user
    except Exception as e:
        logger.error(f"Error updating user: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
