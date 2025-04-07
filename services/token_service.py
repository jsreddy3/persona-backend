from web3 import Web3
from eth_account import Account
from eth_account.messages import encode_defunct
import os
import logging
from repositories.token_repository import TokenRedemptionRepository
from database.models import User
import secrets

logger = logging.getLogger(__name__)

class TokenService:
    def __init__(self):
        # Connect to World Chain Mainnet
        self.w3 = Web3(Web3.HTTPProvider('https://worldchain-mainnet.g.alchemy.com/public'))
        
        # Contract details
        self.token_contract_address = os.getenv("TOKEN_CONTRACT_ADDRESS", "0x1d61D872aa0FE0bD449E6eCB2A2B4106B7B6f99D")
        self.signer_private_key = os.getenv("TOKEN_SIGNER_PRIVATE_KEY")
        
        if not self.token_contract_address:
            logger.error("TOKEN_CONTRACT_ADDRESS not set, using default")
        
        if not self.signer_private_key:
            logger.error("TOKEN_SIGNER_PRIVATE_KEY not set")
            # Generate a temporary key for development if needed
            self.signer_private_key = os.getenv("TOKEN_SIGNER_PRIVATE_KEY", "0x" + secrets.token_hex(32))
            logger.warning("Using temporary private key for development")
        
        # Initialize repository
        self.token_repository = TokenRedemptionRepository()
        
        # Minimal ABI for minting and checking balance
        self.abi = [
            {
                "inputs": [
                    {"internalType": "uint256", "name": "amount", "type": "uint256"},
                    {"internalType": "bytes32", "name": "nonce", "type": "bytes32"},
                    {"internalType": "bytes", "name": "signature", "type": "bytes"}
                ],
                "name": "mintWithSignature",
                "outputs": [],
                "stateMutability": "nonpayable",
                "type": "function"
            }
        ]
        
        # Create contract instance
        self.contract = self.w3.eth.contract(
            address=self.token_contract_address,
            abi=self.abi
        )
    
    def calculate_redeemable_tokens(self, user: User) -> int:
        """
        Calculate how many tokens a user can redeem based on chat popularity.
        Each message sent to user's created characters is worth 10 tokens.
        
        Returns the redeemable amount after subtracting already redeemed tokens.
        """
        if not user:
            return 0
            
        earned_tokens = user.character_messages_received * 100
        redeemable = max(0, earned_tokens - user.tokens_redeemed)
        
        return redeemable
    
    def create_mint_signature(self, user_address: str, amount_in_wei: int, nonce: bytes = None) -> dict:
        """
        Create a signature for minting tokens
        
        Returns a dictionary with:
        - nonce: the nonce used (bytes32 hex string)
        - signature: the signature (bytes hex string)
        - amount: the amount in wei
        """
        # Generate a nonce if not provided
        if nonce is None:
            nonce = self.w3.keccak(text=f"{user_address}-{amount_in_wei}-{self.w3.eth.get_block('latest').timestamp}")
        
        # Important: We need to match exactly how the contract creates the message hash
        # The contract uses: keccak256(abi.encodePacked(msg.sender, amount, nonce))
        message = self.w3.solidity_keccak(
            ['address', 'uint256', 'bytes32'],
            [self.w3.to_checksum_address(user_address), amount_in_wei, nonce]
        )
        
        # Need to hash this again with the Ethereum Signed Message prefix - this is what toEthSignedMessageHash does in the contract
        # This is crucial - the contract uses MessageHashUtils.toEthSignedMessageHash() which adds the prefix
        message_to_sign = encode_defunct(primitive=message)
        
        # Sign the message with the private key
        account = Account.from_key(self.signer_private_key)
        signed_message = account.sign_message(message_to_sign)
        
        return {
            "nonce": nonce.hex(),
            "signature": signed_message.signature.hex(),
            "amount": amount_in_wei
        }
    
    def create_redemption(self, user_id: int, user_address: str, amount: int) -> dict:
        """
        Create a new token redemption.
        
        Args:
            user_id: User's database ID
            user_address: User's blockchain wallet address
            amount: Amount of tokens to redeem (not in wei)
            
        Returns:
            Dictionary with redemption details including signature
        """
        # Convert amount to wei (assuming 18 decimal places)
        amount_in_wei = amount * 10**18
        
        # Generate signature data
        signature_data = self.create_mint_signature(user_address, amount_in_wei)
        
        # Create redemption record in database
        redemption = self.token_repository.create_redemption(
            user_id=user_id,
            amount=amount,
            signature=signature_data["signature"],
            nonce=signature_data["nonce"]
        )
        
        # Update user's tokens_redeemed counter
        self.token_repository.update_user_tokens_redeemed(user_id, amount)
        
        # Return redemption details for frontend
        return {
            "redemption_id": redemption.id,
            "user_address": user_address,
            "amount": amount,
            "amount_in_wei": str(amount_in_wei),  # Convert to string to avoid JS integer issues
            "nonce": signature_data["nonce"],
            "signature": signature_data["signature"],
            "contract_address": self.token_contract_address
        }
    
    def update_redemption_status(self, redemption_id: int, status: str, transaction_hash: str = None) -> bool:
        """
        Update the status of a redemption
        
        Args:
            redemption_id: ID of the redemption to update
            status: New status (completed, failed)
            transaction_hash: Optional blockchain transaction hash
            
        Returns:
            True if update was successful, False otherwise
        """
        return self.token_repository.update_redemption_status(
            redemption_id=redemption_id,
            status=status,
            transaction_hash=transaction_hash
        )