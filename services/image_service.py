import os
import cloudinary
import cloudinary.uploader
from typing import Optional
import mimetypes
import logging

logger = logging.getLogger(__name__)

class ImageService:
    def __init__(self):
        # Configure Cloudinary
        cloudinary.config(
            cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
            api_key=os.getenv("CLOUDINARY_API_KEY"),
            api_secret=os.getenv("CLOUDINARY_API_SECRET"),
            secure=True
        )
    
    def upload_character_image(self, image_data: bytes, character_id: int) -> Optional[str]:
        """
        Upload a character image to Cloudinary
        Returns the URL of the uploaded image
        """
        try:
            # Simple check for image data by looking at first few bytes
            image_signatures = {
                b'\xFF\xD8\xFF': 'image/jpeg',
                b'\x89PNG\r\n': 'image/png',
                b'GIF87a': 'image/gif',
                b'GIF89a': 'image/gif',
                b'RIFF': 'image/webp'  # WEBP starts with 'RIFF'
            }
            
            is_valid_image = False
            for signature, mime_type in image_signatures.items():
                if image_data.startswith(signature):
                    is_valid_image = True
                    break
                    
            if not is_valid_image:
                raise ValueError("Invalid image file format")
            
            # Upload to cloudinary with optimization
            result = cloudinary.uploader.upload(
                image_data,
                public_id=f"character_{character_id}",
                folder="characters",
                overwrite=True,
                resource_type="image",
                transformation=[
                    {"width": 1024, "height": 1024, "crop": "fill"},
                    {"quality": "auto:good"},
                    {"fetch_format": "auto"}
                ]
            )
            
            return result['secure_url']
            
        except Exception as e:
            logger.error(f"Failed to upload image: {str(e)}")
            return None
    
    def delete_character_image(self, character_id: int) -> bool:
        """Delete a character's image from Cloudinary"""
        try:
            result = cloudinary.uploader.destroy(f"characters/character_{character_id}")
            return result.get('result') == 'ok'
        except Exception as e:
            logger.error(f"Failed to delete image: {str(e)}")
            return False
