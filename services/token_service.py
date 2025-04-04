from web3 import Web3
from eth_account import Account
from eth_account.messages import encode_defunct
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
            address=self.contract_address,
            abi=self.abi
        )
    
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