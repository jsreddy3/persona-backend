from fastapi import APIRouter, Depends, HTTPException, File, UploadFile, Form, Request
from sqlalchemy.orm import Session
from typing import List, Optional, Dict
from pydantic import BaseModel
from database.database import get_db, SessionLocal
from database.models import User, Character
from services.character_service import CharacterService
from services.image_service import ImageService
from services.image_generation_service import ImageGenerationService
from services.moderation_service import ModerationService
from dependencies.auth import get_current_user
from database.db_utils import batch_update, increment_counter, deduct_user_credits
import logging
import datetime
import os
import random

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
    character_types: List[str] = []

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
    created_at: str
    updated_at: str
    language: str
    character_types: List[str] = []
    class Config:
        orm_mode = True

    @classmethod
    def from_orm(cls, obj):
        # Convert datetime to string in ISO format
        if isinstance(obj.created_at, datetime.datetime):
            obj.created_at = obj.created_at.isoformat()
        if isinstance(obj.updated_at, datetime.datetime):
            obj.updated_at = obj.updated_at.isoformat()
        return super().from_orm(obj)

class GenerateImageRequest(BaseModel):
    prompt: str
    width: Optional[int] = 1024
    height: Optional[int] = 1024
    steps: Optional[int] = 20

@router.post("/", response_model=CharacterResponse)
async def create_character(
    character: CharacterCreate,
    request: Request,
    current_user: User = Depends(get_current_user)
):
    """Create a new character"""
    try:
        # Keep language-specific attributes for localization
        all_attributes = {
            "en": [
                "chaotic", "mischievous", "unpredictable", "sarcastic", 
                "provocative", "absurd", "irreverent", "rebellious", 
                "dramatic", "exaggerated", "bizarre", "outrageous", 
                "nonsensical", "contradictory", "inflammatory", "ridiculous", 
                "eccentric", "obnoxious", "confusing", "irritating", 
                "controversial", "unhinged", "deceptive", "bamboozling",
                "eye-rolling", "cringe-worthy", "face-palming", "mind-boggling",
                "rage-inducing", "insufferable"
            ],
            "es": [
                "caótico", "travieso", "impredecible", "sarcástico", 
                "provocativo", "absurdo", "irreverente", "rebelde", 
                "dramático", "exagerado", "bizarro", "escandaloso", 
                "sin sentido", "contradictorio", "inflamatorio", "ridículo", 
                "excéntrico", "odioso", "confuso", "irritante", 
                "controversial", "desquiciado", "engañoso", "desconcertante",
                "exasperante", "vergonzoso", "indignante", "alucinante",
                "enfurecedor", "insufrible"
            ],
            "pt": [
                "caótico", "travesso", "imprevisível", "sarcástico", 
                "provocativo", "absurdo", "irreverente", "rebelde", 
                "dramático", "exagerado", "bizarro", "escandaloso", 
                "sem sentido", "contraditório", "inflamatório", "ridículo", 
                "excêntrico", "odioso", "confuso", "irritante", 
                "controverso", "descontrolado", "enganoso", "desconcertante",
                "exaspérant", "constrangedor", "indignante", "alucinante",
                "enfurecedor", "insuportável"
            ],
            "id": [
              "kacau", "nakal", "tidak terduga", "sarkastik",
              "provokatif", "absurd", "tidak sopan", "memberontak",
              "dramatis", "berlebihan", "aneh", "mengejutkan",
              "tidak masuk akal", "kontradiktif", "memicu", "konyol",
              "eksentrik", "menyebalkan", "membingungkan", "mengganggu",
              "kontroversial", "tidak waras", "menipu", "membodohi",
              "memutar mata", "memalukan", "menggelengkan kepala", "membingungkan pikiran",
              "memicu kemarahan", "tak tertahankan"
            ],
            "ko": [
              "혼란스러운", "장난스러운", "예측할 수 없는", "비꼬는",
              "도발적인", "황당한", "불경스러운", "반항적인",
              "극적인", "과장된", "기괴한", "충격적인",
              "무의미한", "모순적인", "선동적인", "우스꽝스러운",
              "괴짜의", "불쾌한", "혼란스러운", "짜증나는",
              "논란이 많은", "제정신이 아닌", "기만적인", "혼란스럽게 하는",
              "눈을 굴리게 하는", "민망한", "얼굴을 감싸게 하는", "난해한",
              "분노를 유발하는", "참을 수 없는"
            ],
            "ja": [
              "混沌とした", "いたずら好きな", "予測不能な", "皮肉な",
              "挑発的な", "不条理な", "不敬な", "反抗的な",
              "劇的な", "大げさな", "奇妙な", "常軌を逸した",
              "ナンセンスな", "矛盾した", "扇動的な", "ばかげた",
              "風変わりな", "不快な", "混乱させる", "いらだたせる",
              "物議を醸す", "支離滅裂な", "欺瞞的な", "困惑させる",
              "目を回させる", "恥ずかしい", "顔を覆いたくなる", "理解を超える",
              "激怒させる", "耐え難い"
            ],
            "fr": [
              "chaotique", "espiègle", "imprévisible", "sarcastique",
              "provocateur", "absurde", "irrévérencieux", "rebelle",
              "dramatique", "exagéré", "bizarre", "scandaleux",
              "insensé", "contradictoire", "incendiaire", "ridicule",
              "excentrique", "odieux", "déroutant", "irritant",
              "controversé", "déséquilibré", "trompeur", "déconcertant",
              "exaspérant", "embarrassant", "consternant", "ahurissant",
              "enrageant", "insupportable"
            ],
            "de": [
              "chaotisch", "schelmisch", "unberechenbar", "sarkastisch",
              "provokativ", "absurd", "respektlos", "rebellisch",
              "dramatisch", "übertrieben", "bizarr", "unerhört",
              "unsinnig", "widersprüchlich", "aufwiegelnd", "lächerlich",
              "exzentrisch", "unausstehlich", "verwirrend", "ärgerlich",
              "umstritten", "durchgeknallt", "täuschend", "verblüffend",
              "augenrollend", "peinlich", "fassungslos machend", "verblüffend",
              "wutentfachend", "unerträglich"
            ],
            "zh": [
              "混乱的", "淘气的", "不可预测的", "讽刺的",
              "挑衅的", "荒谬的", "不敬的", "叛逆的",
              "戏剧性的", "夸张的", "怪异的", "离谱的",
              "荒唐的", "矛盾的", "煽动性的", "可笑的",
              "古怪的", "令人讨厌的", "令人困惑的", "恼人的",
              "有争议的", "失控的", "欺骗性的", "令人迷惑的",
              "令人翻白眼的", "令人尴尬的", "令人捂脸的", "令人费解的",
              "激怒人的", "难以忍受的"
            ],
            "hi": [
              "अराजक", "शरारती", "अप्रत्याशित", "व्यंग्यात्मक", 
              "उकसाने वाला", "बेतुका", "अनादरपूर्ण", "विद्रोही", 
              "नाटकीय", "अतिरंजित", "विचित्र", "अनोखा", 
              "बेमतलब", "विरोधाभासी", "भड़काऊ", "हास्यास्पद", 
              "विलक्षण", "नफरत योग्य", "भ्रमित करने वाला", "चिढ़ाने वाला", 
              "विवादास्पद", "बेकाबू", "धोखेबाज", "दिग्भ्रमित करने वाला",
              "आँखें घुमाने वाला", "शर्मनाक", "चेहरा ढकने वाला", "दिमाग हिला देने वाला",
              "क्रोध उत्पन्न करने वाला", "असहनीय"
            ],
            "sw": [
              "vurugu", "uchokozi", "isiyotabirika", "dhihaka", 
              "uchochezi", "upuuzi", "dharau", "uasi", 
              "mikasi", "kupiga chuku", "ajabu", "kichekesho", 
              "isiyomaana", "kinzani", "kuchochea", "dhihaka", 
              "kisirani", "kuchukiza", "kuchanganya", "kusumbua", 
              "utata", "isiyotarajiwa", "udanganyifu", "kurubuni",
              "kuudhi", "aibu", "kusikitisha", "kufadhaisha",
              "kukasirika", "isiyovumilika"
            ]
        }
        
        # Get language from request header
        language = request.headers.get("accept-language", "en").split(",")[0].split("-")[0].lower()
        language = language if language in all_attributes else "en"
        user_id = current_user.id
        
        # STEP 1: Validate character data and perform moderation check
        # Use a single database session for initial validation and checks
        db_validate = next(get_db())
        
        character_model = None
        character_data = None
        
        try:
            # Validate inputs
            service = CharacterService(db_validate)
            moderation_service = ModerationService()
            
            # Check for profanity or offensive content (don't hold DB connection during API call)
            character_data = {
                "name": character.name,
                "description": character.character_description,
                "greeting": character.greeting,
                "tagline": character.tagline or "",
                "language": language,
                "creator_id": user_id,
                "attributes": character.attributes,
                "character_types": character.character_types,
                "photo_url": character.photo_url or ""
            }
            
            # We don't need to commit anything yet, just prepare the data
        finally:
            # Close the validation connection before external API calls
            db_validate.close()
        
        # STEP 2: Perform moderation check without holding a DB connection
        # This is an external API call that could take time
        moderation_result = await moderation_service.check_content([
            character_data["name"],
            character_data["description"],
            character_data["greeting"],
            character_data["tagline"]
        ])
        
        if not moderation_result["approved"]:
            # Failed moderation check
            raise ValueError(f"Character content violates content policy: {moderation_result['reason']}")

        # STEP 3: Create the character in the database with all data
        db_create = next(get_db())
        try:
            # Create a new service with the write connection
            create_service = CharacterService(db_create)
            
            # Create character in a single transaction
            character_model = create_service.create_character(
                name=character_data["name"],
                character_description=character_data["description"],
                greeting=character_data["greeting"],
                tagline=character_data["tagline"],
                photo_url=character_data["photo_url"],
                creator_id=character_data["creator_id"],
                language=character_data["language"],
                attributes=character_data["attributes"],
                character_types=character_data["character_types"]
            )
            
            # Generate a system message using our language-specific attributes
            attributes_list = all_attributes.get(language, all_attributes["en"])
            character_attributes = character.attributes or random.sample(attributes_list, 3)
            
            # Set system message using character data and generated details
            system_message = f"""You are {character.name}. {character.character_description}
            
Your traits are: {', '.join(character_attributes)}

Additional guidelines:
- Stay true to your character description
- Be conversational and engaging
- Keep your messages concise"""

            # Add the system message in the same transaction
            create_service.repository.update_system_message(character_model.id, system_message)
            
            # Commit all changes in one transaction
            db_create.commit()
            
            return character_model
        except Exception as db_error:
            db_create.rollback()
            logger.error(f"Database error creating character: {str(db_error)}")
            raise db_error
        finally:
            # Ensure connection is closed
            db_create.close()
    except ValueError as e:
        logger.error(f"Validation error creating character: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error creating character: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/list/popular", response_model=List[CharacterResponse])
