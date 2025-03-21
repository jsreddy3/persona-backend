from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import text
from datetime import datetime, timedelta
import logging
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from database.database import get_db
from dependencies.auth import get_admin_access
from .utils import execute_query, get_cached_result, cache_result, invalidate_cache

# Set up logging
logger = logging.getLogger(__name__)

# Create router
router = APIRouter()

# --- Models ---

class AdminUserResponse(BaseModel):
    id: int
    world_id: str
    username: Optional[str]
    email: Optional[str]
    language: str
    credits: int
    wallet_address: Optional[str]
    created_at: datetime
    last_active: Optional[datetime]
    credits_spent: int
    character_count: int
    conversation_count: int
    message_count: int

class UserUpdateRequest(BaseModel):
    username: Optional[str] = None
    email: Optional[str] = None
    language: Optional[str] = None
    credits: Optional[int] = None
    wallet_address: Optional[str] = None

class UserStats(BaseModel):
    totalUsers: int
    activeUsers24h: int
    newUsers7d: int

class UserHistoricalData(BaseModel):
    dates: List[str]
    totalUsers: List[int]
    activeUsers: List[int]
    newUsers: List[int]
    retentionRate: List[float]
    activityDistribution: Dict[str, int]

# --- User Analytics Endpoints ---

@router.get("/analytics/user-stats", response_model=UserStats)
async def get_user_stats(
    db: Session = Depends(get_db),
    is_admin: bool = Depends(get_admin_access)
):
    """Get user statistics for the admin panel with optimized query and caching"""
    # Check cache first
    cache_key = "user_stats"
    cached_result = get_cached_result(cache_key)
    if cached_result:
        return cached_result
        
    try:
        # Calculate time thresholds
        now = datetime.utcnow()
        one_day_ago = now - timedelta(days=1)
        seven_days_ago = now - timedelta(days=7)
        
        # Use a single optimized query to get all stats
        query = text("""
        SELECT
            (SELECT COUNT(*) FROM users) AS total_users,
            (SELECT COUNT(DISTINCT id) FROM users WHERE last_active >= :one_day_ago) AS active_users_24h,
            (SELECT COUNT(*) FROM users WHERE created_at >= :seven_days_ago) AS new_users_7d
        """)
        
        # Execute query with direct synchronous execution
        result = db.execute(query, {
            "one_day_ago": one_day_ago.isoformat(),
            "seven_days_ago": seven_days_ago.isoformat()
        })
        
        # Get results
        row = result.fetchone()
        
        # Create response
        stats = UserStats(
            totalUsers=row.total_users,
            activeUsers24h=row.active_users_24h,
            newUsers7d=row.new_users_7d
        )
        
        # Cache for 5 minutes
        cache_result(cache_key, stats.dict(), 300)
        
        return stats
    except Exception as e:
        logger.error(f"Error getting user stats: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get user stats: {str(e)}")

