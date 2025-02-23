import httpx
import os
import logging
from typing import Optional, Dict
from datetime import datetime
from repositories.user_repository import UserRepository
from database.models import User, WorldIDVerification

logger = logging.getLogger(__name__)

class WorldIDService:
    def __init__(self, user_repository: UserRepository):
        self.user_repository = user_repository
        self.app_id = os.getenv("WORLD_ID_APP_ID")
        if not self.app_id:
            raise ValueError("WORLD_ID_APP_ID environment variable not set")

    async def verify_proof(
        self,
        nullifier_hash: str,
        merkle_root: str,
        proof: str,
        verification_level: str,
        action: str,
        language: str = "en"
    ) -> Dict:
        """Verify a World ID proof and create/update user"""
        try:
            # Check for existing verification
            existing = self.user_repository.get_latest_verification(nullifier_hash)
            if existing:
                user = self.user_repository.create_or_update_user(
                    world_id=nullifier_hash,
                    language=language
                )
                return {
                    "success": True,
                    "verification": {
                        "nullifier_hash": existing.nullifier_hash,
                        "merkle_root": existing.merkle_root
                    },
                    "user": {
                        "id": user.id,
                        "world_id": user.world_id,
                        "language": user.language
                    }
                }

            # Prepare verification request
            verify_data = {
                "nullifier_hash": nullifier_hash,
                "merkle_root": merkle_root,
                "proof": proof,
                "verification_level": verification_level,
                "action": action
            }
            
            # Call World ID API
            async with httpx.AsyncClient() as client:
                verify_url = f"https://developer.worldcoin.org/api/v2/verify/{self.app_id}"
                logger.info(f"Verifying with World ID: {nullifier_hash}")
                
                response = await client.post(verify_url, json=verify_data)
                print(f"World ID API response status: {response.status_code}")
                print(f"World ID API response body: {response.text}")
                response.raise_for_status()
                
                # Create/update user and verification
                user = self.user_repository.create_or_update_user(
                    world_id=nullifier_hash,
                    language=language
                )
                
                verification = self.user_repository.create_verification(
                    world_id=nullifier_hash,
                    merkle_root=merkle_root
                )
                
                return {
                    "success": True,
                    "verification": response.json(),
                    "user": {
                        "id": user.id,
                        "world_id": user.world_id,
                        "language": user.language
                    }
                }
                
        except httpx.HTTPError as e:
            logger.error(f"World ID API error: {str(e)}")
            raise ValueError(f"World ID verification failed: {str(e)}")
        except Exception as e:
            logger.error(f"Verification error: {str(e)}")
            raise ValueError(f"Verification failed: {str(e)}")
