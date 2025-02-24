import os
import requests
import base64
from typing import Optional
import logging

logger = logging.getLogger(__name__)

class ImageGenerationService:
    def __init__(self):
        self.api_key = os.getenv("GETIMG_API_KEY")
        if not self.api_key:
            raise ValueError("GETIMG_API_KEY environment variable not set")
            
    def generate_image(
        self,
        prompt: str,
        width: int = 1024,
        height: int = 1024,
        steps: int = 20,
    ) -> Optional[bytes]:
        """
        Generate an image using getimg.ai's SDXL API
        
        Args:
            prompt: Text description of the image to generate (will be truncated to 800 chars)
            width: Image width (default 1024)
            height: Image height (default 1024)
            steps: Number of inference steps (default 20)
        
        Returns:
            Image data as bytes or None if generation failed
        """
        try:
            logger.info("Preparing getimg.ai API request")
            url = "https://api.getimg.ai/v1/stable-diffusion-xl/text-to-image"
            
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
            # Truncate prompt to 800 characters
            truncated_prompt = prompt[:800]
            if len(prompt) > 800:
                logger.info(f"Truncated prompt from {len(prompt)} to 800 characters")
            
            data = {
                "prompt": truncated_prompt,
                "width": width,
                "height": height,
                "steps": steps
            }
            
            logger.info(f"Making API request to {url}")
            response = requests.post(url, headers=headers, json=data)
            
            if response.status_code != 200:
                logger.error(f"API request failed with status {response.status_code}: {response.text}")
                response.raise_for_status()
            
            logger.info("API request successful, decoding image data")
            image_data = base64.b64decode(response.json()["image"])
            logger.info(f"Successfully decoded {len(image_data)} bytes of image data")
            return image_data
            
        except Exception as e:
            logger.error(f"Failed to generate image: {str(e)}", exc_info=True)
            return None
