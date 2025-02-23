import os
import cloudinary
import cloudinary.uploader
from typing import Optional
import magic
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
            # Verify file type
            file_type = magic.from_buffer(image_data, mime=True)
            if not file_type.startswith('image/'):
                raise ValueError(f"Invalid file type: {file_type}")
            
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
