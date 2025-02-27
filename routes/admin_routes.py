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
    # Additional stats for detailed view
    newMessages: Optional[int] = None
    avgMessagesPerConversation: Optional[float] = None
    activeUsers: Optional[int] = None
    completionRate: Optional[float] = None

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
        
        # Get counts from 24 hours ago for growth calculation
        one_day_ago = datetime.utcnow() - timedelta(days=1)
        
        # Users created in the last 24 hours
        users_24h = db.query(func.count(User.id)).filter(
            User.created_at >= one_day_ago
        ).scalar()
        
        # Active conversations in the last 24 hours (already calculated above)
        
        # Characters created in the last 24 hours
        characters_24h = db.query(func.count(Character.id)).filter(
            Character.created_at >= one_day_ago
        ).scalar()
        
        # Credits purchased in the last 24 hours
        credits_24h = db.query(func.sum(Payment.amount)).filter(
            and_(
                Payment.status == "confirmed",
                Payment.created_at >= one_day_ago
            )
        ).scalar() or 0
        
        # Calculate growth percentages based on 24-hour contribution
        # For a new app, we'll show the percentage of total that was added in the last 24h
        user_growth = calculate_24h_growth(users_24h, total_users)
        conversation_growth = 100.0  # All active conversations are by definition from last 24h
        character_growth = calculate_24h_growth(characters_24h, total_characters)
        credit_growth = calculate_24h_growth(credits_24h, total_credits)
        
        # Additional detailed stats
        
        # New messages in the last 24 hours
        new_messages = db.query(func.count(Message.id)).filter(
            Message.created_at >= one_day_ago
        ).scalar() or 0
        
        # Get average messages per conversation by first calculating per conversation
        conversation_message_counts = db.query(
            Message.conversation_id,
            func.count(Message.id).label('message_count')
        ).group_by(Message.conversation_id).all()
        
        if conversation_message_counts:
            avg_messages = sum(count for _, count in conversation_message_counts) / len(conversation_message_counts)
        else:
            avg_messages = 0
        
        # Active users in the last 24 hours (users who sent at least one message)
        active_users = db.query(func.count(func.distinct(Conversation.creator_id))).filter(
            Conversation.updated_at >= one_day_ago
        ).scalar() or 0
        
        # Completion rate (percentage of conversations with at least 3 messages)
        total_convs = db.query(func.count(Conversation.id)).scalar() or 1  # Avoid division by zero
        completed_convs = db.query(func.count(Conversation.id)).filter(
            db.query(func.count(Message.id))
            .filter(Message.conversation_id == Conversation.id)
            .correlate(Conversation)
            .as_scalar() >= 3
        ).scalar() or 0
        completion_rate = (completed_convs / total_convs) * 100
        
        return DashboardStats(
            totalUsers=total_users,
            activeConversations=active_conversations,
            charactersCreated=total_characters,
            creditsPurchased=total_credits,
            userGrowth=user_growth,
            conversationGrowth=conversation_growth,
            characterGrowth=character_growth,
            creditGrowth=credit_growth,
            # Additional detailed stats
            newMessages=new_messages,
            avgMessagesPerConversation=round(avg_messages, 1),
            activeUsers=active_users,
            completionRate=round(completion_rate, 1),
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

@router.get("/analytics/user-stats", response_model=UserStats)
async def get_user_stats(
    db: Session = Depends(get_db),
    is_admin: bool = Depends(get_admin_access)
):
    """Get user statistics for the admin panel"""
    try:
        # Calculate time thresholds
        now = datetime.utcnow()
        one_day_ago = now - timedelta(days=1)
        seven_days_ago = now - timedelta(days=7)
        
        # Get total users count
        total_users = db.query(func.count(User.id)).scalar()
        
        # Get active users in the last 24 hours
        active_users_24h = db.query(func.count(func.distinct(User.id))).filter(
            User.last_active >= one_day_ago
        ).scalar()
        
        # Get new users in the last 7 days
        new_users_7d = db.query(func.count(User.id)).filter(
            User.created_at >= seven_days_ago
        ).scalar()
        
        return UserStats(
            totalUsers=total_users,
            activeUsers24h=active_users_24h,
            newUsers7d=new_users_7d
        )
    except Exception as e:
        logger.error(f"Error getting user stats: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get user stats: {str(e)}")

@router.get("/analytics/user-historical", response_model=UserHistoricalData)
async def get_user_historical_data(
    days: int = Query(30, ge=7, le=90),  # Default to 30 days, min 7, max 90
    db: Session = Depends(get_db),
    is_admin: bool = Depends(get_admin_access)
):
    """Get historical user data for charts and visualizations"""
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
        
        # Generate data for each day in the range
        current_date = start_date
        while current_date <= end_date:
            next_date = current_date + timedelta(days=1)
            date_str = current_date.strftime("%Y-%m-%d")
            dates.append(date_str)
            
            # Total users up to this date
            total = db.query(func.count(User.id)).filter(
                User.created_at < next_date
            ).scalar() or 0
            total_users.append(total)
            
            # Active users on this day
            active = db.query(func.count(func.distinct(User.id))).filter(
                User.last_active >= current_date,
                User.last_active < next_date
            ).scalar() or 0
            active_users.append(active)
            
            # New users on this day
            new = db.query(func.count(User.id)).filter(
                User.created_at >= current_date,
                User.created_at < next_date
            ).scalar() or 0
            new_users.append(new)
            
            # Retention rate (users who were active today out of users who existed before today)
            users_before_today = db.query(func.count(User.id)).filter(
                User.created_at < current_date
            ).scalar() or 1  # Avoid division by zero
            
            retention = (active / users_before_today) * 100 if users_before_today > 0 else 0
            retention_rates.append(round(retention, 2))
            
            current_date = next_date
        
        # Get message counts per user
        message_counts = db.query(
            User.id,
            func.count(Message.id).label("message_count")
        ).outerjoin(
            Conversation, Conversation.creator_id == User.id
        ).outerjoin(
            Message, Message.conversation_id == Conversation.id
        ).group_by(User.id).all()
        
        # Categorize users by activity level
        activity_buckets = {
            "0 messages": 0,
            "1-5 messages": 0,
            "6-20 messages": 0,
            "21-50 messages": 0,
            "51-100 messages": 0,
            "101+ messages": 0
        }
        
        for _, count in message_counts:
            if count == 0:
                activity_buckets["0 messages"] += 1
            elif count <= 5:
                activity_buckets["1-5 messages"] += 1
            elif count <= 20:
                activity_buckets["6-20 messages"] += 1
            elif count <= 50:
                activity_buckets["21-50 messages"] += 1
            elif count <= 100:
                activity_buckets["51-100 messages"] += 1
            else:
                activity_buckets["101+ messages"] += 1
        
        return UserHistoricalData(
            dates=dates,
            totalUsers=total_users,
            activeUsers=active_users,
            newUsers=new_users,
            retentionRate=retention_rates,
            activityDistribution=activity_buckets
        )
    except Exception as e:
        logger.error(f"Error getting user historical data: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get user historical data: {str(e)}")

# --- User Management Endpoints ---

@router.get("/users", response_model=Dict[str, Any])
async def get_users(
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=100),
    search: Optional[str] = None,
    sort_by: Optional[str] = "id",
    sort_dir: Optional[str] = "desc",
    db: Session = Depends(get_db),
    is_admin: bool = Depends(get_admin_access)
):
    """Get all users with pagination, optional search, and sorting"""
    try:
        # Validate sort direction
        if sort_dir not in ["asc", "desc"]:
            sort_dir = "desc"  # Default to descending if invalid
        
        # Handle special sorting cases for derived fields
        if sort_by in ["character_count", "conversation_count", "message_count"]:
            # For these fields, we need to join with the appropriate tables and apply sorting at the database level
            
            # Base query with user information
            if sort_by == "character_count":
                # Count characters and join with users
                query = db.query(
                    User,
                    func.count(Character.id).label("character_count")
                ).outerjoin(
                    Character, Character.creator_id == User.id
                ).group_by(User.id)
                
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
                
                # Apply sorting
                query = query.order_by(desc("character_count") if sort_dir == "desc" else "character_count")
                
            elif sort_by == "conversation_count":
                # Count conversations and join with users
                query = db.query(
                    User,
                    func.count(Conversation.id).label("conversation_count")
                ).outerjoin(
                    Conversation, Conversation.creator_id == User.id
                ).group_by(User.id)
                
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
                
                # Apply sorting
                query = query.order_by(desc("conversation_count") if sort_dir == "desc" else "conversation_count")
                
            elif sort_by == "message_count":
                # Count messages through conversations and join with users
                query = db.query(
                    User,
                    func.count(Message.id).label("message_count")
                ).outerjoin(
                    Conversation, Conversation.creator_id == User.id
                ).outerjoin(
                    Message, Message.conversation_id == Conversation.id
                ).group_by(User.id)
                
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
                
                # Apply sorting
                query = query.order_by(desc("message_count") if sort_dir == "desc" else "message_count")
            
            # Calculate total for pagination
            total = query.count()
            
            # Apply pagination
            query_results = query.offset((page - 1) * limit).limit(limit).all()
            
            # Process results
            result = []
            for query_result in query_results:
                user = query_result[0]  # The User object
                
                # Get the count that was used for sorting
                primary_count = query_result[1]
                
                # Get the other counts that weren't used for sorting
                if sort_by == "character_count":
                    character_count = primary_count
                    conversation_count = db.query(func.count(Conversation.id)).filter(
                        Conversation.creator_id == user.id
                    ).scalar()
                    message_count = db.query(func.count(Message.id)).join(
                        Conversation, Conversation.id == Message.conversation_id
                    ).filter(
                        Conversation.creator_id == user.id
                    ).scalar()
                elif sort_by == "conversation_count":
                    character_count = db.query(func.count(Character.id)).filter(
                        Character.creator_id == user.id
                    ).scalar()
                    conversation_count = primary_count
                    message_count = db.query(func.count(Message.id)).join(
                        Conversation, Conversation.id == Message.conversation_id
                    ).filter(
                        Conversation.creator_id == user.id
                    ).scalar()
                else:  # message_count
                    character_count = db.query(func.count(Character.id)).filter(
                        Character.creator_id == user.id
                    ).scalar()
                    conversation_count = db.query(func.count(Conversation.id)).filter(
                        Conversation.creator_id == user.id
                    ).scalar()
                    message_count = primary_count
                
                user_data = AdminUserResponse(
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
                result.append(user_data)
        else:
            # Standard query for directly sortable fields
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
            
            # Apply sorting based on parameters
            if sort_by == "id":
                query = query.order_by(desc(User.id) if sort_dir == "desc" else User.id)
            elif sort_by == "username":
                query = query.order_by(desc(User.username) if sort_dir == "desc" else User.username)
            elif sort_by == "credits":
                query = query.order_by(desc(User.credits) if sort_dir == "desc" else User.credits)
            elif sort_by == "created_at":
                query = query.order_by(desc(User.created_at) if sort_dir == "desc" else User.created_at)
            elif sort_by == "last_active":
                query = query.order_by(desc(User.last_active) if sort_dir == "desc" else User.last_active)
            else:
                # Default to created_at if sort field is not directly available
                query = query.order_by(desc(User.created_at) if sort_dir == "desc" else User.created_at)
            
            # Apply pagination
            users = query.offset((page - 1) * limit).limit(limit).all()
            
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
                
                user_data = AdminUserResponse(
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
                result.append(user_data)
        
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

def calculate_24h_growth(last_24h_value, total_value):
    """Calculate what percentage of the total was added in the last 24 hours"""
    if total_value == 0:
        return 0.0
    
    percentage = (last_24h_value / total_value) * 100.0
    return round(percentage, 1) 