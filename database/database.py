from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Debug print
print("Environment variables loaded")
print(f"DATABASE_URL from env is: {os.getenv('DATABASE_URL')}")

# Get database URL - use SQLite locally if no DATABASE_URL is set
if os.getenv("DATABASE_URL"):
    DATABASE_URL = os.getenv("DATABASE_URL")
    # Handle Heroku's postgres:// to postgresql://
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
    print(f"Using PostgreSQL: {DATABASE_URL}")
else:
    # Use SQLite as fallback
    data_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
    os.makedirs(data_dir, exist_ok=True)
    DATABASE_URL = f"sqlite:///{os.path.join(data_dir, 'personaai.db')}"
    print(f"Using SQLite: {DATABASE_URL}")

# Create engine with appropriate settings
if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(
        DATABASE_URL,
        connect_args={"check_same_thread": False}  # Needed for SQLite
    )
else:
    # Configure connection pooling to handle concurrent connections efficiently
    # - pool_size: Maximum number of permanent connections to keep
    # - max_overflow: Maximum number of connections that can be created above pool_size
    # - pool_timeout: Seconds to wait before giving up on getting a connection from the pool
    # - pool_recycle: Connections older than this many seconds will be reestablished
    engine = create_engine(
        DATABASE_URL,
        pool_size=20,              # Default permanent connection pool size
        max_overflow=30,           # Allow 30 connections in excess of pool_size
        pool_timeout=30,           # Wait up to 30 seconds for a connection
        pool_recycle=1800,         # Recycle connections older than 30 minutes
        pool_pre_ping=True         # Verify connections are still active before using
    )

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
