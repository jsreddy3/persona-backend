from fastapi import Depends, HTTPException, Request, Cookie, Query
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from typing import Optional
from pydantic import BaseModel
from datetime import datetime, timedelta
import json
import logging
from database.database import get_db, SessionLocal
from database.models import User, WorldIDVerification, Session as DbSession
from web3 import Web3
import secrets

logger = logging.getLogger(__name__)

class WorldIDCredentials(BaseModel):
    nullifier_hash: str
    merkle_root: str
    proof: str
    verification_level: str

def create_session(user_id: int, db: Session) -> str:
    """Create a new session token for a user"""
    # Invalidate old sessions
    db.query(DbSession).filter(
        DbSession.user_id == user_id,
    ).delete()
    
    # Create new session
    token = secrets.token_urlsafe(32)
    session = DbSession(
        token=token,
        user_id=user_id,
        expires=datetime.utcnow() + timedelta(days=1)
    )
    db.add(session)
    db.commit()
    
    return token

def get_session(token: str, db: Session) -> Optional[DbSession]:
    """Get session if token is valid"""
    session = db.query(DbSession).filter(
        DbSession.token == token,
        DbSession.expires > datetime.utcnow()
    ).first()
    
    if not session:
        return None
        
    return session

# Use auto_error=False to handle the error ourselves
security = HTTPBearer(auto_error=False)

async def get_current_user(
    request: Request = None,
    session_token: str = Cookie(None),
    session_token_query: str = Query(None, alias="session_token"),
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
) -> User:
    """
    Get current user from either:
    1. Session token in Authorization header
    2. Session token in cookie or query param
    3. Wallet address in X-Wallet-Address header
    4. World ID credentials in X-WorldID-Credentials header (legacy)
    """
    logger.info("Auth headers: %s", dict(request.headers) if request else {})
    
    # First try session token
    token = session_token or session_token_query
    if token:
        session = get_session(token, db)
        
        if session:
            logger.info(f"Found valid session for user {session.user_id}")
            # Get user from database
            user = session.user
            if user:
                # Update last active
                user.last_active = datetime.utcnow()
                db.commit()
                return user
            else:
                logger.error(f"No user found for session user_id {session.user_id}")
        else:
            logger.info("No valid session token provided")
    
    if credentials:
        token = credentials.credentials
        logger.info(f"Trying session token: {token[:8]}...")
        session = get_session(token, db)
        
        if session:
            logger.info(f"Found valid session for user {session.user_id}")
            # Get user from database
            user = session.user
            if user:
                # Update last active
                user.last_active = datetime.utcnow()
                db.commit()
                return user
            else:
                logger.error(f"No user found for session user_id {session.user_id}")
        else:
            logger.info("No valid session token provided")
    else:
        logger.info("No session token provided")
    
    # If no request object, we can't check headers
    if not request:
        raise HTTPException(
            status_code=401,
            detail="No authentication provided",
            headers={"WWW-Authenticate": "Bearer"}
        )
    
    # Try wallet address first (preferred auth method)
    wallet_address = request.headers.get('X-Wallet-Address')
    if wallet_address:
        try:
            # Validate wallet address format
            if not Web3.is_address(wallet_address):
                logger.error(f"Invalid wallet address format: {wallet_address}")
                raise HTTPException(
                    status_code=401,
                    detail="Invalid wallet address",
                    headers={"WWW-Authenticate": "Bearer"}
                )
                
            # Convert to checksum address
            wallet_address = Web3.to_checksum_address(wallet_address)
            
            # Get user by wallet address
            user = db.query(User).filter(
                User.wallet_address == wallet_address
            ).first()
            
            if user:
                # Update last active
                user.last_active = datetime.utcnow()
                db.commit()
                return user
            else:
                logger.error(f"No user found with wallet address: {wallet_address}")
                raise HTTPException(
                    status_code=401,
                    detail="User not found for wallet address",
                    headers={"WWW-Authenticate": "Bearer"}
                )
                
        except Exception as e:
            logger.error(f"Error verifying wallet address: {str(e)}")
            raise HTTPException(
                status_code=401,
                detail="Invalid wallet address",
                headers={"WWW-Authenticate": "Bearer"}
            )
        
    # If no valid wallet, try World ID credentials (legacy)
    credentials = request.headers.get('X-WorldID-Credentials')
    if not credentials:
        raise HTTPException(
            status_code=401,
            detail="No authentication provided",
            headers={"WWW-Authenticate": "Bearer"}
        )
        
    try:
        creds = json.loads(credentials)
        logger.info(f"Received credentials for nullifier_hash: {creds['nullifier_hash']}")
        
        # Check for existing verification
        verification = db.query(WorldIDVerification).filter(
            WorldIDVerification.nullifier_hash == creds["nullifier_hash"]
        ).first()
        
        if not verification:
            raise HTTPException(
                status_code=401,
                detail="No verification found",
                headers={"WWW-Authenticate": "Bearer"}
            )
        
        # Get user
        user = db.query(User).filter(
            User.world_id == creds["nullifier_hash"]
        ).first()
        
        if not user:
            raise HTTPException(
                status_code=401,
                detail="User not found",
                headers={"WWW-Authenticate": "Bearer"}
            )
            
        # Update last active
        user.last_active = datetime.utcnow()
        db.commit()
            
        return user
        
    except Exception as e:
        logger.error(f"Error verifying credentials: {str(e)}")
        raise HTTPException(
            status_code=401,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Bearer"}
        )

# Admin API key for direct access without session token
ADMIN_API_KEY = "admin-persona-api-key-2024"  # This should be stored securely in environment variables

async def get_admin_access(
    request: Request,
    db: Session = Depends(get_db)
) -> bool:
    """
    Authenticate admin access using API key
    This bypasses the session token requirement for admin endpoints
    """
    logger.info("Checking admin API key")
    
    # Check for API key in headers
    api_key = request.headers.get('X-Admin-API-Key')
    if not api_key or api_key != ADMIN_API_KEY:
        logger.warning("Invalid or missing admin API key")
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing admin API key",
            headers={"WWW-Authenticate": "Bearer"}
        )
    
    logger.info("Admin API key validated successfully")
    return True
