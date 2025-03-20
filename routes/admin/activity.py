from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import text
from datetime import datetime
import logging
from pydantic import BaseModel
from typing import List, Optional
from database.database import get_db
from dependencies.auth import get_admin_access
from .utils import execute_query, get_cached_result, cache_result

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
        # Use a simpler approach with separate queries
        # Recent user registrations
        users_query = text("""
            SELECT
                'user_' || id AS id,
                'user_joined' AS type,
                COALESCE(username, 'Anonymous User') AS user_name,
                'New user registered' AS details,
                created_at AS timestamp
            FROM users
            ORDER BY created_at DESC
            LIMIT :limit
        """)
        
        # Recent conversations
        convos_query = text("""
            SELECT
                'conv_' || c.id AS id,
                'conversation_started' AS type,
                COALESCE(u.username, 'Anonymous User') AS user_name,
                'Started conversation with character ' || COALESCE(ch.name, 'Unknown') AS details,
                c.created_at AS timestamp
            FROM conversations c
            LEFT JOIN users u ON u.id = c.creator_id
            LEFT JOIN characters ch ON ch.id = c.character_id
            ORDER BY c.created_at DESC
            LIMIT :limit
        """)
        
        # Recent character creations
        chars_query = text("""
            SELECT
                'char_' || ch.id AS id,
                'character_created' AS type,
                COALESCE(u.username, 'Anonymous User') AS user_name,
                'Created new character ' || COALESCE(ch.name, 'Unnamed') AS details,
                ch.created_at AS timestamp
            FROM characters ch
            LEFT JOIN users u ON u.id = ch.creator_id
            ORDER BY ch.created_at DESC
            LIMIT :limit
        """)
        
        # Recent payments
        payments_query = text("""
            SELECT
                'pay_' || p.id AS id,
                'credits_purchased' AS type,
                COALESCE(u.username, 'Anonymous User') AS user_name,
                'Purchased ' || p.amount || ' credits' AS details,
                p.created_at AS timestamp
            FROM payments p
            LEFT JOIN users u ON u.id = p.user_id
            WHERE p.status = 'confirmed'
            ORDER BY p.created_at DESC
            LIMIT :limit
        """)
        
        # Execute queries
        users_result = await execute_query(db, users_query, {"limit": limit})
        convos_result = await execute_query(db, convos_query, {"limit": limit})
        chars_result = await execute_query(db, chars_query, {"limit": limit})
        payments_result = await execute_query(db, payments_query, {"limit": limit})
        
        # Combine results
        all_results = []
        for row in users_result:
            all_results.append({
                "id": row.id,
                "type": row.type,
                "userName": row.user_name,
                "details": row.details,
                "timestamp": row.timestamp
            })
            
        for row in convos_result:
            all_results.append({
                "id": row.id,
                "type": row.type,
                "userName": row.user_name,
                "details": row.details,
                "timestamp": row.timestamp
            })
            
        for row in chars_result:
            all_results.append({
                "id": row.id,
                "type": row.type,
                "userName": row.user_name,
                "details": row.details,
                "timestamp": row.timestamp
            })
            
        for row in payments_result:
            all_results.append({
                "id": row.id,
                "type": row.type,
                "userName": row.user_name,
                "details": row.details,
                "timestamp": row.timestamp
            })
        
        # Sort by timestamp and limit
        all_results.sort(key=lambda x: x["timestamp"], reverse=True)
        limited_results = all_results[:limit]
        
        # Convert to model objects
        activity_items = [ActivityItem(**item) for item in limited_results]
        
        # Cache the response for 60 seconds
        cache_result(cache_key, activity_items, 60)
        
        return activity_items
        
    except Exception as e:
        logger.error(f"Error getting activity feed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get activity feed: {str(e)}") 