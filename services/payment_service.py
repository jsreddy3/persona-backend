import os
import secrets
import httpx
from typing import Dict, Any, List, Optional, Tuple
from decimal import Decimal

from repositories.payment_repository import PaymentRepository

# Constants
TOKEN_DECIMALS = {
    "USDC.e": 6,
    "WLD": 18
}

SUPPORTED_TOKENS = ["WLD", "USDC.e"]
DEFAULT_TOKEN = "WLD"

# Mapping between our internal token names and World App API token names
WORLD_API_TOKEN_MAPPING = {
    "WLD": "WLD",
    "USDC.e": "USDCE"
}

class PaymentService:
    """Service for handling payment operations with World ID MiniKit"""
    
    @staticmethod
    async def get_token_prices(
        crypto_currencies: List[str] = ["WLD", "USDC.e"], 
        fiat_currencies: List[str] = ["USD"]
    ) -> Dict[str, Any]:
        """
        Get current token prices from World App API
        
        Args:
            crypto_currencies: List of cryptocurrencies to get prices for
            fiat_currencies: List of fiat currencies to convert to
            
        Returns:
            Dictionary of price information
        """
        # Convert our token names to World App API token names
        api_crypto_currencies = [WORLD_API_TOKEN_MAPPING.get(token, token) for token in crypto_currencies]
        crypto_str = ",".join(api_crypto_currencies)
        fiat_str = ",".join(fiat_currencies)
        
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"https://app-backend.worldcoin.dev/public/v1/miniapps/prices",
                params={
                    "cryptoCurrencies": crypto_str,
                    "fiatCurrencies": fiat_str
                }
            )
            
            if response.status_code != 200:
                raise Exception(f"Failed to get token prices: {response.text}")
            
            result = response.json()["result"]
            
            # Convert World App API token names back to our internal token names in the response
            if "prices" in result:
                prices = {}
                for api_token, token_data in result["prices"].items():
                    # Map from API token name back to our internal token name
                    internal_token = next((our_token for our_token, api_name in WORLD_API_TOKEN_MAPPING.items() 
                                          if api_name == api_token), api_token)
                    prices[internal_token] = token_data
                
                result["prices"] = prices
                
            return result
    
    @staticmethod
    def token_to_decimals(amount: float, token: str) -> int:
        """
        Convert token amount to decimals for payment.
        
        Args:
            amount: Amount in expected format (e.g., 25.12 for $25.12)
            token: Token type (USDC.e or WLD)
            
        Returns:
            Integer amount with proper decimal places
        """
        if token not in TOKEN_DECIMALS:
            raise ValueError(f"Invalid token: {token}")
            
        decimals = TOKEN_DECIMALS[token]
        factor = 10 ** decimals
        
        # Round to nearest integer instead of requiring a whole number
        # This handles fractional amounts that are common in crypto transactions
        return int(round(amount * factor))
    
    @staticmethod
    def decimals_to_token(amount: int, token: str) -> float:
        """
        Convert decimalized token amount back to human-readable format.
        
        Args:
            amount: Integer amount with decimal places
            token: Token type (USDC.e or WLD)
            
        Returns:
            Float amount in human-readable format
        """
        if token not in TOKEN_DECIMALS:
            raise ValueError(f"Invalid token: {token}")
            
        decimals = TOKEN_DECIMALS[token]
        factor = 10 ** decimals
        
        return amount / factor
    
    @staticmethod
    async def calculate_token_amount(credits: int, token_type: str) -> Tuple[float, int]:
        """
        Calculate the token amount needed for purchasing credits.
        
        Args:
            credits: Number of credits to purchase
            token_type: Type of token to use (WLD or USDC.e)
            
        Returns:
            Tuple of (human_readable_amount, raw_token_amount)
        """
        # Get the credit price from environment
        credit_price_usd = float(os.getenv("CREDIT_PRICE_USD", "0.1"))  # Default $0.10 per credit
        total_usd = credit_price_usd * credits
        
        # Get current token price
        try:
            # Map to API token name
            api_token = WORLD_API_TOKEN_MAPPING.get(token_type, token_type)
            prices = await PaymentService.get_token_prices([token_type], ["USD"])
            
            # Debug print the response structure for troubleshooting
            print(f"Token price API response: {prices}")
            
            if token_type not in prices["prices"]:
                # If our internal token name is not in response, try the API token name
                if api_token in prices["prices"]:
                    # Use API token name to get price data
                    token_price_data = prices["prices"][api_token]["USD"]
                else:
                    raise ValueError(f"Token price data not found for {token_type} or {api_token}")
            else:
                # Use our internal token name
                token_price_data = prices["prices"][token_type]["USD"]
            
            # Calculate token amount needed
            token_price_raw = int(token_price_data["amount"])
            token_decimals = int(token_price_data["decimals"])
            token_price = token_price_raw / (10 ** token_decimals)
            
            # Calculate the token amount needed (USD amount / token price in USD)
            token_amount = total_usd / token_price
            
            # Convert to token with decimals
            token_amount_with_decimals = PaymentService.token_to_decimals(token_amount, token_type)
            
            return (token_amount, token_amount_with_decimals)
        except Exception as e:
            print(f"Error calculating token amount: {str(e)}")
            raise
    
    @staticmethod
    def initiate_payment(
        user_id: int, 
        credits: int, 
        token_type: str = DEFAULT_TOKEN
    ) -> Dict[str, Any]:
        """
        Initialize a payment for message credits
        
        Args:
            user_id: User ID making the payment
            credits: Number of credits to purchase
            token_type: Type of token to use for payment
            
        Returns:
            Dictionary with payment details
        """
        if token_type not in SUPPORTED_TOKENS:
            raise ValueError(f"Unsupported token type: {token_type}")
            
        if credits < 1:
            raise ValueError("Must purchase at least 1 credit")
        
        # Generate unique reference
        reference = secrets.token_hex(16)
        
        # Use repository to create payment record
        PaymentRepository.create_payment(
            user_id=user_id,
            reference=reference,
            credits_amount=credits,
            token_type=token_type,
            token_decimal_places=TOKEN_DECIMALS[token_type],
            recipient_address=os.getenv("PAYMENT_RECIPIENT_ADDRESS")
        )
        
        # Return payment details
        return {
            "reference": reference,
            "recipient": os.getenv("PAYMENT_RECIPIENT_ADDRESS"),
            "credits_amount": credits,
            "token_type": token_type
        }
    
    @staticmethod
    async def verify_transaction(
        reference: str, 
        transaction_payload: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Verify a payment transaction with World ID API
        
        Args:
            reference: Payment reference ID
            transaction_payload: Transaction payload from World App
            
        Returns:
            Dictionary with verification results
        """
        # Get payment record using repository
        payment = PaymentRepository.get_payment_by_reference(reference)
        
        if not payment:
            raise ValueError("Payment not found")
            
        if payment.status == "confirmed":
            raise ValueError("Payment already confirmed")
            
        # Get transaction ID from payload
        transaction_id = transaction_payload.get("transaction_id")
        if not transaction_id:
            raise ValueError("Missing transaction ID in payload")
        
        # Verify with World ID API
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"https://developer.worldcoin.org/api/v2/minikit/transaction/{transaction_id}",
                params={
                    "app_id": os.getenv("WORLD_ID_APP_ID"),
                    "type": "payment"
                },
                headers={
                    "Authorization": f"Bearer {os.getenv('DEV_PORTAL_API_KEY')}"
                }
            )
            
            if response.status_code != 200:
                raise Exception(f"Failed to verify transaction: {response.text}")
                
            transaction = response.json()
            
            # Verify transaction details
            if transaction.get("reference") != reference:
                raise ValueError("Transaction reference mismatch")
        
        # Check transaction status
        transaction_status = transaction.get("transaction_status")
        
        # Prepare transaction details
        transaction_details = {
            "transaction_id": transaction_id,
            "transaction_hash": transaction.get("transaction_hash"),
            "chain": transaction.get("chain"),
            "sender_address": transaction.get("from"),
            "token_amount": transaction.get("token_amount"),
            "token_type": transaction.get("token")
        }
        
        if transaction_status == "failed":
            # Update payment status to failed
            PaymentRepository.update_payment_status(
                reference=reference, 
                status="failed",
                transaction_details=transaction_details
            )
            return {"success": False, "status": "failed"}
        
        # Update payment with transaction details
        PaymentRepository.update_payment_status(
            reference=reference,
            status="pending" if transaction_status == "pending" else "confirmed",
            transaction_details=transaction_details
        )
        
        # If transaction is mined, add credits to user
        if transaction_status == "mined":
            user = PaymentRepository.add_credits_to_user(
                user_id=payment.user_id,
                credits=payment.credits_amount
            )
            
            if user:
                return {
                    "success": True, 
                    "status": "confirmed", 
                    "credits": user.credits
                }
        
        # Still pending
        return {"success": True, "status": "pending"}
    
    @staticmethod
    async def get_transaction_status(reference: str) -> Dict[str, Any]:
        """
        Get the current status of a payment transaction
        
        Args:
            reference: Payment reference ID
            
        Returns:
            Dictionary with transaction status
        """
        # Get payment using repository
        payment = PaymentRepository.get_payment_by_reference(reference)
        
        if not payment:
            raise ValueError("Payment not found")
            
        if not payment.transaction_id:
            return {"status": payment.status, "reference": reference}
            
        # If payment already confirmed, no need to check API
        if payment.status == "confirmed":
            credits = PaymentRepository.get_user_credits(payment.user_id)
            return {
                "success": True,
                "status": "confirmed",
                "credits": credits,
                "reference": reference
            }
            
        # If payment failed, return failure
        if payment.status == "failed":
            return {
                "success": False,
                "status": "failed",
                "reference": reference
            }
        
        # For pending payments, check latest status
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"https://developer.worldcoin.org/api/v2/minikit/transaction/{payment.transaction_id}",
                params={
                    "app_id": os.getenv("WORLD_ID_APP_ID"),
                    "type": "payment"
                },
                headers={
                    "Authorization": f"Bearer {os.getenv('DEV_PORTAL_API_KEY')}"
                }
            )
            
            if response.status_code != 200:
                raise Exception(f"Failed to get transaction status: {response.text}")
                
            transaction = response.json()
        
        # Get transaction status
        transaction_status = transaction.get("transaction_status")
        
        # Prepare transaction details
        transaction_details = {
            "transaction_hash": transaction.get("transaction_hash")
        }
        
        if transaction_status == "failed":
            # Update payment status to failed
            PaymentRepository.update_payment_status(
                reference=reference, 
                status="failed",
                transaction_details=transaction_details
            )
            return {"success": False, "status": "failed", "reference": reference}
            
        if transaction_status == "mined" and payment.status != "confirmed":
            # Update payment status to confirmed
            PaymentRepository.update_payment_status(
                reference=reference, 
                status="confirmed",
                transaction_details=transaction_details
            )
            
            # Add credits to user
            user = PaymentRepository.add_credits_to_user(
                user_id=payment.user_id,
                credits=payment.credits_amount
            )
            
            if user:
                return {
                    "success": True,
                    "status": "confirmed",
                    "credits": user.credits,
                    "reference": reference
                }
        
        # Still pending
        return {"success": True, "status": "pending", "reference": reference}
        
    @staticmethod
    def get_user_payments(user_id: int, status: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get all payments for a user, optionally filtered by status
        
        Args:
            user_id: User ID
            status: Optional status filter
            
        Returns:
            List of payment records
        """
        payments = PaymentRepository.get_user_payments(user_id, status)
        
        # Convert to dictionaries
        return [
            {
                "id": p.id,
                "reference": p.reference,
                "status": p.status,
                "credits_amount": p.credits_amount,
                "token_type": p.token_type,
                "token_amount": p.token_amount,
                "created_at": p.created_at.isoformat() if p.created_at else None
            }
            for p in payments
        ]
