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
            prompt: Text description of the image to generate
            width: Image width (default 1024)
            height: Image height (default 1024)
            steps: Number of inference steps (default 20)
        
        Returns:
            Image data as bytes or None if generation failed
        """
        try:
            url = "https://api.getimg.ai/v1/stable-diffusion-xl/text-to-image"
            
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
            data = {
                "prompt": prompt,
                "width": width,
                "height": height,
                "steps": steps
            }

            response = requests.post(url, headers=headers, json=data)
            response.raise_for_status()
            
            # The API returns base64 encoded image data
            return base64.b64decode(response.json()['image'])
            
        except Exception as e:
            logger.error(f"Failed to generate image: {str(e)}")
            return None
