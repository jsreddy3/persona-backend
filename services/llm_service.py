from typing import List, Dict, Optional
from pydantic import BaseModel
from litellm import completion
import os
import logging
from dotenv import load_dotenv
from database.models import Message

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class LLMConfig(BaseModel):
    model: str = "gpt-4o-mini"
    temperature: float = 0.7
    max_tokens: int = 150

class LLMResponse(BaseModel):
    content: str
    model: str
    completion_id: str

class LLMService:
    def __init__(self, config: Optional[LLMConfig] = None):
        self.config = config or LLMConfig()
        # Load environment variables
        load_dotenv()
        
        # Validate API key
        if not os.getenv("OPENAI_API_KEY"):
            logger.error("OPENAI_API_KEY not found in environment variables")
            raise ValueError("OPENAI_API_KEY not set")

    def process_message(
        self,
        system_message: str,
        conversation_history: List[Message],
        new_message: str,
    ) -> str:
        """
        Process a message in the context of a conversation with a character
        Args:
            system_message: The character's system prompt
            conversation_history: List of previous messages
            new_message: The user's new message
        Returns:
            The AI's response
        """
        try:
            # Build messages array for LLM
            messages = [
                {"role": "system", "content": system_message}
            ]
            
            # Add conversation history
            for msg in conversation_history:
                messages.append({
                    "role": msg.role,
                    "content": msg.content
                })
            
            # Add new message
            messages.append({
                "role": "user",
                "content": new_message
            })
            
            # Log messages being sent
            logger.info(f"Total messages being sent to LLM: {len(messages)}")
            for i, msg in enumerate(messages):
                logger.info(f"Message {i}: role={msg['role']}, content={msg['content'][:50]}...")
            
            logger.info(f"Sending request to LLM with {len(messages)} messages")
            
            # Call LLM
            response = completion(
                model=self.config.model,
                messages=messages,
                temperature=self.config.temperature,
                max_tokens=self.config.max_tokens,
                api_key=os.getenv("OPENAI_API_KEY"),
                stream=False
            )
            
            # Extract and return response
            if not response or not response.choices or not response.choices[0].message:
                logger.error("Received invalid response from LLM")
                raise RuntimeError("Invalid response from language model")
                
            return response.choices[0].message.content
            
        except Exception as e:
            logger.error(f"Error in LLM service: {str(e)}")
            raise RuntimeError(f"Failed to process message: {str(e)}")
            
    def update_config(self, new_config: LLMConfig):
        """Update the LLM configuration"""
        self.config = new_config