async def get_popular_characters(
    request: Request,
    page: int = 1,
    per_page: int = 10,
    language: str = '',
    db: Session = Depends(get_db)
):
    """Get list of popular characters with pagination"""
    try:
        service = CharacterService(db)
        # Get language from request header
        language = request.headers.get("accept-language", "en").split(",")[0].split("-")[0].lower()
        logger.info(f"Getting popular characters for language: {language}, page: {page}, per_page: {per_page}")
        return service.get_popular_characters(language=language, page=page, per_page=per_page)
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
    request: Request,
    db: Session = Depends(get_db)
):
    """Get all characters created by a user with their stats"""
    try:
        # First get the user by world_id
        user = db.query(User).filter(User.world_id == world_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
            
        service = CharacterService(db)
        # Get language from request header
        language = request.headers.get("accept-language", "en").split(",")[0].split("-")[0].lower()
        characters = service.get_creator_characters(user.id, language=language)
        
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
                "updated_at": character.updated_at,
                "language": character.language
            })
            
        return characters_with_stats
    except Exception as e:
        logger.error(f"Error getting creator's characters: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/search/", response_model=List[CharacterResponse])
async def search_characters(
    request: Request,
    query: str = '',
    page: int = 1,
    per_page: int = 10,
    db: Session = Depends(get_db)
):
    """Search characters by name, tagline, or description"""
    logger.info(f"Searching characters with query: {query}")
    try:
        character_service = CharacterService(db)
        # Get language from request header
        language = request.headers.get("accept-language", "en").split(",")[0].split("-")[0].lower()
        characters = character_service.search_characters(query.strip(), page, per_page, language=language)
        return characters
    except Exception as e:
        logger.error(f"Error searching characters: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to search characters")

