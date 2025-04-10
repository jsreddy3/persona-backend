from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os
import logging

logger = logging.getLogger(__name__)

# Get database URL from environment variable
DATABASE_URL = os.getenv("DATABASE_URL")

# Ensure we're using the correct dialect name (postgresql, not postgres)
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
    logger.info("Converted postgres:// URL to postgresql://")

# Create SQLAlchemy engine with connection pooling optimized for distributed deployments
if DATABASE_URL:
    # For PostgreSQL with optimized connection pooling
    engine = create_engine(
        DATABASE_URL,
        pool_size=20,              # Default permanent connection pool size
        max_overflow=40,           # Allow 40 connections in excess of pool_size (increased from 30)
        pool_timeout=30,           # Wait up to 30 seconds for a connection
        pool_recycle=1800,         # Recycle connections older than 30 minutes
        pool_pre_ping=True,        # Verify connections are still active before using
        connect_args={             # Connection args for better global distribution
            "tcp_keepalive": True,  # Keep connections alive
            "keepalives_idle": 60,  # Seconds before sending keepalive probes
            "keepalives_interval": 10,  # Seconds between keepalive probes
            "keepalives_count": 5   # Number of probes before giving up
        } if "postgresql" in DATABASE_URL else {},  # Only apply these for PostgreSQL
        isolation_level="READ COMMITTED"  # Explicit isolation level for better concurrency
    )
    logger.info(f"Connected to database with optimized connection pool")
else:
    # Default to SQLite with minimal pooling for local development
    logger.warning("No DATABASE_URL found, defaulting to SQLite")
    engine = create_engine(
        "sqlite:///./database.db",
        connect_args={"check_same_thread": False}
    )

# Create a configured "Session" class
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class for ORM models
Base = declarative_base()

# Session dependency for FastAPI routes
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Utility function to get connection status
def get_db_pool_status():
    """Get current database connection pool status"""
    try:
        # Only works with SQLAlchemy connection pools
        if hasattr(engine, 'pool'):
            return {
                "pool_size": getattr(engine.pool, 'size', None),
                "checkedin": getattr(engine.pool, 'checkedin', None),
                "checkedout": getattr(engine.pool, 'checkedout', None),
                "overflow": getattr(engine.pool, 'overflow', None)
            }
    except Exception as e:
        logger.error(f"Error getting pool stats: {str(e)}")
    
    return {"status": "unavailable"}
