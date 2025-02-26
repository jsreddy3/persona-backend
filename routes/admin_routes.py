from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session
from sqlalchemy import func, desc, and_, or_, text
from typing import List, Optional, Dict, Any
from pydantic import BaseModel
from datetime import datetime, timedelta
import logging
from database.database import get_db
from database.models import User, Character, Conversation, Message, Payment, Session
from dependencies.auth import get_current_user, create_session, get_admin_access
from services.user_service import UserService

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = APIRouter(tags=["admin"])

# --- Models for Admin API ---

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

class AdminCharacterResponse(BaseModel):
    id: int
    name: str
    creator_id: int
    creator_username: Optional[str]
    character_description: str
    tagline: Optional[str]
    photo_url: Optional[str]
    num_chats_created: int
    num_messages: int
    rating: float
    created_at: datetime
    language: str

class AdminConversationResponse(BaseModel):
    id: int
    character_id: int
    character_name: str
    character_photo: Optional[str]
    user_id: int
    user_name: Optional[str]
    message_count: int
    created_at: datetime
    last_message_at: Optional[datetime]

class AdminMessageResponse(BaseModel):
    id: int
    role: str
    content: str
    created_at: datetime
    
class AdminConversationDetailResponse(BaseModel):
    id: int
    character_id: int
    character_name: str
    character_photo: Optional[str]
    user_id: int
    user_name: Optional[str]
    message_count: int
    created_at: datetime
    last_message_at: Optional[datetime]
    messages: List[AdminMessageResponse]

class DashboardStats(BaseModel):
    totalUsers: int
    activeConversations: int
    charactersCreated: int
    creditsPurchased: int
    userGrowth: float
    conversationGrowth: float
    characterGrowth: float
    creditGrowth: float

class ActivityItem(BaseModel):
    id: str
    type: str
    userName: str
    details: str
    timestamp: datetime

class HealthItem(BaseModel):
    service: str
    status: str
    latency: float
    message: str

# --- Admin Authentication ---

async def get_admin_user(
    current_user: User = Depends(get_current_user),
) -> User:
    """Check if the current user is an admin"""
    # For now, we'll consider users with specific emails as admins
    # In a production environment, you would have a proper role-based system
    admin_emails = ["admin@persona.ai", "vivek.vajipey@gmail.com"]
    
    if not current_user.email or current_user.email not in admin_emails:
        logger.warning(f"Unauthorized admin access attempt by user {current_user.id}")
        raise HTTPException(status_code=403, detail="Not authorized to access admin API")
    
    return current_user

# --- Health Check Endpoint ---

@router.get("/health")
async def health_check():
    """Health check endpoint for the admin API"""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "version": "1.0.0"
    }

# --- Dashboard Endpoints ---

@router.get("/analytics/dashboard", response_model=DashboardStats)
async def get_dashboard_stats(
    db: Session = Depends(get_db),
    is_admin: bool = Depends(get_admin_access)
):
    """Get dashboard statistics for the admin panel"""
    try:
        # Get current counts
        total_users = db.query(func.count(User.id)).scalar()
        active_conversations = db.query(func.count(Conversation.id)).filter(
            Conversation.updated_at >= datetime.utcnow() - timedelta(days=1)
        ).scalar()
        total_characters = db.query(func.count(Character.id)).scalar()
        total_credits = db.query(func.sum(Payment.amount)).filter(
            Payment.status == "confirmed"
        ).scalar() or 0
        
        # Get counts from 30 days ago for growth calculation
        thirty_days_ago = datetime.utcnow() - timedelta(days=30)
        
        users_30d_ago = db.query(func.count(User.id)).filter(
            User.created_at <= thirty_days_ago
        ).scalar()
        
        conversations_30d_ago = db.query(func.count(Conversation.id)).filter(
            Conversation.created_at <= thirty_days_ago
        ).scalar()
        
        characters_30d_ago = db.query(func.count(Character.id)).filter(
            Character.created_at <= thirty_days_ago
        ).scalar()
        
        credits_30d_ago = db.query(func.sum(Payment.amount)).filter(
            and_(
                Payment.status == "confirmed",
                Payment.created_at <= thirty_days_ago
            )
        ).scalar() or 0
        
        # Calculate growth percentages
        user_growth = calculate_growth(users_30d_ago, total_users)
        conversation_growth = calculate_growth(conversations_30d_ago, active_conversations)
        character_growth = calculate_growth(characters_30d_ago, total_characters)
        credit_growth = calculate_growth(credits_30d_ago, total_credits)
        
        return DashboardStats(
            totalUsers=total_users,
            activeConversations=active_conversations,
            charactersCreated=total_characters,
            creditsPurchased=total_credits,
            userGrowth=user_growth,
            conversationGrowth=conversation_growth,
            characterGrowth=character_growth,
            creditGrowth=credit_growth
        )
    except Exception as e:
        logger.error(f"Error getting dashboard stats: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get dashboard stats: {str(e)}")