@router.get("/analytics/user-historical", response_model=UserHistoricalData)
async def get_user_historical_data(
    days: int = Query(30, ge=1, le=90),  # Default to 30 days, min 1, max 90
    db: Session = Depends(get_db),
    is_admin: bool = Depends(get_admin_access)
):
    """Get historical user data for charts and visualizations"""
    # Check cache first
    cache_key = f"user_historical_data_{days}"
    cached_result = get_cached_result(cache_key)
    if cached_result:
        return cached_result
        
    try:
        # Calculate date range
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=days)
        
        # Initialize result containers
        dates = []
        total_users = []
        active_users = []
        new_users = []
        retention_rates = []
        
        # For short time ranges (1-3 days), provide more granular data
        use_hourly_data = days <= 3
        
        # Time increment depends on the range
        if use_hourly_data:
            # For 1-3 days, provide hourly data points
            increment = timedelta(hours=4)  # Every 4 hours
        else:
            # For longer ranges, use daily data points
            increment = timedelta(days=1)
        
        # Generate data for each day in the range
        current_date = start_date
        
        while current_date <= end_date:
            next_date = current_date + increment
            
            # Format date string based on granularity
            if use_hourly_data:
                date_str = current_date.strftime("%Y-%m-%d %H:%M")
            else:
                date_str = current_date.strftime("%Y-%m-%d")
                
            dates.append(date_str)
            
            # Optimized query for total users up to this date
            total_query = text("""
                SELECT COUNT(*) FROM users
                WHERE created_at < :next_date
            """)
            
            # Execute query for total users
            total_result = db.execute(total_query, {"next_date": next_date.isoformat()})
            total = total_result.scalar() or 0
            total_users.append(total)
            
            # Active users in this time period
            active_query = text("""
                SELECT COUNT(DISTINCT id) FROM users
                WHERE last_active >= :current_date
                AND last_active < :next_date
            """)
            
            # Execute query for active users
            active_result = db.execute(active_query, {
                "current_date": current_date.isoformat(),
                "next_date": next_date.isoformat()
            })
            active = active_result.scalar() or 0
            active_users.append(active)
            
            # New users in this time period
            new_query = text("""
                SELECT COUNT(*) FROM users
                WHERE created_at >= :current_date
                AND created_at < :next_date
            """)
            
            # Execute query for new users
            new_result = db.execute(new_query, {
                "current_date": current_date.isoformat(),
                "next_date": next_date.isoformat()
            })
            new = new_result.scalar() or 0
            new_users.append(new)
            
            # Define the previous period based on our increment
            previous_period_start = current_date - increment
            previous_period_end = current_date
            
            # Retention rate calculation - find users who were active in the previous period
            retention_query = text("""
                WITH previous_active AS (
                    SELECT id FROM users
                    WHERE last_active >= :previous_period_start
                    AND last_active < :previous_period_end
                    AND created_at < :previous_period_end
                ),
                returning_users AS (
                    SELECT id FROM users
                    WHERE last_active >= :current_date
                    AND last_active < :next_date
                    AND id IN (SELECT id FROM previous_active)
                )
                SELECT 
                    (SELECT COUNT(*) FROM previous_active) AS previous_active_count,
                    (SELECT COUNT(*) FROM returning_users) AS returning_count
            """)
            
            # Execute query for retention rate
            retention_result = db.execute(retention_query, {
                "previous_period_start": previous_period_start.isoformat(),
                "previous_period_end": previous_period_end.isoformat(),
                "current_date": current_date.isoformat(),
                "next_date": next_date.isoformat()
            })
            retention_row = retention_result.fetchone()
            
            # Calculate retention rate safely
            previous_active_count = retention_row.previous_active_count or 1  # Avoid division by zero
            returning_count = retention_row.returning_count or 0
            retention = (returning_count / previous_active_count) * 100 if previous_active_count > 0 else 0
            
            # Cap at 100% to avoid impossible values
            retention_rates.append(round(min(retention, 100.0), 2))
            
            current_date = next_date
        
        # Get message counts per user for activity distribution
        activity_query = text("""
            SELECT 
                CASE 
                    WHEN message_count = 0 THEN '0 messages'
                    WHEN message_count BETWEEN 1 AND 5 THEN '1-5 messages'
                    WHEN message_count BETWEEN 6 AND 20 THEN '6-20 messages'
                    WHEN message_count BETWEEN 21 AND 50 THEN '21-50 messages'
                    WHEN message_count BETWEEN 51 AND 100 THEN '51-100 messages'
                    ELSE '101+ messages'
                END AS bucket,
                COUNT(*) AS count
            FROM (
                SELECT 
                    u.id,
                    COALESCE(
                        (SELECT COUNT(*) FROM messages m 
                         JOIN conversations c ON m.conversation_id = c.id 
                         WHERE c.creator_id = u.id),
                        0
                    ) AS message_count
                FROM users u
            ) AS user_messages
            GROUP BY bucket
            ORDER BY CASE bucket
                WHEN '0 messages' THEN 1
                WHEN '1-5 messages' THEN 2
                WHEN '6-20 messages' THEN 3
                WHEN '21-50 messages' THEN 4
                WHEN '51-100 messages' THEN 5
                WHEN '101+ messages' THEN 6
            END
        """)
        
        # Execute query for activity distribution
        activity_result = db.execute(activity_query)
        
        # Convert to dictionary
        activity_buckets = {
            "0 messages": 0,
            "1-5 messages": 0,
            "6-20 messages": 0,
            "21-50 messages": 0,
            "51-100 messages": 0,
            "101+ messages": 0
        }
        
        for row in activity_result:
            activity_buckets[row.bucket] = row.count
        
        # Create and return the response
        response = UserHistoricalData(
            dates=dates,
            totalUsers=total_users,
            activeUsers=active_users,
            newUsers=new_users,
            retentionRate=retention_rates,
            activityDistribution=activity_buckets
        )
        
        # Cache for 1 hour
        cache_result(cache_key, response.dict(), 3600)
        
        return response
    except Exception as e:
        logger.error(f"Error getting user historical data: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get user historical data: {str(e)}")

# --- Optimized User Endpoints ---

