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
class ConversationResponse(BaseModel):
    """Model for conversation response in admin API"""
    id: int
    creator_id: int
    username: Optional[str] = None
    character_id: int
    character_name: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    message_count: int = 0
    title: Optional[str] = None
    last_message_timestamp: Optional[datetime] = None

@router.get("/conversations")
async def get_conversations(
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=100),
    user_id: Optional[int] = None,
    character_id: Optional[int] = None,
    search: Optional[str] = None,
    sort_by: str = "updated_at",
    sort_dir: str = "desc",
    db: Session = Depends(get_db),
    is_admin: bool = Depends(get_admin_access)
):
    """Get paginated conversations with optimized query and caching"""
    logger.info(f"Getting conversations page {page}, limit {limit}")
    
    # Create cache key based on all parameters
    cache_key = f"conversations_list_{page}_{limit}_{user_id}_{character_id}_{search}_{sort_by}_{sort_dir}"
    cached_result = get_cached_result(cache_key)
    if cached_result:
        logger.info("Returning cached conversations result")
        return cached_result
    
    try:
        # Validate sort parameters to prevent SQL injection
        valid_sort_columns = ["id", "created_at", "updated_at", "message_count", "last_message_timestamp"]
        if sort_by not in valid_sort_columns:
            sort_by = "updated_at"
            
        valid_sort_directions = ["asc", "desc"]
        if sort_dir.lower() not in valid_sort_directions:
            sort_dir = "desc"
        
        # Build the WHERE clause based on filters
        where_clauses = []
        count_params = {}
        
        if user_id:
            where_clauses.append("c.creator_id = :user_id")
            count_params["user_id"] = user_id
            
        if character_id:
            where_clauses.append("c.character_id = :character_id")
            count_params["character_id"] = character_id
            
        if search:
            where_clauses.append("(u.username ILIKE :search OR ch.name ILIKE :search)")
            count_params["search"] = f"%{search}%"
            
        # Construct WHERE clause for count query
        where_clause = " WHERE " + " AND ".join(where_clauses) if where_clauses else ""
        
        # Count total conversations with filters
        count_query = text(f"""
            SELECT COUNT(*) FROM conversations c
            LEFT JOIN users u ON c.creator_id = u.id
            LEFT JOIN characters ch ON c.character_id = ch.id
            {where_clause}
        """)
        
        # Execute count query - using synchronous execution
        result = db.execute(count_query, count_params)
        total_count = result.scalar()
        
        # Build conversation query with filters
        query_params = {**count_params, "offset": (page - 1) * limit, "limit": limit}
        
        # Base query
        query = f"""
            SELECT 
                c.id, 
                c.creator_id,
                u.username,
                c.character_id,
                ch.name as character_name,
                c.created_at,
                c.updated_at,
                'Conversation' as title,  /* Default title since column doesn't exist */
                (
                    SELECT COUNT(*) 
                    FROM messages 
                    WHERE conversation_id = c.id
                ) as message_count,
                (
                    SELECT MAX(created_at) 
                    FROM messages 
                    WHERE conversation_id = c.id
                ) as last_message_timestamp
            FROM conversations c
            LEFT JOIN users u ON c.creator_id = u.id
            LEFT JOIN characters ch ON c.character_id = ch.id
            {where_clause}
        """
            
        # Add sorting with fully qualified column names
        if sort_by == "created_at":
            query += f" ORDER BY c.created_at {sort_dir}"
        elif sort_by == "updated_at":
            query += f" ORDER BY c.updated_at {sort_dir}"
        elif sort_by == "id":
            query += f" ORDER BY c.id {sort_dir}"
        elif sort_by == "message_count":
            query += f" ORDER BY message_count {sort_dir}"
        elif sort_by == "last_message_timestamp":
            query += f" ORDER BY last_message_timestamp {sort_dir}"
        else:
            query += f" ORDER BY c.updated_at {sort_dir}"
        
        # Add pagination
        query += " LIMIT :limit OFFSET :offset"
        
        # Execute query - using synchronous execution
        result = db.execute(text(query), query_params)
        conversations = [dict(row) for row in result.fetchall()]
        
        response = {
            "items": conversations,
            "total": total_count,
            "page": page,
            "limit": limit,
            "pages": (total_count + limit - 1) // limit
        }
        
        # Cache response for 30 seconds
        cache_result(cache_key, response, 30)
        return response
        
    except Exception as e:
        logger.error(f"Error getting conversations: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get conversations: {str(e)}")

