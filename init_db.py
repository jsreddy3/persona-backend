from database.database import engine, SessionLocal
from database.models import Base, User, Character, Conversation, Message, WorldIDVerification
from datetime import datetime

def init_db():
    print("Creating database tables...")
    Base.metadata.create_all(bind=engine)
    print("Database tables created successfully!")
    
    # Create test data
    db = SessionLocal()
    try:
        # Create test user if doesn't exist
        test_user = db.query(User).filter(User.world_id == "test_nullifier_123").first()
        if not test_user:
            test_user = User(
                world_id="test_nullifier_123",
                language="en",
                credits=100,
                created_at=datetime.utcnow(),
                last_active=datetime.utcnow()
            )
            db.add(test_user)
            db.flush()  # Get the user ID
            
            # Create verification record
            verification = WorldIDVerification(
                user_id=test_user.id,
                nullifier_hash=test_user.world_id,
                merkle_root="test_merkle_root",
                created_at=datetime.utcnow()
            )
            db.add(verification)
            print("Created test user with World ID verification!")
            
        # Create test character if it doesn't exist
        test_char = db.query(Character).filter(Character.name == "Test Character").first()
        if not test_char:
            test_char = Character(
                name="Test Character",
                system_prompt="You are a friendly test character who helps users verify the chat system is working.",
                greeting="Hello! I'm a test character. Nice to meet you!",
                tagline="I'm here to help test the system",
                photo_url="https://example.com/test.jpg",
                attributes=["test", "friendly", "helpful"],
                creator_id=test_user.id if test_user else None
            )
            db.add(test_char)
            print("Created test character!")
            
        db.commit()
        
    except Exception as e:
        print(f"Error creating test data: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    init_db()
