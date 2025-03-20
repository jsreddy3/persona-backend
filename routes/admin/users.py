from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import text
from datetime import datetime
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