@router.get("/analytics/activity", response_model=List[ActivityItem])
async def get_activity(
    limit: int = 10,
    db: Session = Depends(get_db),
    is_admin: bool = Depends(get_admin_access)
):
    """Get recent activity for the admin dashboard"""
    try:
        # Get recent user registrations
        new_users = db.query(User).order_by(desc(User.created_at)).limit(limit).all()
        user_activities = [
            ActivityItem(
                id=f"user_{user.id}",
                type="user_joined",
                userName=user.username or "Anonymous User",
                details=f"New user registered with language {user.language}",
                timestamp=user.created_at
            )
            for user in new_users
        ]
        
        # Get recent conversations
        new_conversations = db.query(
            Conversation, User, Character
        ).join(
            User, User.id == Conversation.creator_id
        ).join(
            Character, Character.id == Conversation.character_id
        ).order_by(
            desc(Conversation.created_at)
        ).limit(limit).all()
        
        conversation_activities = [
            ActivityItem(
                id=f"conv_{conv[0].id}",
                type="conversation_started",
                userName=conv[1].username or "Anonymous User",
                details=f"Started conversation with character {conv[2].name}",
                timestamp=conv[0].created_at
            )
            for conv in new_conversations
        ]
        
        # Get recent character creations
        new_characters = db.query(
            Character, User
        ).join(
            User, User.id == Character.creator_id
        ).order_by(
            desc(Character.created_at)
        ).limit(limit).all()
        
        character_activities = [
            ActivityItem(
                id=f"char_{char[0].id}",
                type="character_created",
                userName=char[1].username or "Anonymous User",
                details=f"Created new character {char[0].name}",
                timestamp=char[0].created_at
            )
            for char in new_characters
        ]
        
        # Get recent payments
        recent_payments = db.query(
            Payment, User
        ).join(
            User, User.id == Payment.user_id
        ).filter(
            Payment.status == "confirmed"
        ).order_by(
            desc(Payment.created_at)
        ).limit(limit).all()
        
        payment_activities = [
            ActivityItem(
                id=f"pay_{payment[0].id}",
                type="credits_purchased",
                userName=payment[1].username or "Anonymous User",
                details=f"Purchased {payment[0].amount} credits",
                timestamp=payment[0].created_at
            )
            for payment in recent_payments
        ]
        
        # Combine all activities, sort by timestamp, and return the most recent ones
        all_activities = user_activities + conversation_activities + character_activities + payment_activities
        all_activities.sort(key=lambda x: x.timestamp, reverse=True)
        
        return all_activities[:limit]
    except Exception as e:
        logger.error(f"Error getting activity feed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get activity feed: {str(e)}")

@router.get("/analytics/health", response_model=List[HealthItem])
async def get_system_health(
    is_admin: bool = Depends(get_admin_access),
    db: Session = Depends(get_db)
):
    """Get system health information"""
    try:
        # Check database health
        db_start_time = datetime.utcnow()
        db.execute(text("SELECT 1")).scalar()  # Use text() function for raw SQL
        db_latency = (datetime.utcnow() - db_start_time).total_seconds() * 1000  # ms
        
        # Check user service
        user_service_start = datetime.utcnow()
        user_count = db.query(func.count(User.id)).scalar()
        user_service_latency = (datetime.utcnow() - user_service_start).total_seconds() * 1000
        
        # Check conversation service
        conv_service_start = datetime.utcnow()
        conv_count = db.query(func.count(Conversation.id)).scalar()
        conv_service_latency = (datetime.utcnow() - conv_service_start).total_seconds() * 1000
        
        # Check character service
        char_service_start = datetime.utcnow()
        char_count = db.query(func.count(Character.id)).scalar()
        char_service_latency = (datetime.utcnow() - char_service_start).total_seconds() * 1000
        
        # Return health information
        return [
            HealthItem(
                service="Database",
                status="healthy" if db_latency < 500 else "degraded",
                latency=db_latency,
                message=f"Database responding in {db_latency:.2f}ms"
            ),
            HealthItem(
                service="User Service",
                status="healthy" if user_service_latency < 500 else "degraded",
                latency=user_service_latency,
                message=f"Managing {user_count} users"
            ),
            HealthItem(
                service="Conversation Service",
                status="healthy" if conv_service_latency < 500 else "degraded",
                latency=conv_service_latency,
                message=f"Managing {conv_count} conversations"
            ),
            HealthItem(
                service="Character Service",
                status="healthy" if char_service_latency < 500 else "degraded",
                latency=char_service_latency,
                message=f"Managing {char_count} characters"
            )
        ]
    except Exception as e:
        logger.error(f"Error checking system health: {str(e)}")
        return [
            HealthItem(
                service="System",
                status="down",
                latency=999,
                message=f"Error: {str(e)}"
            )
        ]

