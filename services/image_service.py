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
            logger.info(f"Starting image upload for character {character_id}")
            # Simple check for image data by looking at first few bytes
            image_signatures = {
                b'\xFF\xD8\xFF': 'image/jpeg',
                b'\x89PNG\r\n': 'image/png',
                b'GIF87a': 'image/gif',
                b'GIF89a': 'image/gif',
                b'RIFF': 'image/webp'  # WEBP starts with 'RIFF'
            }
            
            is_valid_image = False
            detected_type = None
            for signature, mime_type in image_signatures.items():
                if image_data.startswith(signature):
                    is_valid_image = True
                    detected_type = mime_type
                    break
                    
            if not is_valid_image:
                logger.error(f"Invalid image format. First few bytes: {image_data[:20].hex()}")
                raise ValueError("Invalid image file format")
            
            logger.info(f"Valid image detected of type: {detected_type}")
            
            # Upload to cloudinary with optimization
            logger.info("Starting Cloudinary upload...")
            result = cloudinary.uploader.upload(
                image_data,
                public_id=f"character_{character_id}",
                folder="characters",
                overwrite=True,
                resource_type="image",
                transformation=[
                    {"quality": "auto:good"},
                    {"fetch_format": "auto"}
                ]
            )
            
            if 'secure_url' in result:
                url = result['secure_url']
                logger.info(f"Upload successful. URL: {url}")
                return url
            else:
                logger.error(f"Upload failed. Result: {result}")
                return None
                
        except Exception as e:
            logger.error(f"Failed to upload image: {str(e)}", exc_info=True)
            return None
    
    def delete_character_image(self, character_id: int) -> bool:
        """Delete a character's image from Cloudinary"""
        try:
            result = cloudinary.uploader.destroy(f"characters/character_{character_id}")
            return result.get('result') == 'ok'
        except Exception as e:
            logger.error(f"Failed to delete image: {str(e)}")
            return False
