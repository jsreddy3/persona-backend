import logging
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from database.models import SIWENonce, User
from typing import Optional, Dict, Any
import secrets
from web3 import Web3
from eth_account import Account
from eth_account.messages import encode_defunct

logger = logging.getLogger(__name__)

class SIWEService:
    def generate_nonce(self, db: Session) -> str:
        """
        Generate a random nonce for SIWE auth
        
        Returns:
            A random string to be used as a nonce
        """
        nonce = secrets.token_urlsafe(32)
        logger.info(f"Generating new nonce: {nonce[:8]}...")
        
        # Store nonce in database with expiration
        nonce_obj = SIWENonce(
            nonce=nonce,
            created_at=datetime.utcnow(),
            expires_at=datetime.utcnow() + timedelta(minutes=15),
            used=False
        )
        db.add(nonce_obj)
        db.commit()
        
        logger.info(f"Stored nonce {nonce[:8]}... with expiration: {nonce_obj.expires_at}")
        
        return nonce
        
    def verify_nonce(self, db: Session, nonce: str) -> bool:
        """
        Verify a nonce is valid and not used
        
        Args:
            db: Database session
            nonce: Nonce to verify
            
        Returns:
            True if nonce is valid and not used, False otherwise
        """
        logger.info(f"Verifying nonce: {nonce[:8]}...")
        
        nonce_obj = db.query(SIWENonce).filter(
            SIWENonce.nonce == nonce,
            SIWENonce.used == False,
            SIWENonce.expires_at > datetime.utcnow()
        ).first()
        
        if not nonce_obj:
            logger.error(f"Nonce {nonce[:8]}... not found, expired, or already used")
            return False
            
        logger.info(f"Nonce {nonce[:8]}... is valid")
        return True
        
    def use_nonce(self, db: Session, nonce: str) -> None:
        """
        Mark a nonce as used
        
        Args:
            db: Database session
            nonce: Nonce to mark as used
        """
        logger.info(f"Marking nonce as used: {nonce[:8]}...")
        
        nonce_obj = db.query(SIWENonce).filter(
            SIWENonce.nonce == nonce
        ).first()
        
        if nonce_obj:
            nonce_obj.used = True
            db.commit()
            logger.info(f"Nonce {nonce[:8]}... marked as used")
        else:
            logger.warning(f"Attempted to mark non-existent nonce {nonce[:8]}... as used")
            
    def verify_wallet_auth(self, db: Session, payload: Dict[str, Any], nonce: str) -> Optional[str]:
        """
        Verify a wallet auth payload from MiniKit
        
        Args:
            db: Database session
            payload: MiniKit wallet auth payload (MiniAppWalletAuthSuccessPayload)
            nonce: Expected nonce
            
        Returns:
            wallet_address if validation succeeds, None otherwise
        """
        try:
            # First verify the nonce is valid and unused
            if not self.verify_nonce(db, nonce):
                logger.error(f"Invalid or expired nonce: {nonce}")
                return None
                
            # Verify payload status
            if payload.get("status") != "success":
                logger.error(f"Payload status is not success: {payload.get('status')}")
                return None
                
            # Extract message, signature, and address from payload
            message = payload.get("message")
            signature = payload.get("signature")
            address = payload.get("address")
            
            if not message or not signature or not address:
                logger.error("Missing required fields in payload")
                return None
                
            try:
                # Parse and validate SIWE message
                siwe_message_data = self.parse_siwe_message(message)
                
                # Validate nonce in message matches expected nonce
                if siwe_message_data.get("nonce") != nonce:
                    logger.error(f"Nonce mismatch. Got: {siwe_message_data.get('nonce')}, Expected: {nonce}")
                    return None
                    
                # Validate expiration time
                expiration_time = siwe_message_data.get("expiration_time")
                if expiration_time:
                    # Convert to offset-naive datetime for comparison with datetime.utcnow()
                    try:
                        # Parse ISO format with timezone
                        expiration = datetime.fromisoformat(expiration_time.replace('Z', '+00:00'))
                        # Remove timezone info to make it naive
                        expiration = expiration.replace(tzinfo=None)
                        if expiration < datetime.utcnow():
                            logger.error("Message has expired")
                            return None
                    except Exception as e:
                        logger.error(f"Error parsing expiration time: {str(e)}")
                        return None
                        
                # Validate not before time
                not_before = siwe_message_data.get("not_before")
                if not_before:
                    try:
                        # Parse ISO format with timezone
                        not_before_time = datetime.fromisoformat(not_before.replace('Z', '+00:00'))
                        # Remove timezone info to make it naive
                        not_before_time = not_before_time.replace(tzinfo=None)
                        if not_before_time > datetime.utcnow():
                            logger.error("Not Before time has not passed")
                            return None
                    except Exception as e:
                        logger.error(f"Error parsing not-before time: {str(e)}")
                        return None
                        
                # Validate the address in the message matches the address in the payload
                if siwe_message_data.get("address").lower() != address.lower():
                    logger.error(f"Address mismatch. Message: {siwe_message_data.get('address')}, Payload: {address}")
                    return None
                    
                # Full production implementation with eth_account for signature verification
                try:
                    # Use encode_defunct to create an EIP-191 encoded message
                    message_object = encode_defunct(text=message)
                    
                    # Debug logging
                    logger.info(f"SIWE Message to verify: '{message}'")
                    logger.info(f"Raw signature: '{signature}'")
                    
                    # Recover the address from the signature
                    if not signature.startswith('0x'):
                        signature = f"0x{signature}"
                        
                    recovered_address = Account.recover_message(message_object, signature=signature)
                    logger.info(f"Full SIWE data: {siwe_message_data}")
                    
                    # Compare recovered address with the one in the payload
                    if recovered_address.lower() != address.lower():
                        logger.error(f"Signature verification failed. Recovered: {recovered_address}, Expected: {address}")
                        return None
                        
                    logger.info(f"Signature verified successfully for address: {address}")
                except Exception as e:
                    logger.error(f"Signature verification error: {str(e)}")
                    return None
                
                # If all validations pass, return the wallet address
                return Web3.to_checksum_address(address)
                
            except Exception as e:
                logger.error(f"Error validating SIWE message: {str(e)}")
                return None
            
        except Exception as e:
            logger.error(f"Error verifying wallet auth: {str(e)}")
            return None
            
    def parse_siwe_message(self, message_str: str) -> Dict[str, Any]:
        """
        Parse a SIWE message string into its components
        
        Args:
            message_str: SIWE message string
            
        Returns:
            Dictionary containing parsed SIWE message fields
        """
        lines = message_str.split('\n')
        if len(lines) < 7:  # Minimum required fields
            raise ValueError("Invalid SIWE message format: too few lines")
            
        result = {}
        
        # Extract domain (remove "wants you to sign in with your Ethereum account:")
        preamble_suffix = " wants you to sign in with your Ethereum account:"
        if preamble_suffix in lines[0]:
            result["domain"] = lines[0].replace(preamble_suffix, "")
        else:
            raise ValueError("Invalid SIWE message format: missing domain preamble")
            
        # Extract address (line 1)
        result["address"] = lines[1]
        
        # Line 2 is typically empty
        
        # Extract statement if present (line 3 if it doesn't start with a tag)
        current_line = 3
        if current_line < len(lines) and not lines[current_line].startswith("URI:") and lines[current_line].strip():
            result["statement"] = lines[current_line]
            current_line += 1
            
        # Process remaining tagged fields
        for i in range(current_line, len(lines)):
            line = lines[i]
            
            if not line.strip():
                continue
                
            if line.startswith("URI:"):
                result["uri"] = line.replace("URI:", "").strip()
            elif line.startswith("Version:"):
                result["version"] = line.replace("Version:", "").strip()
            elif line.startswith("Chain ID:"):
                result["chain_id"] = line.replace("Chain ID:", "").strip()
            elif line.startswith("Nonce:"):
                result["nonce"] = line.replace("Nonce:", "").strip()
            elif line.startswith("Issued At:"):
                result["issued_at"] = line.replace("Issued At:", "").strip()
            elif line.startswith("Expiration Time:"):
                result["expiration_time"] = line.replace("Expiration Time:", "").strip()
            elif line.startswith("Not Before:"):
                result["not_before"] = line.replace("Not Before:", "").strip()
            elif line.startswith("Request ID:"):
                result["request_id"] = line.replace("Request ID:", "").strip()
            
        # Validate required fields
        required_fields = ["domain", "address", "uri", "version", "nonce", "issued_at"]
        for field in required_fields:
            if field not in result:
                raise ValueError(f"Invalid SIWE message format: missing required field {field}")
                
        return result
        
    def get_user_by_wallet(self, db: Session, wallet_address: str) -> Optional[User]:
        """Get a user by wallet address"""
        return db.query(User).filter(User.wallet_address == wallet_address).first()
        
    def create_user(self, db: Session, wallet_address: str, username: str = None, email: str = None) -> User:
        """
        Create a new user with a wallet address
        
        Args:
            db: Database session
            wallet_address: Ethereum wallet address
            username: Optional username
            email: Optional email
            
        Returns:
            Newly created User object
        """
        logger.info(f"Creating new user with wallet address: {wallet_address}")
        
        if username:
            logger.info(f"Username provided: {username}")
        
        # Create new user
        user = User(
            wallet_address=wallet_address,
            username=username,
            email=email,
            last_active=datetime.utcnow()
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        
        logger.info(f"Created new user with ID: {user.id}")
        
        return user
        
    def link_wallet_to_world_id(self, db: Session, world_id: str, wallet_address: str) -> Optional[User]:
        """
        Link a wallet address to an existing World ID user
        
        Args:
            db: Database session
            world_id: World ID nullifier hash
            wallet_address: Ethereum wallet address
            
        Returns:
            User object if successful, None otherwise
        """
        logger.info(f"Linking wallet {wallet_address} to World ID {world_id[:8]}...")
        
        # Find user by World ID
        user = db.query(User).filter(User.world_id == world_id).first()
        
        if not user:
            logger.error(f"No user found with World ID: {world_id[:8]}...")
            return None
            
        # Check if wallet address is already linked to another user
        existing_wallet_user = db.query(User).filter(User.wallet_address == wallet_address).first()
        if existing_wallet_user and existing_wallet_user.id != user.id:
            logger.error(f"Wallet address {wallet_address} is already linked to user {existing_wallet_user.id}")
            return None
            
        # Link wallet address to user
        user.wallet_address = wallet_address
        db.commit()
        logger.info(f"Successfully linked wallet {wallet_address} to user {user.id}")
        
        return user