# --- User Management Endpoints ---

@router.get("/users", response_model=Dict[str, Any])
async def get_users(
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=100),
    search: Optional[str] = None,
    db: Session = Depends(get_db),
    is_admin: bool = Depends(get_admin_access)
):
    """Get all users with pagination and optional search"""
    try:
        query = db.query(User)
        
        # Apply search filter if provided
        if search:
            search_term = f"%{search}%"
            query = query.filter(
                or_(
                    User.username.ilike(search_term),
                    User.email.ilike(search_term),
                    User.world_id.ilike(search_term)
                )
            )
        
        # Calculate total for pagination
        total = query.count()
        
        # Apply pagination
        users = query.order_by(desc(User.created_at)).offset((page - 1) * limit).limit(limit).all()
        
        # Enhance user data with additional information
        result = []
        for user in users:
            # Get character count
            character_count = db.query(func.count(Character.id)).filter(
                Character.creator_id == user.id
            ).scalar()
            
            # Get conversation count
            conversation_count = db.query(func.count(Conversation.id)).filter(
                Conversation.creator_id == user.id
            ).scalar()
            
            # Get message count
            message_count = db.query(func.count(Message.id)).join(
                Conversation, Conversation.id == Message.conversation_id
            ).filter(
                Conversation.creator_id == user.id
            ).scalar()
            
            result.append(AdminUserResponse(
                id=user.id,
                world_id=user.world_id,
                username=user.username,
                email=user.email,
                language=user.language,
                credits=user.credits,
                wallet_address=user.wallet_address,
                created_at=user.created_at,
                last_active=user.last_active,
                credits_spent=user.credits_spent,
                character_count=character_count,
                conversation_count=conversation_count,
                message_count=message_count
            ))
        
        # Return with pagination metadata
        return {
            "data": result,
            "total": total,
            "page": page,
            "limit": limit,
            "totalPages": (total + limit - 1) // limit
        }
    except Exception as e:
        logger.error(f"Error getting users: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get users: {str(e)}")

