from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from typing import Optional
from pydantic import BaseModel, Field
from datetime import datetime
import json
import logging
import re
from database.database import get_db, SessionLocal
from database.models import User, WorldIDVerification
from repositories.user_repository import UserRepository
from services.user_service import UserService
from services.world_id_service import WorldIDService
from services.siwe_service import SIWEService
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
    id: int
    wallet_address: Optional[str]
    world_id: Optional[str]  # Now optional since users can authenticate with just wallet
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
    """
    Verify World ID credentials from header and check stored verifications
    
    Optimized for performance with short-lived connections and error handling
    """    
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
        
        # Use a short-lived database connection
        conn_db = next(get_db())
        try:
            # Check for existing verification with an efficient query
            verification = conn_db.query(WorldIDVerification).filter(
                WorldIDVerification.nullifier_hash == parsed_creds.nullifier_hash
            ).first()
            
            if not verification:
                logger.error(f"No verification found for nullifier_hash: {parsed_creds.nullifier_hash}")
                return None
            
            # Import the increment_counter utility for atomic update
            from database.db_utils import update_with_lock
            
            # Update user's last_active timestamp using row-level locking
            user = conn_db.query(User).filter(
                User.world_id == parsed_creds.nullifier_hash
            ).first()
            
            if user:
                # Define update function for atomic update
                def update_last_active(user_obj):
                    user_obj.last_active = datetime.now()
                
                # Use row-level locking to prevent conflicts
                update_with_lock(conn_db, User, user.id, update_last_active)
                
                # Commit the transaction
                conn_db.commit()
            
            return parsed_creds
        except Exception as db_error:
            conn_db.rollback()
            logger.error(f"Database error during credential verification: {str(db_error)}")
            logger.exception("Full traceback:")
            return None
        finally:
            # Ensure connection is closed
            conn_db.close()
            
    except json.JSONDecodeError:
        logger.error(f"Invalid JSON in X-WorldID-Credentials header: {credentials}")
        return None
    except KeyError as key_error:
        logger.error(f"Missing key in credentials: {str(key_error)}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error verifying credentials: {str(e)}")
        logger.exception("Full traceback:")
        return None

async def verify_wallet_address(
    request: Request,
    db: Session = Depends(get_db)
) -> Optional[str]:
    """Verify wallet address from header and check if it's linked to a user"""
    logger.info("Verifying wallet address from header")
    
    wallet_address = request.headers.get('X-Wallet-Address')
    if not wallet_address:
        logger.info("No wallet address found in header")
        return None
    
    try:
        # Validate wallet address format
        if not Web3.is_address(wallet_address):
            logger.error(f"Invalid wallet address format: {wallet_address}")
            return None
            
        # Convert to checksum address
        wallet_address = Web3.to_checksum_address(wallet_address)
        
        # Check if wallet address is linked to a user
        user = db.query(User).filter(
            User.wallet_address == wallet_address
        ).first()
        
        if user:
            user.last_active = datetime.utcnow()
            db.commit()
            return wallet_address
        else:
            logger.error(f"No user found with wallet address: {wallet_address}")
            return None
            
    except Exception as e:
        logger.error(f"Error verifying wallet address: {str(e)}")
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
async def purchase_credits(
    user_id: int,
    purchase: CreditPurchase,
    current_user: User = Depends(get_current_user)
):
    """
    Purchase credits for a user
    
    Optimized for global distribution with atomic updates to prevent conflicts
    """
    try:
        # Verify the user is updating their own account
        if current_user.id != user_id:
            raise HTTPException(status_code=403, detail="Can only purchase credits for your own account")
            
        # Use a short-lived database connection
        db = next(get_db())
        try:
            # Map package to credit amount
            credit_packages = {
                "small": 10,
                "medium": 50,
                "large": 100,
            }
            
            amount = credit_packages.get(purchase.package)
            if not amount:
                raise ValueError(f"Invalid package: {purchase.package}")
            
            # Use update_with_lock to safely update with row-level locking
            from database.db_utils import update_with_lock
            
            def add_credits(user):
                user.credits += amount
                user.last_purchase_date = datetime.now()
                # Track any additional analytics needed
                if not user.total_purchased:
                    user.total_purchased = amount
                else:
                    user.total_purchased += amount
            
            updated_user = update_with_lock(db, User, user_id, add_credits)
            
            if not updated_user:
                raise HTTPException(status_code=404, detail="User not found")
                
            # Commit the transaction
            db.commit()
            
            return {"credits": updated_user.credits}
            
        except ValueError as e:
            db.rollback()
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            db.rollback()
            raise e
        finally:
            # Ensure connection is closed
            db.close()
    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        logger.error(f"Error purchasing credits: {str(e)}")
        logger.exception("Full traceback:")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/verify", response_model=dict)
