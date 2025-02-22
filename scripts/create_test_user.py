import os
import sys
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from database.models import Base, User, WorldIDVerification
from database.database import DATABASE_URL
from datetime import datetime

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def create_test_user():
    # Create all tables
    Base.metadata.create_all(bind=engine)
    
    db = SessionLocal()
    try:
        # Check if test user already exists
        existing_user = db.query(User).filter(User.world_id == "test_nullifier_123").first()
        if existing_user:
            print(f"Test user already exists with world_id: {existing_user.world_id}")
            return
            
        # Create a test user with a fake nullifier hash
        test_user = User(
            world_id="test_nullifier_123",
            language="en",
            credits=100,
            created_at=datetime.utcnow(),
            last_active=datetime.utcnow()
        )
        db.add(test_user)
        db.flush()  # Get the user ID
        
        # Create a verification record
        verification = WorldIDVerification(
            user_id=test_user.id,
            nullifier_hash=test_user.world_id,
            merkle_root="test_merkle_root",
            created_at=datetime.utcnow()
        )
        db.add(verification)
        
        db.commit()
        print(f"Created test user with world_id: {test_user.world_id}")
        
    except Exception as e:
        print(f"Error creating test user: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    create_test_user()