@router.get("/users/{user_id}", response_model=AdminUserResponse)
async def get_user_by_id(
    user_id: int,
    db: Session = Depends(get_db),
    is_admin: bool = Depends(get_admin_access)
):
    """Get a single user by ID with detailed information"""
    try:
        user = db.query(User).filter(User.id == user_id).first()
        
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Get character count
        character_count = db.query(func.count(Character.id)).filter(
            Character.creator_id == user.id
        ).scalar()
        
        # Get conversation count
        conversation_count = db.query(func.count(Conversation.id)).filter(
            Conversation.creator_id == user.id
        ).scalar()
        
        # Get message count
        message_count = db.query(func.count(Message.id)).join(
            Conversation, Conversation.id == Message.conversation_id
        ).filter(
            Conversation.creator_id == user.id
        ).scalar()
        
        return AdminUserResponse(
            id=user.id,
            world_id=user.world_id,
            username=user.username,
            email=user.email,
            language=user.language,
            credits=user.credits,
            wallet_address=user.wallet_address,
            created_at=user.created_at,
            last_active=user.last_active,
            credits_spent=user.credits_spent,
            character_count=character_count,
            conversation_count=conversation_count,
            message_count=message_count
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting user by ID: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get user: {str(e)}")

class UserUpdateRequest(BaseModel):
    username: Optional[str] = None
    email: Optional[str] = None
    language: Optional[str] = None
    credits: Optional[int] = None
    wallet_address: Optional[str] = None

@router.put("/users/{user_id}", response_model=AdminUserResponse)
async def update_user(
    user_id: int,
    user_data: UserUpdateRequest,
    db: Session = Depends(get_db),
    is_admin: bool = Depends(get_admin_access)
):
    """Update a user's information"""
    try:
        user = db.query(User).filter(User.id == user_id).first()
        
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Update user fields if provided
        if user_data.username is not None:
            user.username = user_data.username
        
        if user_data.email is not None:
            user.email = user_data.email
        
        if user_data.language is not None:
            user.language = user_data.language
        
        if user_data.credits is not None:
            user.credits = user_data.credits
        
        if user_data.wallet_address is not None:
            user.wallet_address = user_data.wallet_address
        
        # Save changes
        db.commit()
        db.refresh(user)
        
        # Get character count
        character_count = db.query(func.count(Character.id)).filter(
            Character.creator_id == user.id
        ).scalar()
        
        # Get conversation count
        conversation_count = db.query(func.count(Conversation.id)).filter(
            Conversation.creator_id == user.id
        ).scalar()
        
        # Get message count
        message_count = db.query(func.count(Message.id)).join(
            Conversation, Conversation.id == Message.conversation_id
        ).filter(
            Conversation.creator_id == user.id
        ).scalar()
        
        return AdminUserResponse(
            id=user.id,
            world_id=user.world_id,
            username=user.username,
            email=user.email,
            language=user.language,
            credits=user.credits,
            wallet_address=user.wallet_address,
            created_at=user.created_at,
            last_active=user.last_active,
            credits_spent=user.credits_spent,
            character_count=character_count,
            conversation_count=conversation_count,
            message_count=message_count
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating user: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to update user: {str(e)}")

@router.delete("/users/{user_id}", status_code=204)
async def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    is_admin: bool = Depends(get_admin_access)
):
    """Delete a user"""
    try:
        user = db.query(User).filter(User.id == user_id).first()
        
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Delete user's conversations and messages
        conversations = db.query(Conversation).filter(Conversation.creator_id == user_id).all()
        for conversation in conversations:
            # Delete messages in the conversation
            db.query(Message).filter(Message.conversation_id == conversation.id).delete()
        
        # Delete conversations
        db.query(Conversation).filter(Conversation.creator_id == user_id).delete()
        
        # Delete characters created by the user
        db.query(Character).filter(Character.creator_id == user_id).delete()
        
        # Delete payments
        db.query(Payment).filter(Payment.user_id == user_id).delete()
        
        # Delete sessions
        db.query(Session).filter(Session.user_id == user_id).delete()
        
        # Finally, delete the user
        db.delete(user)
        db.commit()
        
        return None
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting user: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to delete user: {str(e)}")

# --- Character Management Endpoints ---

@router.get("/characters", response_model=Dict[str, Any])
async def get_characters(
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=100),
    search: Optional[str] = None,
    db: Session = Depends(get_db),
    is_admin: bool = Depends(get_admin_access)
):
    """Get all characters with pagination and optional search"""
    try:
        query = db.query(Character, User.username).join(
            User, User.id == Character.creator_id
        )
        
        # Apply search filter if provided
        if search:
            search_term = f"%{search}%"
            query = query.filter(
                or_(
                    Character.name.ilike(search_term),
                    Character.tagline.ilike(search_term),
                    Character.character_description.ilike(search_term)
                )
            )
        
        # Calculate total for pagination
        total = query.count()
        
        # Apply pagination
        characters = query.order_by(desc(Character.created_at)).offset((page - 1) * limit).limit(limit).all()
        
        # Format response
        result = []
        for char, username in characters:
            # Check if language attribute exists, use default if not
            language = getattr(char, 'language', 'en')
            
            result.append(AdminCharacterResponse(
                id=char.id,
                name=char.name,
                creator_id=char.creator_id,
                creator_username=username,
                character_description=char.character_description,
                tagline=char.tagline,
                photo_url=char.photo_url,
                num_chats_created=char.num_chats_created,
                num_messages=char.num_messages,
                rating=char.rating,
                created_at=char.created_at,
                language=language
            ))
        
        # Return with pagination metadata
        return {
            "data": result,
            "total": total,
            "page": page,
            "limit": limit,
            "totalPages": (total + limit - 1) // limit
        }
    except Exception as e:
        logger.error(f"Error getting characters: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get characters: {str(e)}")