async def verify_world_id(
    request: VerifyRequest,
    req: Request
):
    """
    Verify a World ID proof and create/update user
    
    Note: This route is being maintained for backward compatibility
    but will be deprecated in favor of the wallet-based auth
    """
    # Following optimized DB connection pattern
    db = SessionLocal()
    try:
        # Get language from Accept-Language header
        accept_language = req.headers.get("accept-language", "en")
        language = parse_accept_language(accept_language)
        logger.info(f"Using language from header: {language}")
        
        user_repo = UserRepository(db)
        world_id_service = WorldIDService(user_repo)
        
        result = await world_id_service.verify_proof(
            nullifier_hash=request.nullifier_hash,
            merkle_root=request.merkle_root,
            proof=request.proof,
            verification_level=request.verification_level,
            action=request.action,
            language=language
        )
        
        # Create session token after successful verification
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
    finally:
        db.close()

@router.get("/me", response_model=UserResponse)
async def get_current_user_info(
    current_user: User = Depends(get_current_user)
):
    """Get the current user's information"""
    # Convert the SQLAlchemy model to a dict for the Pydantic model
    return {
        "id": current_user.id,
        "wallet_address": current_user.wallet_address,
        "world_id": current_user.world_id,
        "username": current_user.username or "User",  # Provide default if null
        "language": current_user.language or "en",    # Provide default if null
        "credits": current_user.credits or 0          # Provide default if null
    }

@router.get("/stats", response_model=dict)
async def get_user_stats(
    current_user: User = Depends(get_current_user)
):
    """
    Get user stats
    
    Optimized for performance with denormalized counters and minimal database access
    """
    try:
        # Use a short-lived database connection
        db = next(get_db())
        try:
            # Use a single efficient query to get the latest user data
            # This ensures we get the most up-to-date counter values
            user = db.query(User).filter(User.id == current_user.id).with_for_update(skip_locked=True).first()
            
            if not user:
                raise HTTPException(status_code=404, detail="User not found")
            
            # Count characters separately since this could be a large collection
            # and we want to avoid loading all objects into memory
            character_count = db.query(User.id).join(
                User.created_characters
            ).filter(User.id == current_user.id).count()
            
            # Build response using denormalized counters for O(1) performance
            stats = {
                "credits_used": user.credits_spent or 0,
                "messages_sent": user.character_messages_received or 0,  # Using the correct field
                "characters": character_count,
                "username": user.username,
                "character_messages_received": user.character_messages_received or 0,
                "tokens_redeemed": user.tokens_redeemed or 0
            }
            
            # Commit transaction
            db.commit()
            
            return stats
        except Exception as e:
            db.rollback()
            raise e
        finally:
            # Ensure connection is closed
            db.close()
    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        logger.error(f"Error getting user stats: {str(e)}")
        logger.exception("Full traceback:")
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/update", response_model=UserResponse)
async def update_user(
    user_update: UserUpdate,
    current_user: User = Depends(get_current_user)
):
    """
    Update user profile
    
    Optimized for global distribution with row-level locking to prevent conflicts
    """
    try:
        # Validate wallet address outside DB transaction
        wallet_address = user_update.wallet_address
        if wallet_address:
            if not Web3.is_address(wallet_address):
                raise HTTPException(status_code=400, detail="Invalid Ethereum address")
            # Convert to checksum address
            wallet_address = Web3.to_checksum_address(wallet_address)
            user_update.wallet_address = wallet_address
        
        # Use a short-lived database connection for validation
        db_validate = next(get_db())
        try:
            # Check if wallet is already linked to another account
            if wallet_address:
                existing_user = db_validate.query(User).filter(
                    User.wallet_address == wallet_address,
                    User.id != current_user.id
                ).first()
                
                if existing_user:
                    raise HTTPException(
                        status_code=409, 
                        detail="This wallet is already linked to another account"
                    )
        finally:
            db_validate.close()
        
        # Use a separate connection for the actual update
        from database.db_utils import update_with_lock
        
        db_update = next(get_db())
        try:
            # Extract only the non-null update values
            update_values = {k: v for k, v in user_update.dict().items() if v is not None}
            
            if not update_values:
                # No changes to make
                return {
                    "id": current_user.id,
                    "wallet_address": current_user.wallet_address,
                    "world_id": current_user.world_id,
                    "username": current_user.username or "User",
                    "language": current_user.language or "en",
                    "credits": current_user.credits or 0
                }
            
            # Define update function for update_with_lock
            def update_user_profile(user):
                for key, value in update_values.items():
                    setattr(user, key, value)
                user.updated_at = datetime.now()
            
            # Use row-level locking to prevent conflicts
            updated_user = update_with_lock(db_update, User, current_user.id, update_user_profile)
            
            if not updated_user:
                raise HTTPException(status_code=404, detail="User not found")
                
            # Commit the transaction
            db_update.commit()
            
            # Return response model
            return {
                "id": updated_user.id,
                "wallet_address": updated_user.wallet_address,
                "world_id": updated_user.world_id,
                "username": updated_user.username or "User", 
                "language": updated_user.language or "en",
                "credits": updated_user.credits or 0
            }
        except Exception as update_error:
            db_update.rollback()
            raise update_error
        finally:
            db_update.close()
            
    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        logger.error(f"Error updating user: {str(e)}")
        logger.exception("Full traceback:")
        raise HTTPException(status_code=500, detail=str(e))
