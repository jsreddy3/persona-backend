from fastapi import APIRouter, Depends, HTTPException, File, UploadFile, Form
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel
from database.database import get_db
from database.models import User
from services.character_service import CharacterService
from services.image_service import ImageService
from services.image_generation_service import ImageGenerationService
from dependencies.auth import get_current_user
import logging

logger = logging.getLogger(__name__)

router = APIRouter(tags=["characters"])  

# Print routes being registered
logger.info("Registering character routes:")
for route in router.routes:
    logger.info(f"Character route: {route.path} [{','.join(route.methods)}]")

class CharacterCreate(BaseModel):
    name: str
    character_description: str
    greeting: str
    tagline: Optional[str] = None
    photo_url: Optional[str] = None
    attributes: List[str] = []

class CharacterResponse(BaseModel):
    id: int
    name: str
    character_description: str
    greeting: str
    tagline: Optional[str] = ""
    photo_url: Optional[str] = ""
    num_chats_created: int = 0
    num_messages: int = 0
    rating: float = 0.0
    attributes: List[str] = []
    
    class Config:
        orm_mode = True  

class GenerateImageRequest(BaseModel):
    prompt: str
    width: Optional[int] = 1024
    height: Optional[int] = 1024
    steps: Optional[int] = 20

@router.post("/", response_model=CharacterResponse)
async def create_character(
    character: CharacterCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create a new character"""
    try:
        # Create character
        service = CharacterService(db)
        new_character = service.create_character(
            name=character.name,
            character_description=character.character_description,
            greeting=character.greeting,
            tagline=character.tagline,
            photo_url=character.photo_url,
            creator_id=current_user.id,
            attributes=character.attributes
        )
        
        # Generate initial image if none provided
        if not new_character.photo_url:
            try:
                logger.info(f"Starting image generation for character {new_character.id}")
                # Create a prompt combining name and description
                prompt = f"A portrait of {character.name}. {character.character_description}"
                logger.info(f"Using prompt: {prompt}")
                
                # Generate image
                image_gen = ImageGenerationService()
                logger.info("Calling getimg.ai API...")
                image_data = image_gen.generate_image(prompt=prompt)
                
                if image_data:
                    logger.info("Image generated successfully, uploading to Cloudinary...")
                    # Upload to cloudinary
                    image_service = ImageService()
                    url = image_service.upload_character_image(image_data, new_character.id)
                    
                    if url:
                        logger.info(f"Image uploaded successfully, URL: {url}")
                        # Update character
                        new_character = service.update_character_image(new_character.id, url)
                        logger.info("Character photo_url updated in database")
                    else:
                        logger.error("Failed to get URL from Cloudinary upload")
                else:
                    logger.error("Failed to generate image data from getimg.ai")
                
            except Exception as e:
                logger.error(f"Failed to generate initial character image: {str(e)}", exc_info=True)
                # Continue without image if generation fails
                pass
        
        # Create initial conversation
        try:
            from services.conversation_service import ConversationService
            conv_service = ConversationService(db)
            conv_service.create_conversation(
                character_id=new_character.id,
                user_id=current_user.id
            )
        except Exception as e:
            logger.error(f"Failed to create initial conversation: {str(e)}")
            # Continue even if conversation creation fails
            pass
        
        return new_character
        
    except Exception as e:
        logger.error(f"Error creating character: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/list/popular", response_model=List[CharacterResponse])
async def get_popular_characters(
    db: Session = Depends(get_db)
):
    """Get list of popular characters"""
    try:
        service = CharacterService(db)
        return service.get_popular_characters()
    except Exception as e:
        logger.error(f"Error getting popular characters: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/detail/{character_id}", response_model=CharacterResponse)
async def get_character(
    character_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get character details by ID"""
    try:
        service = CharacterService(db)
        character = service.get_character(character_id)  
        if not character:
            raise HTTPException(status_code=404, detail="Character not found")
        return character
    except Exception as e:
        logger.error(f"Error getting character {character_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{character_id}/stats")
async def get_character_stats(
    character_id: int,
    db: Session = Depends(get_db)
):
    """Get character stats"""
    try:
        service = CharacterService(db)
        stats = service.get_stats(character_id)
        return stats
    except Exception as e:
        logger.error(f"Error getting character stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/{character_id}/image")
async def upload_character_image(
    character_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Upload a character's image"""
    try:
        # Print debug info
        print(f"Received file: {file.filename}")
        
        # Read file
        contents = await file.read()
        print(f"Read {len(contents)} bytes")
        
        # Upload image
        image_service = ImageService()
        url = image_service.upload_character_image(contents, character_id)
        if not url:
            raise HTTPException(status_code=400, detail="Failed to upload image")
            
        # Update character
        service = CharacterService(db)
        character = service.update_character_image(character_id, url)
        if not character:
            raise HTTPException(status_code=400, detail="Failed to update character")
            
        return {"photo_url": url}
        
    except Exception as e:
        logger.error(f"Error uploading character image: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/{character_id}/generate-image")
async def generate_character_image(
    character_id: int,
    request: GenerateImageRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Generate an AI image for a character"""
    try:
        # Generate image
        image_gen = ImageGenerationService()
        image_data = image_gen.generate_image(
            prompt=request.prompt,
            width=request.width,
            height=request.height,
            steps=request.steps
        )
        
        if not image_data:
            raise HTTPException(status_code=400, detail="Failed to generate image")
            
        # Upload to cloudinary
        image_service = ImageService()
        url = image_service.upload_character_image(image_data, character_id)
        if not url:
            raise HTTPException(status_code=400, detail="Failed to upload generated image")
            
        # Update character
        service = CharacterService(db)
        character = service.update_character_image(character_id, url)
        if not character:
            raise HTTPException(status_code=400, detail="Failed to update character")
            
        return {"photo_url": url}
        
    except Exception as e:
        logger.error(f"Error generating character image: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/creator/{world_id}")
async def get_creator_characters(
    world_id: str,
    db: Session = Depends(get_db)
):
    """Get all characters created by a user with their stats"""
    try:
        # First get the user by world_id
        user = db.query(User).filter(User.world_id == world_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
            
        service = CharacterService(db)
        characters = service.get_creator_characters(user.id)
        
        # Get stats for each character
        characters_with_stats = []
        for character in characters:
            stats = service.get_stats(character.id)
            characters_with_stats.append({
                **stats,
                "character_description": character.character_description,
                "greeting": character.greeting,
                "tagline": character.tagline,
                "photo_url": character.photo_url,
                "attributes": character.attributes,
                "created_at": character.created_at,
                "updated_at": character.updated_at
            })
            
        return characters_with_stats
    except Exception as e:
        logger.error(f"Error getting creator's characters: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/search", response_model=List[CharacterResponse], include_in_schema=True)
@router.get("/search/", response_model=List[CharacterResponse], include_in_schema=False)
async def search_characters(
    query: str,
    page: int = 1,
    per_page: int = 10,
    db: Session = Depends(get_db)
):
    """Search characters by name, tagline, or description"""
    logger.info(f"Searching characters with query: {query}")
    try:
        character_service = CharacterService(db)
        characters = character_service.search_characters(query, page, per_page)
        return characters
    except Exception as e:
        logger.error(f"Error searching characters: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to search characters")
