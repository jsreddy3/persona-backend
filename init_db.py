from database.database import engine, SessionLocal
from database.models import Base, User, Character, Conversation, Message

def init_db():
    print("Creating database tables...")
    Base.metadata.create_all(bind=engine)
    print("Database tables created successfully!")
    
    # Create test data
    db = SessionLocal()
    try:
        # Create test character if it doesn't exist
        test_char = db.query(Character).filter(Character.name == "Test Character").first()
        if not test_char:
            test_char = Character(
                name="Test Character",
                system_prompt="You are a friendly test character who helps users verify the chat system is working.",
                greeting="Hello! I'm a test character. Nice to meet you!",
                tagline="I'm here to help test the system",
                photo_url="https://example.com/test.jpg",
                attributes=["test", "friendly", "helpful"]
            )
            db.add(test_char)
            db.commit()
            print("Created test character!")
    except Exception as e:
        print(f"Error creating test data: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    init_db()
