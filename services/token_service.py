from web3 import Web3
from eth_account import Account
from eth_account.messages import encode_defunct
import json
import secrets
import os
import logging

logger = logging.getLogger(__name__)

class TokenService:
    def __init__(self):
        # Connect to World Chain Mainnet
        self.w3 = Web3(Web3.HTTPProvider('https://worldchain-mainnet.g.alchemy.com/public'))
        
        # Contract details
        self.contract_address = os.getenv("TOKEN_CONTRACT_ADDRESS")
        self.signer_private_key = os.getenv("TOKEN_SIGNER_PRIVATE_KEY")
        
        if not self.contract_address or not self.signer_private_key:
            raise ValueError("TOKEN_CONTRACT_ADDRESS and TOKEN_SIGNER_PRIVATE_KEY must be set")
        
        # Minimal ABI for minting and checking balance
        self.abi = [
            {
                "inputs": [
                    {"name": "amount", "type": "uint256"},
                    {"name": "nonce", "type": "bytes32"},
                    {"name": "signature", "type": "bytes"}
                ],
                "name": "mintWithSignature",
                "outputs": [],
                "stateMutability": "nonpayable",
                "type": "function"
            },
            {
                "inputs": [
                    {"name": "account", "type": "address"}
                ],
                "name": "balanceOf",
                "outputs": [
                    {"name": "", "type": "uint256"}
                ],
                "stateMutability": "view",
                "type": "function"
            }
        ]
        
        # Create contract instance
        self.contract = self.w3.eth.contract(
            address=self.contract_address,
            abi=self.abi
        )

    def create_mint_signature(self, user_address: str, amount_in_wei: int, nonce: bytes) -> bytes:
        """
        Create a signature for minting tokens
        """
        # Create the message hash (must match the contract's hash creation)
        message = self.w3.solidity_keccak(
            ['address', 'uint256', 'bytes32'],
            [user_address, amount_in_wei, nonce]
        )
        
        # Sign the message hash
        account = Account.from_key(self.signer_private_key)
        signed = account.sign_message(encode_defunct(message))
        return signed.signature

    def mint_tokens(self, to_address: str, amount: float) -> str:
        """
        Request token minting with a valid signature
        Returns the transaction hash
        """
        try:
            # Convert amount to wei (18 decimals)
            amount_in_wei = int(amount * 10**18)
            
            # Generate random nonce
            nonce = secrets.token_bytes(32)
            
            # Get signature
            signature = self.create_mint_signature(to_address, amount_in_wei, nonce)
            
            # Build transaction data
            mint_data = self.contract.encodeABI(
                fn_name="mintWithSignature",
                args=[amount_in_wei, nonce, signature]
            )
            
            # Build full transaction
            tx = {
                'from': to_address,
                'to': self.contract_address,
                'data': mint_data,
                'value': 0,
                'gas': 200000,
                'gasPrice': self.w3.eth.gas_price,
                'nonce': self.w3.eth.get_transaction_count(to_address)
            }
            
            # Send transaction
            tx_hash = self.w3.eth.send_transaction(tx)
            return tx_hash.hex()
            
        except Exception as e:
            logger.error(f"Failed to mint tokens: {str(e)}", exc_info=True)
            raise e

    def get_balance(self, address: str) -> float:
        """
        Get token balance of an address
        Returns balance in PERSONA tokens (not wei)
        """
        try:
            balance_wei = self.contract.functions.balanceOf(address).call()
            return balance_wei / 10**18
        except Exception as e:
            logger.error(f"Failed to get balance: {str(e)}", exc_info=True)
            raise e