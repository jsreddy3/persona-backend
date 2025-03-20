from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import text
from datetime import datetime
import logging
from pydantic import BaseModel
from typing import List, Optional
from database.database import get_db
from dependencies.auth import get_admin_access
from .utils import execute_query, get_cached_result, cache_result, invalidate_cache

# Set up logging
logger = logging.getLogger(__name__)

# Create router
router = APIRouter()

# --- Models ---

class ActivityItem(BaseModel):
    id: str
    type: str
    userName: str
    details: str
    timestamp: datetime

# --- Optimized Activity Feed Endpoint ---

@router.get("/analytics/activity", response_model=List[ActivityItem])
async def get_activity(
    limit: int = Query(10, ge=1, le=50),  # Limit between 1 and 50
    db: Session = Depends(get_db),
    is_admin: bool = Depends(get_admin_access)
):
    """Get recent activity feed with optimized query and caching"""
    # Check cache first
    cache_key = f"activity_feed_{limit}"
    cached_result = get_cached_result(cache_key)
    if cached_result:
        return cached_result
        
    try:
        # Use an optimized single query with UNION ALL to combine different activities
        query = text("""
            SELECT id, type, user_name, details, timestamp
            FROM (
                -- Recent user registrations
                SELECT
                    'user_' || id AS id,
                    'user_joined' AS type,
                    COALESCE(username, 'Anonymous User') AS user_name,
                    'New user registered' AS details,
                    created_at AS timestamp
                FROM users
                
                UNION ALL
                
                -- Recent conversations
                SELECT
                    'conv_' || c.id AS id,
                    'conversation_started' AS type,
                    COALESCE(u.username, 'Anonymous User') AS user_name,
                    'Started conversation with character ' || COALESCE(ch.name, 'Unknown') AS details,
                    c.created_at AS timestamp
                FROM conversations c
                LEFT JOIN users u ON u.id = c.creator_id
                LEFT JOIN characters ch ON ch.id = c.character_id
                
                UNION ALL
                
                -- Recent character creations
                SELECT
                    'char_' || ch.id AS id,
                    'character_created' AS type,
                    COALESCE(u.username, 'Anonymous User') AS user_name,
                    'Created new character ' || COALESCE(ch.name, 'Unnamed') AS details,
                    ch.created_at AS timestamp
                FROM characters ch
                LEFT JOIN users u ON u.id = ch.creator_id
                
                UNION ALL
                
                -- Recent payments
                SELECT
                    'pay_' || p.id AS id,
                    'credits_purchased' AS type,
                    COALESCE(u.username, 'Anonymous User') AS user_name,
                    'Purchased ' || p.amount || ' credits' AS details,
                    p.created_at AS timestamp
                FROM payments p
                LEFT JOIN users u ON u.id = p.user_id
                WHERE p.status = 'confirmed'
            ) AS all_activities
            ORDER BY timestamp DESC
            LIMIT :limit
        """)
        
        # Execute query using direct synchronous execution
        result = db.execute(query, {"limit": limit})
        
        # Convert results to model objects
        activities = []
        for row in result:
            activities.append(ActivityItem(
                id=row.id,
                type=row.type,
                userName=row.user_name,
                details=row.details,
                timestamp=row.timestamp
            ))
        
        # Cache the response for 60 seconds
        cache_result(cache_key, activities, 60)
        
        return activities
        
    except Exception as e:
        logger.error(f"Error getting activity feed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get activity feed: {str(e)}") 