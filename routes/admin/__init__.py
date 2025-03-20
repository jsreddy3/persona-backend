from fastapi import APIRouter

# Create main admin router
router = APIRouter()

# Import all route modules
from .dashboard import router as dashboard_router
from .health import router as health_router
from .activity import router as activity_router
from .users import router as users_router
from .characters import router as characters_router
from .conversations import router as conversations_router

# Include all routers
router.include_router(health_router)
router.include_router(dashboard_router)
router.include_router(activity_router)
router.include_router(users_router)
router.include_router(characters_router)
router.include_router(conversations_router) 