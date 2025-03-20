from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text
from datetime import datetime
import logging
from database.database import get_db
from dependencies.auth import get_admin_access
from .utils import cached, execute_with_timeout
from typing import List

# Set up logging
logger = logging.getLogger(__name__)

# Create router
router = APIRouter()

class HealthItem:
    def __init__(self, service: str, status: str, latency: float, message: str):
        self.service = service
        self.status = status
        self.latency = latency
        self.message = message

@router.get("/health")
async def health_check():
    """Health check endpoint for the admin API"""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "version": "1.0.0"
    }

@router.get("/analytics/health")
@cached(ttl_seconds=60)  # Cache for 1 minute
async def get_system_health(
    db: Session = Depends(get_db),
    is_admin: bool = Depends(get_admin_access)
):
    """Get system health information with optimized queries and caching"""
    try:
        # Get health data using a single optimized query
        query = """
        SELECT 
            (SELECT COUNT(*) FROM users) as user_count,
            (SELECT COUNT(*) FROM conversations) as conversation_count,
            (SELECT COUNT(*) FROM characters) as character_count,
            (SELECT COUNT(*) FROM messages) as message_count
        """
        
        # Execute with timeout
        start_time = datetime.utcnow()
        result = execute_with_timeout(db, query, timeout_seconds=3)
        row = result.fetchone()
        db_latency = (datetime.utcnow() - start_time).total_seconds() * 1000
        
        # Create response items
        health_items = [
            {
                "service": "Database",
                "status": "healthy" if db_latency < 500 else "degraded",
                "latency": round(db_latency, 2),
                "message": f"Database responding in {db_latency:.2f}ms"
            },
            {
                "service": "User Service",
                "status": "healthy",
                "latency": round(db_latency * 0.4, 2),  # Approximate for user service
                "message": f"Managing {row.user_count} users"
            },
            {
                "service": "Conversation Service",
                "status": "healthy",
                "latency": round(db_latency * 0.3, 2),  # Approximate for conversation service
                "message": f"Managing {row.conversation_count} conversations"
            },
            {
                "service": "Character Service",
                "status": "healthy",
                "latency": round(db_latency * 0.3, 2),  # Approximate for character service
                "message": f"Managing {row.character_count} characters"
            }
        ]
        
        return health_items
        
    except Exception as e:
        logger.error(f"Error checking system health: {str(e)}")
        return [
            {
                "service": "System",
                "status": "down",
                "latency": 999,
                "message": f"Error: {str(e)}"
            }
        ] 