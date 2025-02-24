from typing import List, Dict, Optional
from pydantic import BaseModel
from litellm import completion, acompletion
import os
import logging
from dotenv import load_dotenv
from database.models import Message

logger = logging.getLogger(__name__)

class LLMConfig(BaseModel):
    model: str = "gpt-4o-mini"
    temperature: float = 0.7
    max_tokens: int = 150
    window_size: int = 12  # Number of message pairs (user + assistant) to keep

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

    def _get_windowed_messages(
        self,
        system_message: str,
        conversation_history: List[Message],
        new_message: str
    ) -> List[Dict[str, str]]:
        """
        Get windowed conversation messages, keeping system prompt and last N pairs
        """
        messages = [{"role": "system", "content": system_message}]
        
        # Calculate how many message pairs to keep
        window_size = self.config.window_size * 2  # Multiply by 2 for user + assistant pairs
        
        # If we have more messages than our window, slice the history
        if len(conversation_history) > window_size:
            conversation_history = conversation_history[-window_size:]
        
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
        
        # Log windowed messages
        logger.info(f"Using {len(messages)-1} messages from history (window_size={self.config.window_size} pairs)")
        for i, msg in enumerate(messages):
            logger.info(f"Message {i}: role={msg['role']}, content={msg['content'][:50]}...")
            
        return messages

    async def process_message(
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
            # Get windowed messages
            messages = self._get_windowed_messages(system_message, conversation_history, new_message)
            
            logger.info(f"Sending request to LLM with {len(messages)} messages")
            
            # Call LLM with minimal parameters
            response = await acompletion(
                model=self.config.model,
                messages=messages,
                temperature=self.config.temperature,
                max_tokens=self.config.max_tokens
            )
            
            # Extract and return response
            if not response or not response.choices or not response.choices[0].message:
                logger.error("Received invalid response from LLM")
                raise RuntimeError("Invalid response from language model")
                
            return response.choices[0].message.content
            
        except Exception as e:
            logger.error(f"Error in LLM service: {str(e)}")
            raise RuntimeError(f"Failed to process message: {str(e)}")
            
    async def stream_message(
        self,
        system_message: str,
        conversation_history: List[Message],
        new_message: str,
    ):
        """
        Stream a message response token by token
        Args:
            system_message: The character's system prompt
            conversation_history: List of previous messages
            new_message: The user's new message
        Yields:
            Tokens from the AI's response
        """
        try:
            # Get windowed messages
            messages = self._get_windowed_messages(system_message, conversation_history, new_message)
            
            logger.info(f"Starting streaming request to LLM with {len(messages)} messages")
            
            # Call LLM with streaming
            response = await acompletion(
                model=self.config.model,
                messages=messages,
                temperature=self.config.temperature,
                max_tokens=self.config.max_tokens,
                stream=True
            )
            
            async for chunk in response:
                if chunk and chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
                    
        except Exception as e:
            logger.error(f"Error in LLM streaming service: {str(e)}")
            raise RuntimeError(f"Failed to stream message: {str(e)}")

    def update_config(self, new_config: LLMConfig):
        """Update the LLM configuration"""
        self.config = new_config