import logging
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy.sql import text
from typing import List, Optional, Dict, Any
from pydantic import BaseModel
from datetime import datetime

from database.database import get_db
from dependencies.auth import get_admin_access
from routes.admin.utils import (
    execute_query, 
    get_cached_result,
    cache_result,
    invalidate_cache
)

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create router
router = APIRouter()

# Pydantic models
class AdminCharacterResponse(BaseModel):
    """Model for character response in admin API"""
    id: int
    name: str
    creator_id: int
    creator_name: Optional[str] = None
    is_public: bool
    is_featured: bool
    created_at: datetime
    updated_at: Optional[datetime] = None
    avg_rating: Optional[float] = None
    description: Optional[str] = None
    conversation_count: int = 0

class CharacterUpdateRequest(BaseModel):
    """Model for character update request"""
    name: Optional[str] = None
    description: Optional[str] = None
    is_public: Optional[bool] = None
    is_featured: Optional[bool] = None

@router.get("/characters")
async def get_characters(
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=100),
    search: Optional[str] = None,
    sort_by: str = "created_at",
    sort_dir: str = "desc",
    db: Session = Depends(get_db),
    is_admin: bool = Depends(get_admin_access)
):
    """Get paginated characters with optimized query and caching"""
    logger.info(f"Getting characters page {page}, limit {limit}")
    
    cache_key = f"characters_list_{page}_{limit}_{search}_{sort_by}_{sort_dir}"
    cached_result = get_cached_result(cache_key)
    if cached_result:
        logger.info("Returning cached characters result")
        return cached_result
    
    try:
        # Validate sort parameters to prevent SQL injection
        valid_sort_columns = ["id", "name", "created_at", "updated_at", "avg_rating", "conversation_count"]
        if sort_by not in valid_sort_columns:
            sort_by = "created_at"
            
        valid_sort_directions = ["asc", "desc"]
        if sort_dir.lower() not in valid_sort_directions:
            sort_dir = "desc"
        
        # Count total characters with search filter if provided
        count_params = {}
        if search:
            count_query = text("""
                SELECT COUNT(*) FROM characters 
                WHERE name ILIKE :search OR description ILIKE :search
            """)
            count_params["search"] = f"%{search}%"
        else:
            count_query = text("SELECT COUNT(*) FROM characters")
        
        # Execute count query - using synchronous version to avoid issues
        result = db.execute(count_query, count_params)
        total_count = result.scalar()
        
        # Build character query with search filter if provided
        query_params = {"offset": (page - 1) * limit, "limit": limit}
        
        # Base query
        query = f"""
            SELECT 
                c.id, 
                c.name, 
                c.creator_id,
                u.username as creator_name,
                'true' as is_public,
                'false' as is_featured,
                c.created_at,
                c.updated_at,
                c.character_description as description,
                0 as avg_rating,  /* Default value since character_ratings table doesn't exist */
                (
                    SELECT COUNT(*) 
                    FROM conversations 
                    WHERE character_id = c.id
                ) as conversation_count
            FROM characters c
            LEFT JOIN users u ON c.creator_id = u.id
        """
        
        # Add search condition if provided
        if search:
            query += " WHERE c.name ILIKE :search OR c.character_description ILIKE :search"
            query_params["search"] = f"%{search}%"
            
        # Add sorting with fully qualified column names
        if sort_by == "created_at":
            query += f" ORDER BY c.created_at {sort_dir}"
        elif sort_by == "updated_at":
            query += f" ORDER BY c.updated_at {sort_dir}"
        elif sort_by == "name":
            query += f" ORDER BY c.name {sort_dir}"
        elif sort_by == "id":
            query += f" ORDER BY c.id {sort_dir}"
        elif sort_by == "avg_rating":
            query += f" ORDER BY avg_rating {sort_dir}"
        elif sort_by == "conversation_count":
            query += f" ORDER BY conversation_count {sort_dir}"
        else:
            query += f" ORDER BY c.created_at {sort_dir}"
        
        # Add pagination
        query += " LIMIT :limit OFFSET :offset"
        
        # Execute query - using synchronous version to avoid issues
        result = db.execute(text(query), query_params)
        characters = [dict(row) for row in result.fetchall()]
        
        response = {
            "items": characters,
            "total": total_count,
            "page": page,
            "limit": limit,
            "pages": (total_count + limit - 1) // limit
        }
        
        # Cache response for 30 seconds
        cache_result(cache_key, response, 30)
        return response
        
    except Exception as e:
        logger.error(f"Error getting characters: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get characters: {str(e)}")