@router.get("/conversations/{conversation_id}")
async def get_conversation_by_id(
    conversation_id: int,
    db: Session = Depends(get_db),
    is_admin: bool = Depends(get_admin_access)
):
    """Get a conversation by ID with messages"""
    logger.info(f"Getting conversation with ID {conversation_id}")
    
    cache_key = f"conversation_{conversation_id}"
    cached_result = get_cached_result(cache_key)
    if cached_result:
        logger.info("Returning cached conversation result")
        return cached_result
    
    try:
        # Get conversation details
        conversation_query = text("""
            SELECT 
                c.id, 
                c.creator_id,
                u.username,
                c.character_id,
                ch.name as character_name,
                c.created_at,
                c.updated_at,
                'Conversation' as title  /* Default title since column doesn't exist */
            FROM conversations c
            LEFT JOIN users u ON c.creator_id = u.id
            LEFT JOIN characters ch ON c.character_id = ch.id
            WHERE c.id = :conversation_id
        """)
        
        # Execute query - using synchronous execution
        result = db.execute(conversation_query, {"conversation_id": conversation_id})
        conversation = result.fetchone()
        
        if not conversation:
            raise HTTPException(status_code=404, detail="Conversation not found")
        
        # Get messages for this conversation
        messages_query = text("""
            SELECT 
                id,
                conversation_id,
                role,  /* Using role instead of creator_id which doesn't exist */
                content as message,  /* Using content instead of message which doesn't exist */
                CASE WHEN role = 'assistant' THEN 1 ELSE 0 END as is_bot,
                created_at
            FROM messages
            WHERE conversation_id = :conversation_id
            ORDER BY created_at ASC
        """)
        
        # Execute query - using synchronous execution
        result = db.execute(messages_query, {"conversation_id": conversation_id})
        messages = [dict(row) for row in result.fetchall()]
        
        # Construct full response
        response = {
            "conversation": dict(conversation),
            "messages": messages,
            "message_count": len(messages)
        }
        
        # Cache response for 30 seconds
        cache_result(cache_key, response, 30)
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting conversation by ID: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get conversation: {str(e)}")

@router.delete("/conversations/{conversation_id}")
async def delete_conversation(
    conversation_id: int,
    db: Session = Depends(get_db),
    is_admin: bool = Depends(get_admin_access)
):
    """Delete a conversation and its messages"""
    logger.info(f"Deleting conversation with ID {conversation_id}")
    
    try:
        # First check if the conversation exists
        conversation_exists_query = text("""
            SELECT EXISTS(SELECT 1 FROM conversations WHERE id = :conversation_id)
        """)
        
        # Execute query - using synchronous execution
        result = db.execute(conversation_exists_query, {"conversation_id": conversation_id})
        conversation_exists = result.scalar()
        
        if not conversation_exists:
            logger.warning(f"Conversation with ID {conversation_id} not found")
            raise HTTPException(status_code=404, detail="Conversation not found")
        
        # Start a transaction to delete messages and then the conversation
        # First, delete the messages
        delete_messages_query = text("""
            DELETE FROM messages WHERE conversation_id = :conversation_id
        """)
        
        # Execute query - using synchronous execution
        db.execute(delete_messages_query, {"conversation_id": conversation_id})
        
        # Then, delete the conversation
        delete_conversation_query = text("""
            DELETE FROM conversations 
            WHERE id = :conversation_id
            RETURNING id
        """)
        
        # Execute query - using synchronous execution
        result = db.execute(delete_conversation_query, {"conversation_id": conversation_id})
        deleted_conversation = result.fetchone()
        
        if deleted_conversation:
            # Invalidate cache for this conversation and the conversations list
            invalidate_cache(f"conversation_{conversation_id}")
            invalidate_cache("conversations_list")
            
            return {
                "message": "Conversation deleted successfully",
                "id": conversation_id,
                "success": True
            }
        else:
            raise HTTPException(status_code=500, detail="Failed to delete conversation")
            
    except Exception as e:
        logger.error(f"Error deleting conversation: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error deleting conversation: {str(e)}") 