from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, Dict, Any
from database.database import get_db, SessionLocal
from database.models import User
from services.siwe_service import SIWEService
from dependencies.auth import create_session
import logging

logger = logging.getLogger(__name__)
router = APIRouter()
siwe_service = SIWEService()

# Models for request validation
class WalletAuthPayload(BaseModel):
    status: str
    message: str
    signature: str
    address: str
    version: int

class WalletAuthRequest(BaseModel):
    payload: WalletAuthPayload
    nonce: str

class LinkWalletRequest(BaseModel):
    payload: WalletAuthPayload
    nonce: str
    world_id: str

class CreateWalletUserRequest(BaseModel):
    wallet_address: str
    temp_state: str  # Temporary state to verify request legitimacy

@router.get("/nonce")
async def get_nonce():
    """Generate a nonce for SIWE authentication"""
    logger.info("Generating new nonce for wallet authentication")
    
    # Following optimized DB connection pattern - open connection only when needed
    db = SessionLocal()
    try:
        nonce = siwe_service.generate_nonce(db)
        logger.info(f"Generated nonce: {nonce[:8]}...")
        return {"nonce": nonce}
    finally:
        db.close()

@router.post("/wallet")
async def wallet_auth(request: WalletAuthRequest):
    """
    Authenticate with wallet using MiniKit walletAuth
    
    This follows the optimized DB connection pattern for potentially
    long-running operations
    """
    logger.info(f"Wallet authentication attempt with nonce: {request.nonce[:8]}...")
    
    # First DB session for validation
    db = SessionLocal()
    try:
        # Verify wallet auth payload
        wallet_address = siwe_service.verify_wallet_auth(
            db, request.payload.dict(), request.nonce
        )
        
        if not wallet_address:
            logger.error("Wallet authentication failed: could not verify signature")
            raise HTTPException(status_code=401, detail="Invalid signature or payload")
            
        logger.info(f"Wallet signature verified for address: {wallet_address}")
            
        # Check if user exists with this wallet
        user = siwe_service.get_user_by_wallet(db, wallet_address)
        
        if user:
            # User exists, create session
            logger.info(f"User found for wallet address {wallet_address}: {user.id}")
            token = create_session(user.id, db)
            logger.info(f"Created session token for user {user.id}")
            return {
                "status": "success", 
                "session_token": token,
                "user_exists": True
            }
        else:
            # No user with this wallet - return special response
            # Frontend will show migration screen or new user flow
            logger.info(f"No user found with wallet address {wallet_address}")
            return {
                "status": "success",
                "user_exists": False,
                "wallet_address": wallet_address,
                "temp_state": request.nonce  # Use nonce as temporary state
            }
    finally:
        db.close()

@router.post("/link-wallet")
async def link_wallet(request: LinkWalletRequest):
    """Link wallet to existing World ID account (for migration)"""
    logger.info(f"Attempting to link wallet {request.payload.address} to existing account")
    
    # First DB session for validation
    db = SessionLocal()
    try:
        # Verify wallet auth payload
        wallet_address = siwe_service.verify_wallet_auth(
            db, request.payload.dict(), request.nonce
        )
        
        if not wallet_address:
            logger.error("Wallet authentication failed: could not verify signature")
            raise HTTPException(status_code=401, detail="Invalid signature or payload")
        
        # Check if wallet is already linked to another account
        existing_wallet_user = siwe_service.get_user_by_wallet(db, wallet_address)
        if existing_wallet_user:
            logger.error(f"Wallet address {wallet_address} is already linked to user {existing_wallet_user.id}")
            raise HTTPException(
                status_code=409, 
                detail="This wallet is already linked to another account"
            )
        
        # Link wallet to existing World ID user
        user = siwe_service.link_wallet_to_world_id(db, request.world_id, wallet_address)
        if not user:
            logger.error(f"No user found with World ID {request.world_id}")
            raise HTTPException(status_code=404, detail="User with this World ID not found")
        
        logger.info(f"Successfully linked wallet {wallet_address} to user {user.id}")
        
        # Create session
        token = create_session(user.id, db)
        logger.info(f"Created session token for user {user.id} after wallet linking")
        
        return {
            "status": "success",
            "message": "Wallet linked successfully",
            "session_token": token
        }
    finally:
        db.close()

@router.post("/new-user")
async def create_new_user(request: CreateWalletUserRequest):
    """Create new user with wallet address only"""
    logger.info(f"Creating new user with wallet address: {request.wallet_address}")
    
    # Open DB connection
    db = SessionLocal()
    try:
        # Check if wallet is already linked to an account
        existing_user = siwe_service.get_user_by_wallet(db, request.wallet_address)
        if existing_user:
            logger.error(f"Wallet address {request.wallet_address} is already linked to user {existing_user.id}")
            raise HTTPException(
                status_code=409, 
                detail="This wallet is already linked to an account"
            )
        
        # Create new user
        user = siwe_service.create_user(db, request.wallet_address)
        
        logger.info(f"Successfully created new user {user.id} with wallet {request.wallet_address}")
        
        # Create session
        token = create_session(user.id, db)
        logger.info(f"Created session token for new user {user.id}")
        
        return {
            "status": "success",
            "message": "Account created successfully",
            "session_token": token
        }
    finally:
        db.close()