@router.get("/users", response_model=Dict[str, Any])
async def get_users(
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=50),  # Limit between 1 and 50
    search: Optional[str] = None,
    sort_by: Optional[str] = "id",
    sort_dir: Optional[str] = "desc",
    db: Session = Depends(get_db),
    is_admin: bool = Depends(get_admin_access)
):
    """Get paginated users with optimized query and caching"""
    # Check cache first
    cache_key = f"users_list_{page}_{limit}_{search}_{sort_by}_{sort_dir}"
    cached_result = get_cached_result(cache_key)
    if cached_result:
        return cached_result
        
    try:
        # Calculate offset
        offset = (page - 1) * limit
        
        # Prepare search condition
        search_condition = ""
        params = {"limit": limit, "offset": offset}
        
        if search:
            search_condition = """
            WHERE u.username ILIKE :search
            OR u.email ILIKE :search
            OR u.world_id ILIKE :search
            """
            params["search"] = f"%{search}%"
        
        # Prepare sorting
        sort_field = "u.id"
        if sort_by == "username":
            sort_field = "u.username"
        elif sort_by == "credits":
            sort_field = "u.credits"
        elif sort_by == "created_at":
            sort_field = "u.created_at"
        elif sort_by == "last_active":
            sort_field = "u.last_active"
        elif sort_by == "character_count":
            sort_field = "character_count"
        elif sort_by == "conversation_count":
            sort_field = "conversation_count"
        elif sort_by == "message_count":
            sort_field = "message_count"
        
        sort_direction = "DESC" if sort_dir.lower() == "desc" else "ASC"
        
        # Build the query for total count (separate from data query for efficiency)
        count_query = text(f"""
        SELECT COUNT(*) AS total
        FROM users u
        {search_condition}
        """)
        
        # Build the main data query with efficient joins
        data_query = text(f"""
        SELECT 
            u.id,
            u.world_id,
            u.username,
            u.email,
            u.language,
            u.credits,
            u.wallet_address,
            u.created_at,
            u.last_active,
            u.credits_spent,
            (SELECT COUNT(*) FROM characters WHERE creator_id = u.id) AS character_count,
            (SELECT COUNT(*) FROM conversations WHERE creator_id = u.id) AS conversation_count,
            (SELECT COUNT(*) FROM conversations c 
             JOIN messages m ON m.conversation_id = c.id 
             WHERE c.creator_id = u.id) AS message_count
        FROM users u
        {search_condition}
        ORDER BY {sort_field} {sort_direction}
        LIMIT :limit OFFSET :offset
        """)
        
        # Execute count query - using synchronous version to avoid issues
        count_result = db.execute(count_query, params)
        total = count_result.scalar() or 0
        
        # Execute data query - using synchronous version to avoid issues
        data_result = db.execute(data_query, params)
        
        # Format response
        users = []
        for row in data_result:
            users.append(AdminUserResponse(
                id=row.id,
                world_id=row.world_id,
                username=row.username,
                email=row.email,
                language=row.language,
                credits=row.credits,
                wallet_address=row.wallet_address,
                created_at=row.created_at,
                last_active=row.last_active,
                credits_spent=row.credits_spent,
                character_count=row.character_count,
                conversation_count=row.conversation_count,
                message_count=row.message_count
            ))
        
        # Create response with pagination metadata
        response = {
            "data": users,
            "total": total,
            "page": page,
            "limit": limit,
            "totalPages": (total + limit - 1) // limit
        }
        
        # Cache response for 30 seconds
        cache_result(cache_key, response, 30)
        
        return response
    except Exception as e:
        logger.error(f"Error getting users: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get users: {str(e)}")

@router.get("/users/{user_id}", response_model=AdminUserResponse)
async def get_user_by_id(
    user_id: int,
    db: Session = Depends(get_db),
    is_admin: bool = Depends(get_admin_access)
):
    """Get a single user by ID with optimized query and caching"""
    # Check cache first
    cache_key = f"user_{user_id}"
    cached_result = get_cached_result(cache_key)
    if cached_result:
        return cached_result
        
    try:
        # Build the query with efficient subqueries
        query = text("""
        SELECT 
            u.id,
            u.world_id,
            u.username,
            u.email,
            u.language,
            u.credits,
            u.wallet_address,
            u.created_at,
            u.last_active,
            u.credits_spent,
            (SELECT COUNT(*) FROM characters WHERE creator_id = u.id) AS character_count,
            (SELECT COUNT(*) FROM conversations WHERE creator_id = u.id) AS conversation_count,
            (SELECT COUNT(*) FROM conversations c 
             JOIN messages m ON m.conversation_id = c.id 
             WHERE c.creator_id = u.id) AS message_count
        FROM users u
        WHERE u.id = :user_id
        """)
        
        # Execute query - using synchronous version to avoid issues
        result = db.execute(query, {"user_id": user_id})
        row = result.fetchone()
        
        if not row:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Format response
        response = AdminUserResponse(
            id=row.id,
            world_id=row.world_id,
            username=row.username,
            email=row.email,
            language=row.language,
            credits=row.credits,
            wallet_address=row.wallet_address,
            created_at=row.created_at,
            last_active=row.last_active,
            credits_spent=row.credits_spent,
            character_count=row.character_count,
            conversation_count=row.conversation_count,
            message_count=row.message_count
        )
        
        # Cache response for 30 seconds
        cache_result(cache_key, response.dict(), 30)
        
        return response
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting user by ID: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get user: {str(e)}")