@router.get("/characters/{character_id}")
async def get_character_by_id(
    character_id: int,
    db: Session = Depends(get_db),
    is_admin: bool = Depends(get_admin_access)
):
    """Get a character by ID with optimized query and caching"""
    logger.info(f"Getting character with ID {character_id}")
    
    cache_key = f"character_{character_id}"
    cached_result = get_cached_result(cache_key)
    if cached_result:
        logger.info("Returning cached character result")
        return cached_result
    
    try:
        query = text("""
            SELECT 
                c.id, 
                c.name, 
                c.creator_id,
                u.username as creator_name,
                'true' as is_public,
                'false' as is_featured,
                c.created_at,
                c.updated_at,
                c.character_description as description,
                0 as avg_rating,
                (
                    SELECT COUNT(*) 
                    FROM conversations 
                    WHERE character_id = c.id
                ) as conversation_count
            FROM characters c
            LEFT JOIN users u ON c.creator_id = u.id
            WHERE c.id = :character_id
        """)
        
        # Execute query - using synchronous version to avoid issues
        result = db.execute(query, {"character_id": character_id})
        character = result.fetchone()
        
        if not character:
            raise HTTPException(status_code=404, detail="Character not found")
            
        response = dict(character)
        
        # Cache response for 30 seconds
        cache_result(cache_key, response, 30)
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting character by ID: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get character: {str(e)}")

@router.patch("/characters/{character_id}")
async def update_character(
    character_id: int,
    update_data: CharacterUpdateRequest,
    db: Session = Depends(get_db),
    is_admin: bool = Depends(get_admin_access)
):
    """Update a character"""
    logger.info(f"Updating character with ID {character_id}")
    
    try:
        # First check if the character exists
        character_exists_query = text("""
            SELECT EXISTS(SELECT 1 FROM characters WHERE id = :character_id)
        """)
        
        # Execute query - using synchronous version to avoid issues
        result = db.execute(character_exists_query, {"character_id": character_id})
        character_exists = result.scalar()
        
        if not character_exists:
            logger.warning(f"Character with ID {character_id} not found")
            raise HTTPException(status_code=404, detail="Character not found")
        
        # Build the update query dynamically based on provided fields
        update_fields = []
        params = {"character_id": character_id}
        
        # Only include fields that were provided in the request
        if update_data.name is not None:
            update_fields.append("name = :name")
            params["name"] = update_data.name
            
        if update_data.description is not None:
            update_fields.append("character_description = :description")
            params["description"] = update_data.description
        
        if update_data.is_public is not None:
            update_fields.append("is_public = :is_public")
            params["is_public"] = update_data.is_public
            
        if update_data.is_featured is not None:
            update_fields.append("is_featured = :is_featured")
            params["is_featured"] = update_data.is_featured
        
        if not update_fields:
            return {"message": "No fields to update", "success": True}
        
        # Add updated_at timestamp
        update_fields.append("updated_at = CURRENT_TIMESTAMP")
        
        # Construct and execute the update query
        update_query = text(f"""
            UPDATE characters 
            SET {', '.join(update_fields)}
            WHERE id = :character_id
            RETURNING id, name, creator_id, created_at, updated_at, character_description
        """)
        
        # Execute query - using synchronous version to avoid issues
        result = db.execute(update_query, params)
        updated_character = result.fetchone()
        
        if updated_character:
            # Invalidate cache for this character and the characters list
            invalidate_cache(f"character_{character_id}")
            invalidate_cache("characters_list")
            
            return {
                "message": "Character updated successfully",
                "character": dict(updated_character),
                "success": True
            }
        else:
            raise HTTPException(status_code=500, detail="Failed to update character")
            
    except Exception as e:
        logger.error(f"Error updating character: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error updating character: {str(e)}") 