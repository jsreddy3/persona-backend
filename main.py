from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import os
from routes import (
    user_routes,
    character_routes,
    conversation_routes,
    payment_routes,
    token_routes,
    timing_routes,
    # admin_routes  # Original admin routes
)
from routes import new_admin_routes  # New optimized admin routes
from routes import auth_routes  # New wallet auth routes
from routes import transcription_routes  # New transcription routes
from middleware import TimingMiddleware
from database.init_db import init_db
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="PersonaAI API")

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins for development
    allow_credentials=True,
    allow_methods=["*"],  # Allow all methods
    allow_headers=["*"],  # Allow all headers
    expose_headers=["*"],
)

# Language middleware
@app.middleware("http")
async def get_accept_language(request: Request, call_next):
    language = request.headers.get("accept-language", "en").split(",")[0].lower()
    # Store language in request state
    request.state.language = language
    response = await call_next(request)
    return response

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Root path redirects to index.html
@app.get("/")
async def root():
    return FileResponse("static/index.html")

# Include routers with API prefix
api_prefix = "/api"
app.include_router(user_routes.router, prefix=f"{api_prefix}/users", tags=["users"])
app.include_router(character_routes.router, prefix=f"{api_prefix}/characters", tags=["characters"])
app.include_router(conversation_routes.router, prefix=f"{api_prefix}/conversations", tags=["conversations"])
app.include_router(payment_routes.router, prefix=f"{api_prefix}/payments", tags=["payments"])
app.include_router(token_routes.router, prefix=f"{api_prefix}/tokens", tags=["tokens"])
app.include_router(timing_routes.router, prefix=f"{api_prefix}/timing", tags=["timing"])
app.include_router(auth_routes.router, prefix=f"{api_prefix}/auth", tags=["auth"])  # New wallet auth routes
# app.include_router(admin_routes.router, prefix=f"{api_prefix}/admin", tags=["admin"])  # Original admin routes
app.include_router(new_admin_routes.router, prefix=f"{api_prefix}/admin", tags=["admin"])  # New optimized admin routes
app.include_router(transcription_routes.router, prefix=f"{api_prefix}/transcription", tags=["transcription"])  # New transcription routes

# Print all registered routes for debugging
for route in app.routes:
    if hasattr(route, 'methods'):  # Only log actual routes, not mounted apps
        logger.info(f"Registered route: {route.path} [{','.join(route.methods)}]")

# Initialize database
init_db()

# Log initialization
logger.info("PersonaAI API initialized successfully")