@router.patch("/users/{user_id}")
async def update_user(
    user_id: int,
    update_data: UserUpdateRequest,
    db: Session = Depends(get_db),
    is_admin: bool = Depends(get_admin_access)
):
    """Update a user"""
    logger.info(f"Updating user with ID {user_id}")
    
    try:
        # First check if the user exists
        user_exists_query = text("""
            SELECT EXISTS(SELECT 1 FROM users WHERE id = :user_id)
        """)
        
        # Execute query - using synchronous version to avoid issues
        result = db.execute(user_exists_query, {"user_id": user_id})
        user_exists = result.scalar()
        
        if not user_exists:
            logger.warning(f"User with ID {user_id} not found")
            raise HTTPException(status_code=404, detail="User not found")
        
        # Build the update query dynamically based on provided fields
        update_fields = []
        params = {"user_id": user_id}
        
        # Only include fields that were provided in the request
        if update_data.username is not None:
            update_fields.append("username = :username")
            params["username"] = update_data.username
            
        if update_data.email is not None:
            update_fields.append("email = :email")
            params["email"] = update_data.email
        
        if update_data.language is not None:
            update_fields.append("language = :language")
            params["language"] = update_data.language
            
        if update_data.credits is not None:
            update_fields.append("credits = :credits")
            params["credits"] = update_data.credits
            
        if update_data.wallet_address is not None:
            update_fields.append("wallet_address = :wallet_address")
            params["wallet_address"] = update_data.wallet_address
        
        if not update_fields:
            return {"message": "No fields to update", "success": True}
        
        # Add updated_at timestamp
        update_fields.append("last_active = CURRENT_TIMESTAMP")
        
        # Construct and execute the update query
        update_query = text(f"""
            UPDATE users 
            SET {', '.join(update_fields)}
            WHERE id = :user_id
            RETURNING id, username, email, world_id, language, credits, wallet_address,
                    created_at, last_active, credits_spent
        """)
        
        # Execute query - using synchronous version to avoid issues
        result = db.execute(update_query, params)
        updated_user = result.fetchone()
        
        if updated_user:
            # Invalidate cache for this user and the users list
            invalidate_cache(f"user_{user_id}")
            invalidate_cache("users_list")
            
            return {
                "message": "User updated successfully",
                "user": dict(updated_user),
                "success": True
            }
        else:
            raise HTTPException(status_code=500, detail="Failed to update user")
            
    except Exception as e:
        logger.error(f"Error updating user: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error updating user: {str(e)}")

@router.get("/users/language-stats")
async def get_user_language_stats(
    db: Session = Depends(get_db),
    is_admin: bool = Depends(get_admin_access)
):
    """Get statistics about user language preferences"""
    # Check cache first
    cache_key = "user_language_stats"
    cached_result = get_cached_result(cache_key)
    if cached_result:
        return cached_result
        
    try:
        # Optimized query to get language counts
        query = text("""
            SELECT 
                language, 
                COUNT(*) as count 
            FROM users 
            GROUP BY language 
            ORDER BY count DESC
        """)
        
        # Execute query
        result = db.execute(query)
        
        # Process results
        language_stats = {}
        total_users = 0
        
        for row in result:
            language = row.language or "unknown"
            count = row.count
            language_stats[language] = count
            total_users += count
        
        # Calculate percentages
        response = {
            "total_users": total_users,
            "languages": [
                {
                    "language": lang,
                    "count": count,
                    "percentage": round((count / total_users) * 100, 2) if total_users > 0 else 0
                }
                for lang, count in language_stats.items()
            ]
        }
        
        # Cache for 1 hour
        cache_result(cache_key, response, 3600)
        
        return response
    except Exception as e:
        logger.error(f"Error getting language stats: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get language stats: {str(e)}") 