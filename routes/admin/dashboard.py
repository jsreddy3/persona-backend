from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text
from datetime import datetime, timedelta
import logging
from pydantic import BaseModel
from typing import Optional
from database.database import get_db
from dependencies.auth import get_admin_access
from .utils import execute_query, get_cached_result, cache_result

# Set up logging
logger = logging.getLogger(__name__)

# Create router
router = APIRouter()

# --- Models ---

class DashboardStats(BaseModel):
    totalUsers: int
    activeConversations: int
    charactersCreated: int
    creditsPurchased: int
    userGrowth: float
    conversationGrowth: float
    characterGrowth: float
    creditGrowth: float
    # Additional stats for detailed view
    newMessages: Optional[int] = None
    avgMessagesPerConversation: Optional[float] = None
    activeUsers: Optional[int] = None
    completionRate: Optional[float] = None

# --- Helper Functions ---

def calculate_growth(new_count: int, total_count: int) -> float:
    """Calculate growth percentage"""
    if total_count == 0:
        return 0.0
    return round((new_count / total_count) * 100.0, 1)

# --- Optimized Dashboard Stats Endpoint ---

@router.get("/analytics/dashboard", response_model=DashboardStats)
async def get_dashboard_stats(
    db: Session = Depends(get_db),
    is_admin: bool = Depends(get_admin_access)
):
    """Get dashboard statistics with optimized queries and caching"""
    # Check cache first
    cache_key = "dashboard_stats"
    cached_result = get_cached_result(cache_key)
    if cached_result:
        return cached_result
        
    try:
        # Calculate time thresholds
        now = datetime.utcnow()
        one_day_ago = now - timedelta(days=1)
        one_day_ago_str = one_day_ago.isoformat()
        
        # Use a single optimized query to get all basic stats
        query = text("""
        SELECT
            -- Total counts
            (SELECT COUNT(*) FROM users) AS total_users,
            (SELECT COUNT(*) FROM characters) AS total_characters,
            (SELECT COUNT(*) FROM conversations WHERE updated_at >= :one_day_ago) AS active_conversations,
            (SELECT COALESCE(SUM(amount), 0) FROM payments WHERE status = 'confirmed') AS total_credits,
            
            -- Last 24 hours counts
            (SELECT COUNT(*) FROM users WHERE created_at >= :one_day_ago) AS new_users_24h,
            (SELECT COUNT(*) FROM characters WHERE created_at >= :one_day_ago) AS new_characters_24h,
            (SELECT COALESCE(SUM(amount), 0) FROM payments 
             WHERE status = 'confirmed' AND created_at >= :one_day_ago) AS new_credits_24h,
             
            -- Additional stats
            (SELECT COUNT(*) FROM messages WHERE created_at >= :one_day_ago) AS new_messages,
            (SELECT COUNT(DISTINCT creator_id) FROM conversations WHERE updated_at >= :one_day_ago) AS active_users,
            
            -- Avg messages per conversation (approximate for speed)
            (SELECT CASE 
                WHEN COUNT(*) = 0 THEN 0 
                ELSE CAST(COUNT(messages.id) AS FLOAT) / COUNT(DISTINCT messages.conversation_id) 
                END 
             FROM messages) AS avg_messages_per_conversation,
             
            -- Completion rate (faster approximation)
            (SELECT 
                CASE 
                    WHEN COUNT(*) = 0 THEN 0 
                    ELSE CAST(COUNT(CASE WHEN message_count >= 3 THEN 1 END) AS FLOAT) / COUNT(*) * 100 
                END
             FROM (
                SELECT conversation_id, COUNT(*) as message_count 
                FROM messages 
                GROUP BY conversation_id
             ) AS conversation_messages) AS completion_rate
        """)
        
        # Execute query with async method
        result = await execute_query(
            db, 
            query, 
            params={"one_day_ago": one_day_ago_str}
        )
        
        # Fetch results
        row = result.fetchone()
        
        # Calculate growth rates
        user_growth = calculate_growth(row.new_users_24h, row.total_users)
        character_growth = calculate_growth(row.new_characters_24h, row.total_characters)
        credit_growth = calculate_growth(row.new_credits_24h, row.total_credits)
        
        # Create response
        response = DashboardStats(
            totalUsers=row.total_users,
            activeConversations=row.active_conversations,
            charactersCreated=row.total_characters,
            creditsPurchased=row.total_credits,
            userGrowth=user_growth,
            conversationGrowth=100.0,  # All active conversations are from last 24h by definition
            characterGrowth=character_growth,
            creditGrowth=credit_growth,
            newMessages=row.new_messages,
            avgMessagesPerConversation=round(row.avg_messages_per_conversation, 1),
            activeUsers=row.active_users,
            completionRate=round(row.completion_rate, 1),
        )
        
        # Cache the response for 5 minutes
        cache_result(cache_key, response.dict(), 300)
        
        return response
    except Exception as e:
        logger.error(f"Error getting dashboard stats: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get dashboard stats: {str(e)}") 