@router.get("/ping")
async def ping():
    """Diagnostic endpoint to check latency"""
    return {
        "timestamp": datetime.datetime.now().isoformat(),
        "region": os.environ.get("HEROKU_REGION", "unknown")
    }

@router.get("/diagnose")
async def diagnose(db: Session = Depends(get_db)):
    """Diagnostic endpoint to check database and API latency"""
    start_time = datetime.datetime.now()
    
    # Test DB connection
    db_connect_start = datetime.datetime.now()
    try:
        # Get PostgreSQL server location and timezone
        db_location = None
        db_version = None
        try:
            db_timezone = db.execute("SHOW timezone").scalar()
            db_version = db.execute("SELECT version()").scalar()
            # Get the connection information
            connection_info = db.execute("SELECT inet_server_addr(), inet_server_port()").first()
            if connection_info:
                db_location = f"{connection_info[0]}:{connection_info[1]}"
        except:
            db_timezone = "unknown"
            
        # Simple query to test connection
        db.execute("SELECT 1").first()
        db_connect_time = (datetime.datetime.now() - db_connect_start).total_seconds()
    except Exception as e:
        db_connect_time = -1
        db_timezone = "error"
        db_location = None
        db_version = None
        logger.error(f"DB connection error: {str(e)}")
    
    # Test simple query
    query_start = datetime.datetime.now()
    try:
        # Get count of characters as a simple test query
        count = db.query(Character).count()
        query_time = (datetime.datetime.now() - query_start).total_seconds()
    except Exception as e:
        count = -1
        query_time = -1
        logger.error(f"Query error: {str(e)}")
    
    # Get pool status if possible
    pool_stats = {}
    try:
        from sqlalchemy import inspect
        inspector = inspect(db.bind)
        if hasattr(inspector, 'pool'):
            pool = inspector.pool
            pool_stats = {
                "pool_size": getattr(pool, 'size', None),
                "checkedin": getattr(pool, 'checkedin', None),
                "checkedout": getattr(pool, 'checkedout', None),
                "overflow": getattr(pool, 'overflow', None)
            }
    except Exception as e:
        logger.error(f"Error getting pool stats: {str(e)}")
    
    total_time = (datetime.datetime.now() - start_time).total_seconds()
    
    return {
        "timestamp": start_time.isoformat(),
        "region": os.environ.get("FLY_REGION", "unknown"),
        "machine": os.environ.get("FLY_MACHINE_ID", "unknown"),
        "db_connect_time_ms": round(db_connect_time * 1000, 2),  # ms
        "query_time_ms": round(query_time * 1000, 2),  # ms
        "total_time_ms": round(total_time * 1000, 2),  # ms
        "character_count": count,
        "db_timezone": db_timezone,
        "db_location": db_location,
        "db_version": db_version,
        "pool_stats": pool_stats
    }

@router.get("/group-by-type", response_model=Dict[str, List[CharacterResponse]])
async def get_characters_grouped_by_type(
    request: Request,
    db: Session = Depends(get_db)
):
    """Get characters grouped by type"""
    try:
        service = CharacterService(db)
        # Get language from request header
        language = request.headers.get("accept-language", "en").split(",")[0].split("-")[0].lower()
        characters = service.get_characters_grouped_by_type(language=language)
        return characters
    except Exception as e:
        logger.error(f"Error getting characters grouped by type: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
