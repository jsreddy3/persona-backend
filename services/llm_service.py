from typing import List, Dict, Optional
from pydantic import BaseModel
from openai import AsyncOpenAI
import os
import logging
from dotenv import load_dotenv
from database.models import Message
from services.timing import time_network_operation

logger = logging.getLogger(__name__)

class LLMConfig(BaseModel):
    model: str = "accounts/fireworks/models/deepseek-v3"  # Correct format for Fireworks AI
    temperature: float = 0.6
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
        
        # Validate API key - only need Fireworks API key now
        if not os.getenv("FIREWORKS_API_KEY"):
            logger.error("FIREWORKS_API_KEY not found in environment variables")
            raise ValueError("FIREWORKS_API_KEY not set")
        
        # Create OpenAI client with Fireworks API base
        self.client = AsyncOpenAI(
            api_key=os.getenv("FIREWORKS_API_KEY"),
            base_url="https://api.fireworks.ai/inference/v1"
        )
        
        # logger.info(f"LLM Service initialized with model: {self.config.model}")

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
        # logger.info(f"Using {len(messages)-1} messages from history (window_size={self.config.window_size} pairs)")
        # for i, msg in enumerate(messages):
        #     logger.info(f"Message {i}: role={msg['role']}, content={msg['content'][:50]}...")
            
        return messages

    # @time_network_operation
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
            
            # logger.info(f"Sending request to LLM with {len(messages)} messages")
            
            # Call LLM with Fireworks parameters using OpenAI client
            response = await self.client.chat.completions.create(
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
            
    # @time_network_operation
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
            
            # logger.info(f"Starting streaming request to LLM with {len(messages)} messages")
            
            # Call LLM with streaming and Fireworks parameters using OpenAI client
            response = await self.client.chat.completions.create(
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
        
    async def process_single_prompt(
        self,
        system_prompt: str,
        user_prompt: str,
    ) -> str:
        """
        Process a single prompt without conversation context
        Args:
            system_prompt: The system instructions
            user_prompt: The user's prompt
        Returns:
            The LLM's response
        """
        try:
            # Create messages array with system and user messages
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]
            
            # Call LLM with Fireworks parameters using OpenAI client
            response = await self.client.chat.completions.create(
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
            logger.error(f"Error in LLM service single prompt: {str(e)}")
            raise RuntimeError(f"Failed to process prompt: {str(e)}")
            
    async def process_structured_output(
        self,
        system_prompt: str,
        user_prompt: str,
        json_schema: Dict,
        model: str = None,
        strict: bool = True
    ) -> Dict:
        """
        Process a prompt and receive a structured JSON output conforming to the provided schema
        Args:
            system_prompt: The system instructions
            user_prompt: The user's prompt
            json_schema: JSON schema that defines the expected output format
            model: Optional model override for this request
            strict: Whether to enforce strict schema compliance
        Returns:
            Parsed JSON response conforming to the schema
        """
        try:
            # Create messages array with system and user messages
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]
            
            # Set up the response format for structured output
            response_format = {
                "type": "json_object",
                "schema": json_schema
            }
            
            # Use a specific model if provided, otherwise use the configured model
            model_to_use = model or self.config.model
            
            # Call LLM with structured output parameters
            response = await self.client.chat.completions.create(
                model=model_to_use,
                messages=messages,
                temperature=self.config.temperature,
                max_tokens=self.config.max_tokens,
                response_format=response_format
            )
            
            # Extract and parse the response
            if not response or not response.choices or not response.choices[0].message:
                logger.error("Received invalid response from LLM")
                raise RuntimeError("Invalid response from language model")
                
            content = response.choices[0].message.content
            
            # Parse the JSON response
            import json
            try:
                parsed_response = json.loads(content)
                return parsed_response
            except json.JSONDecodeError:
                logger.error(f"Failed to parse JSON response: {content}")
                raise RuntimeError("LLM response was not valid JSON")
            
        except Exception as e:
            logger.error(f"Error in LLM service structured output: {str(e)}")
            raise RuntimeError(f"Failed to process structured output: {str(e)}")