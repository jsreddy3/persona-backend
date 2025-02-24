import asyncio
import os
from dotenv import load_dotenv
from openai import AsyncOpenAI
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_fireworks_ai():
    """
    Test the Fireworks AI integration with DeepSeek V3
    """
    # Load environment variables
    load_dotenv()
    
    # Set environment variables directly for this test
    fireworks_api_key = os.getenv("FIREWORKS_API_KEY")
    
    # Create OpenAI client with Fireworks API base
    client = AsyncOpenAI(
        api_key=fireworks_api_key,
        base_url="https://api.fireworks.ai/inference/v1"
    )
    
    # Test message
    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Hello, how are you today?"}
    ]
    
    try:
        logger.info("Sending test request to Fireworks AI DeepSeek V3...")
        
        # Call LLM with Fireworks parameters using OpenAI client
        response = await client.chat.completions.create(
            model="accounts/fireworks/models/deepseek-v3",
            messages=messages,
            temperature=0.6,
            max_tokens=150
        )
        
        # Print response
        logger.info(f"Response received from model: {response.model}")
        logger.info(f"Content: {response.choices[0].message.content}")
        
        return True
    except Exception as e:
        logger.error(f"Error testing Fireworks AI: {str(e)}")
        return False

if __name__ == "__main__":
    # Run the test
    result = asyncio.run(test_fireworks_ai())
    
    if result:
        logger.info("✅ Fireworks AI integration test passed!")
    else:
        logger.error("❌ Fireworks AI integration test failed!") 