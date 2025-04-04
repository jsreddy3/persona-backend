from typing import Dict, Optional, Tuple
import logging
import os
from services.llm_service import LLMService, LLMConfig

logger = logging.getLogger(__name__)

class ModerationResult:
    """Result of content moderation check"""
    def __init__(self, approved: bool, reason: str = "", category: str = ""):
        self.approved = approved
        self.reason = reason
        self.category = category

class ModerationService:
    """
    Service for moderating user-generated content using LLM
    Ensures content follows community guidelines
    """
    
    def __init__(self, llm_service: Optional[LLMService] = None):
        """Initialize the moderation service"""
        # Use a GPT-4o-mini model specifically for moderation
        moderation_config = LLMConfig(
            model="accounts/fireworks/models/deepseek-v3", 
            temperature=0.1,  # Low temperature for more consistent results
            max_tokens=200
        )
        
        # Create LLM service or use provided one
        self.llm_service = llm_service or LLMService(moderation_config)
        logger.info("Moderation service initialized")
        
    async def moderate_character(
        self,
        name: str,
        character_description: str,
        greeting: str,
        tagline: Optional[str] = None,
    ) -> ModerationResult:
        """
        Moderate a character's content before saving to database
        
        Args:
            name: Character name
            character_description: Character description
            greeting: Character greeting message
            tagline: Optional character tagline
            
        Returns:
            ModerationResult with approval status and reason
        """
        # Combine all character info for context
        character_info = f"""
Name: {name}
Description: {character_description}
Greeting: {greeting}
Tagline: {tagline or ''}
"""
        
        # System prompt explaining moderation guidelines
        system_prompt = """
You are a content moderator for a character-based AI chat platform. Your job is to review character descriptions
and determine if they violate our community guidelines.

MODERATION GUIDELINES:
- ALLOW sensual descriptions and flirtatious content (as long as it's not explicit)
- ALLOW fictional violence, mild profanity, and mature themes when appropriate
- ALLOW things that are objectifying, focus excessively and even problematically, just nothing extremely explicit
- REJECT extreme racist or hateful content
- REJECT extremely sexist or discriminatory content
- REJECT content that explicitly describes nudity or sexual acts
- REJECT content that promotes illegal activities
- REJECT content likely to generate problematic AI images

DEFAULT TO APPROVING content unless it clearly violates the guidelines. We want to allow creative expression and
mature themes while ensuring a safe environment.
"""

        user_prompt = f"""
Please review this character submission and determine if it should be approved or rejected:

{character_info}

Provide a structured judgment following our guidelines.
"""

        # Define the JSON schema for the response
        json_schema = {
            "type": "object",
            "properties": {
                "approved": {
                    "type": "boolean",
                    "description": "Whether the character should be approved (true) or rejected (false)"
                },
                "reason": {
                    "type": "string",
                    "description": "Explanation for why the character was approved or rejected"
                },
                "category": {
                    "type": "string",
                    "enum": ["hate_speech", "sexual_content", "violence", "illegal_activity", "other", "none"],
                    "description": "Category of violation if rejected, 'none' if approved"
                }
            },
            "required": ["approved", "reason", "category"]
        }

        try:
            # Use the structured output method from LLM service
            response = await self.llm_service.process_structured_output(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                json_schema=json_schema,
                model="accounts/fireworks/models/deepseek-v3"  # Use GPT-4o-mini equivalent
            )
            
            # Create result from response
            result = ModerationResult(
                approved=response["approved"],
                reason=response["reason"],
                category=response["category"]
            )
            
            if not result.approved:
                logger.info(f"Character '{name}' rejected: {result.reason} (Category: {result.category})")
            else:
                logger.debug(f"Character '{name}' approved")
                
            return result
            
        except Exception as e:
            logger.error(f"Error during character moderation: {str(e)}")
            # Default to approved if moderation fails (with logging)
            logger.warning("Defaulting to approved due to moderation error")
            return ModerationResult(
                approved=True, 
                reason="Approved by default due to moderation service error",
                category="none"
            )