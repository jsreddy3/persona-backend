from sqlalchemy.orm import Session, joinedload
from sqlalchemy import update, and_, func
from typing import Optional
from datetime import datetime
from .base import BaseRepository
from database.models import User, WorldIDVerification
import random

# Lists for generating usernames
ADJECTIVES = [
    # Personality traits
    "happy", "clever", "brave", "swift", "bright",
    "wise", "mighty", "fierce", "noble", "gentle",
    
    # Magical/Mystical
    "cosmic", "mystic", "golden", "silver", "crystal",
    "astral", "ethereal", "celestial", "arcane", "mythic",
    
    # Elements/Nature
    "storm", "frost", "flame", "shadow", "thunder",
    "solar", "lunar", "stellar", "ocean", "forest",
    
    # Colors/Materials
    "azure", "crimson", "jade", "amber", "obsidian",
    "sapphire", "emerald", "ruby", "onyx", "platinum",
    
    # Epic/Powerful
    "epic", "legendary", "eternal", "supreme", "ultra",
    "mega", "super", "hyper", "prime", "elite",
    
    # Tech/Sci-fi
    "cyber", "quantum", "digital", "neon", "techno",
    "binary", "neural", "plasma", "vector", "crypto",
    
    # Aesthetic
    "dreamy", "pixel", "retro", "vintage", "noire",
    "pastel", "vivid", "zen", "cosmic", "psychic"
]

NOUNS = [
    # Mythical Creatures
    "phoenix", "dragon", "wolf", "tiger", "eagle",
    "griffin", "unicorn", "sphinx", "hydra", "kraken",
    "chimera", "wyrm", "basilisk", "manticore", "pegasus",
    
    # Character Classes
    "wizard", "knight", "sage", "hero", "legend",
    "warrior", "hunter", "spirit", "shadow", "star",
    "paladin", "ranger", "rogue", "mage", "druid",
    "monk", "bard", "oracle", "ninja", "samurai",
    
    # Nature/Animals
    "raven", "lion", "hawk", "bear", "fox",
    "cobra", "panther", "falcon", "wolf", "owl",
    
    # Fantasy Elements
    "crystal", "storm", "flame", "frost", "thunder",
    "void", "aether", "nebula", "aurora", "comet",
    
    # Tech/Sci-fi
    "cyborg", "nexus", "matrix", "vector", "binary",
    "pixel", "cyber", "neural", "quantum", "cosmic",
    
    # Objects/Weapons
    "blade", "shield", "crown", "scepter", "orb",
    "katana", "arrow", "staff", "tome", "relic",
    
    # Abstract Concepts
    "destiny", "fate", "dream", "soul", "mind",
    "echo", "enigma", "phantom", "specter", "vision"
]

class UserRepository(BaseRepository[User]):
    def __init__(self, db: Session):
        super().__init__(User, db)
    
    def get_by_world_id(self, world_id: str) -> Optional[User]:
        """Get user by their World ID nullifier hash"""
        return self.db.query(User).filter(User.world_id == world_id).first()
    
    def get_latest_verification(self, world_id: str) -> Optional[WorldIDVerification]:
        """Get the user's latest World ID verification"""
        return self.db.query(WorldIDVerification)\
            .join(User)\
            .filter(User.world_id == world_id)\
            .order_by(WorldIDVerification.created_at.desc())\
            .first()

    def generate_unique_username(self) -> str:
        """Generate a unique username by combining an adjective and noun with a random number"""
        while True:
            adj = random.choice(ADJECTIVES)
            noun = random.choice(NOUNS)
            num = random.randint(100, 999)
            username = f"{adj}{noun}{num}"
            
            # Check if username exists
            existing = self.db.query(User).filter(User.username == username).first()
            if not existing:
                return username

    def create_or_update_user(self, world_id: str, language: str = "en") -> User:
        """Create a new user or update existing one with World ID"""
        user = self.get_by_world_id(world_id)
        
        if not user:
            username = self.generate_unique_username()
            user = User(
                world_id=world_id,
                username=username,
                language=language.lower(),
                created_at=datetime.utcnow(),
                last_active=datetime.utcnow()
            )
            self.db.add(user)
        else:
            user.last_active = datetime.utcnow()
            if language:
                user.language = language.lower()
        
        self.db.commit()
        self.db.refresh(user)
        return user

    def create_verification(self, world_id: str, merkle_root: str) -> WorldIDVerification:
        """Create a new World ID verification record"""
        user = self.get_by_world_id(world_id)
        if not user:
            raise ValueError(f"User with World ID {world_id} not found")
            
        verification = WorldIDVerification(
            user_id=user.id,
            nullifier_hash=world_id,
            merkle_root=merkle_root,
            created_at=datetime.utcnow()
        )
        
        self.db.add(verification)
        self.db.commit()
        self.db.refresh(verification)
        return verification

    def update_credits(self, user_id: int, amount: int) -> Optional[User]:
        """Update user credits by adding amount (can be negative)"""
        user = self.get_by_id(user_id)
        if not user or user.credits + amount < 0:
            return None
            
        user.credits += amount
        self.db.commit()
        self.db.refresh(user)
        return user
    
    def get_by_email(self, email: str) -> Optional[User]:
        """Get user by email"""
        return self.db.query(User).filter(User.email == email).first()
    
    def get_with_characters(self, user_id: int) -> Optional[User]:
        """Get user with their created characters eagerly loaded"""
        return self.db.query(User)\
            .filter(User.id == user_id)\
            .options(joinedload(User.created_characters))\
            .first()