# --- Conversation Management Endpoints ---

@router.get("/conversations", response_model=Dict[str, Any])
async def get_conversations(
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=100),
    search: Optional[str] = None,
    db: Session = Depends(get_db),
    is_admin: bool = Depends(get_admin_access)
):
    """Get all conversations with pagination and optional search"""
    try:
        # Join with Character and User to get names
        query = db.query(
            Conversation,
            Character.name.label("character_name"),
            Character.photo_url.label("character_photo"),
            User.username.label("user_name"),
            func.count(Message.id).label("message_count"),
            func.max(Message.created_at).label("last_message_at")
        ).join(
            Character, Character.id == Conversation.character_id
        ).join(
            User, User.id == Conversation.creator_id
        ).outerjoin(
            Message, Message.conversation_id == Conversation.id
        ).group_by(
            Conversation.id, Character.name, Character.photo_url, User.username
        )
        
        # Apply search filter if provided
        if search:
            search_term = f"%{search}%"
            query = query.filter(
                or_(
                    Character.name.ilike(search_term),
                    User.username.ilike(search_term)
                )
            )
        
        # Calculate total for pagination
        total = query.count()
        
        # Apply pagination
        conversations = query.order_by(desc(Conversation.created_at)).offset((page - 1) * limit).limit(limit).all()
        
        # Format response
        result = []
        for conv in conversations:
            result.append(AdminConversationResponse(
                id=conv.Conversation.id,
                character_id=conv.Conversation.character_id,
                character_name=conv.character_name,
                character_photo=conv.character_photo,
                user_id=conv.Conversation.creator_id,
                user_name=conv.user_name,
                message_count=conv.message_count,
                created_at=conv.Conversation.created_at,
                last_message_at=conv.last_message_at
            ))
        
        # Return with pagination metadata
        return {
            "data": result,
            "total": total,
            "page": page,
            "limit": limit,
            "totalPages": (total + limit - 1) // limit
        }
    except Exception as e:
        logger.error(f"Error getting conversations: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get conversations: {str(e)}")

@router.get("/conversations/{conversation_id}", response_model=AdminConversationDetailResponse)
async def get_conversation_detail(
    conversation_id: int,
    db: Session = Depends(get_db),
    is_admin: bool = Depends(get_admin_access)
):
    """Get detailed information about a specific conversation including messages"""
    try:
        # Get conversation details
        conv_query = db.query(
            Conversation,
            Character.name.label("character_name"),
            Character.photo_url.label("character_photo"),
            User.username.label("user_name"),
            func.count(Message.id).label("message_count"),
            func.max(Message.created_at).label("last_message_at")
        ).join(
            Character, Character.id == Conversation.character_id
        ).join(
            User, User.id == Conversation.creator_id
        ).outerjoin(
            Message, Message.conversation_id == Conversation.id
        ).filter(
            Conversation.id == conversation_id
        ).group_by(
            Conversation.id, Character.name, Character.photo_url, User.username
        ).first()
        
        if not conv_query:
            raise HTTPException(status_code=404, detail="Conversation not found")
        
        # Get all messages for this conversation
        messages = db.query(Message).filter(
            Message.conversation_id == conversation_id
        ).order_by(Message.created_at).all()
        
        # Format messages
        message_responses = [
            AdminMessageResponse(
                id=msg.id,
                role=msg.role,
                content=msg.content,
                created_at=msg.created_at
            ) for msg in messages
        ]
        
        # Return conversation with messages
        return AdminConversationDetailResponse(
            id=conv_query.Conversation.id,
            character_id=conv_query.Conversation.character_id,
            character_name=conv_query.character_name,
            character_photo=conv_query.character_photo,
            user_id=conv_query.Conversation.creator_id,
            user_name=conv_query.user_name,
            message_count=conv_query.message_count,
            created_at=conv_query.Conversation.created_at,
            last_message_at=conv_query.last_message_at,
            messages=message_responses
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting conversation detail: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get conversation detail: {str(e)}")

# --- Helper Functions ---

def calculate_growth(old_value, new_value):
    """Calculate growth percentage between two values"""
    if old_value == 0:
        return 100.0 if new_value > 0 else 0.0
    
    growth = ((new_value - old_value) / old_value) * 100.0
    return round(growth, 1) 