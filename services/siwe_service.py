import logging
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from database.models import SIWENonce, User
from typing import Optional, Dict, Any
import secrets
from web3 import Web3
from eth_account import Account
from eth_account.messages import encode_defunct
import os
from eth_utils import keccak
from eth_account._utils.signing import sign_message_hash, to_standard_signature_bytes
from eth_keys import KeyAPI

logger = logging.getLogger(__name__)

# Safe contract ABI for the isOwner function
SAFE_CONTRACT_ABI = [
    {
        "inputs": [
            {
                "internalType": "address",
                "name": "owner",
                "type": "address"
            }
        ],
        "name": "isOwner",
        "outputs": [
            {
                "internalType": "bool",
                "name": "",
                "type": "bool"
            }
        ],
        "stateMutability": "view",
        "type": "function"
    }
]

# RPC endpoints for different chains
CHAIN_RPC_URLS = {
    # Chain ID 480 is Optimism Sepolia - Update to match MiniKit's Alchemy endpoint
    '480': os.getenv('OPTIMISM_SEPOLIA_RPC_URL', 'https://worldchain-mainnet.g.alchemy.com/public'),
    # Can add more chains as needed
    '1': 'https://mainnet.infura.io/v3/9aa3d95b3bc440fa88ea12eaa4456161',  # Ethereum mainnet
    '10': 'https://mainnet.optimism.io',  # Optimism mainnet
}

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
            # Extract data from payload
            status = payload.get("status")
            message = payload.get("message")
            signature = payload.get("signature") 
            address = payload.get("address")
            
            # Basic validation
            if not all([status, message, signature, address]):
                logger.error("Missing required fields in wallet auth payload")
                return None
                
            if status != "success":
                logger.error(f"Invalid status in wallet auth payload: {status}")
                return None
                
            # Verify the nonce
            if not self.verify_nonce(db, nonce):
                logger.error(f"Invalid nonce: {nonce}")
                return None
                
            # Mark the nonce as used to prevent replay attacks
            self.use_nonce(db, nonce)
            
            # Parse SIWE message
            siwe_message_data = self.parse_siwe_message(message)
            
            # Additional validations
            try:
                # Validate nonce in message
                if siwe_message_data.get("nonce") != nonce:
                    logger.error(f"Nonce mismatch. Message: {siwe_message_data.get('nonce')}, Expected: {nonce}")
                    return None
                    
                # Validate expiration time
                expiration_time = siwe_message_data.get("expiration_time")
                if expiration_time:
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
                if siwe_message_data.get("address", "").lower() != address.lower():
                    logger.error(f"Address mismatch. Message: {siwe_message_data.get('address')}, Payload: {address}")
                    return None
                    
                # Full production implementation with eth_account for signature verification
                try:
                    # Debug logging
                    logger.info(f"SIWE Message to verify: '{message}'")
                    logger.info(f"Raw signature: '{signature}'")
                    
                    # Double-prefix the message to match MiniKit's implementation
                    # First, apply the ERC-191 prefix manually
                    ERC_191_PREFIX = "\x19Ethereum Signed Message:\n"
                    prefixed_message = f"{ERC_191_PREFIX}{len(message)}{message}"
                    
                    # Then, hash this already-prefixed message, effectively applying the prefix AGAIN
                    # This matches MiniKit's approach exactly: hashMessage(ERC_191_PREFIX + len(message) + message)
                    double_prefixed_message = f"{ERC_191_PREFIX}{len(prefixed_message)}{prefixed_message}"
                    hashed_message = keccak(text=double_prefixed_message)
                    logger.info(f"Hashed message: {hashed_message.hex()}")
                    
                    # Format signature to match their approach
                    if signature.startswith('0x'):
                        signature = signature[2:]  # Remove 0x prefix if present
                    
                    # Recover the signer address
                    sig_bytes = bytes.fromhex(signature)
                    
                    # Need to correctly format the signature
                    if len(sig_bytes) == 65:
                        # Extract r, s, v from signature
                        r = int.from_bytes(sig_bytes[:32], byteorder='big')
                        s = int.from_bytes(sig_bytes[32:64], byteorder='big')
                        v = sig_bytes[64]
                        
                        # Normalize v: if it's 27 or 28, convert to 0 or 1
                        if v >= 27:
                            v -= 27
                            
                        # KeyAPI expects a signature as a bytes object
                        keys = KeyAPI()
                        
                        # First create the signature object from components
                        sig_obj = keys.Signature(vrs=(v, r, s))
                        
                        # Then recover the public key
                        pk = keys.PublicKey.recover_from_msg_hash(hashed_message, sig_obj)
                        
                        # Get the address from the public key
                        recovered_address = pk.to_checksum_address()
                        logger.info(f"Recovered address: {recovered_address}")
                    else:
                        logger.error(f"Invalid signature length: {len(sig_bytes)}")
                        return None
                    
                    # Verify through contract ONLY if direct address match fails
                    if recovered_address.lower() == address.lower():
                        # Direct match - no need for contract verification
                        logger.info(f"Direct address match between recovered and wallet: {recovered_address}")
                        return Web3.to_checksum_address(address)
                    
                    # Address doesn't match directly, try contract verification
                    # Verify the recovered signer is authorized for the wallet address
                    chain_id = siwe_message_data.get("chain_id")
                    if not chain_id:
                        logger.error("Chain ID not found in SIWE message")
                        return None
                        
                    # Get RPC URL for the chain
                    rpc_url = CHAIN_RPC_URLS.get(chain_id)
                    if not rpc_url:
                        logger.error(f"No RPC URL found for chain ID {chain_id}")
                        return None
                    
                    try:
                        # Initialize Web3 connection - match their approach exactly
                        w3 = Web3(Web3.HTTPProvider(rpc_url))
                        if not w3.is_connected():
                            logger.error(f"Failed to connect to RPC endpoint: {rpc_url}")
                            # NEVER accept auth when RPC connection fails
                            return None
                            
                        # Ensure addresses are checksummed
                        checksum_wallet = Web3.to_checksum_address(address)
                        checksum_signer = Web3.to_checksum_address(recovered_address)
                        
                        try:
                            # Create contract instance like MiniKit does
                            contract = w3.eth.contract(address=checksum_wallet, abi=SAFE_CONTRACT_ABI)
                            
                            # Call isOwner function
                            is_authorized = contract.functions.isOwner(checksum_signer).call()
                            
                            if is_authorized:
                                logger.info(f"Contract verification successful: {checksum_signer} is authorized for {checksum_wallet}")
                                return Web3.to_checksum_address(address)
                            else:
                                logger.error(f"Contract verification failed: {checksum_signer} is not authorized for {checksum_wallet}")
                                # NEVER accept auth when verification fails
                                return None
                        except Exception as contract_error:
                            # Contract call failed - could be not a contract or wrong ABI
                            logger.error(f"Contract call failed: {str(contract_error)}")
                            # NEVER accept auth when contract verification fails
                            return None
                    except Exception as web3_error:
                        logger.error(f"Web3 verification error: {str(web3_error)}")
                        # NEVER accept auth without verification
                        return None
                except Exception as sig_error:
                    logger.error(f"Signature verification error: {str(sig_error)}")
                    return None
            except Exception as validation_error:
                logger.error(f"Error validating SIWE message: {str(validation_error)}")
                return None
        except Exception as e:
            logger.error(f"Error verifying wallet auth: {str(e)}")
            return None

    def parse_siwe_message(self, message_str: str) -> Dict[str, str]:
        """
        Parse a SIWE message string into its components
        
        Args:
            message_str: SIWE message string
            
        Returns:
            Dictionary containing parsed SIWE message fields
        """
        logger.info(f"Parsing SIWE message: '{message_str}'")
        
        try:
            lines = message_str.strip().split('\n')
            result = {}
            
            # Parse domain and address from first line
            if len(lines) > 0:
                first_line = lines[0]
                if ' wants you to sign in with your Ethereum account:' in first_line:
                    result['domain'] = first_line.split(' wants you to sign in with your Ethereum account:')[0]
                    
            # The second line should be the address
            if len(lines) > 1:
                result['address'] = lines[1].strip()
                
            # Parse remaining fields
            for i in range(2, len(lines)):
                line = lines[i].strip()
                if ': ' in line:
                    key, value = line.split(': ', 1)
                    key = key.lower().replace(' ', '_')
                    result[key] = value
                else:
                    # This line is likely the statement
                    result['statement'] = line
            
            logger.info(f"Parsed SIWE message result: {result}")
            return result
        except Exception as e:
            logger.error(f"Error parsing SIWE message: {str(e)}")
            return {}

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
