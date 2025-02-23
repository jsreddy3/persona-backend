from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import os
from routes import character_routes
from routes import user_routes
from routes import conversation_routes
from routes import payment_routes
from database.init_db import init_db
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(title="PersonaAI API")

# Configure CORS - keep it simple first
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Debug: Print middleware
logger.info("Registered middleware:")
for middleware in app.user_middleware:
    logger.info(f"Middleware: {middleware}")

# API prefix
api_prefix = "/api"

# Include routers
app.include_router(
    user_routes.router,
    prefix=f"{api_prefix}/users",
    tags=["users"]
)
app.include_router(
    character_routes.router,
    prefix=f"{api_prefix}/characters",
    tags=["characters"]
)
app.include_router(
    conversation_routes.router,
    prefix=f"{api_prefix}/conversations",
    tags=["conversations"]
)
app.include_router(
    payment_routes.router,
    prefix=f"{api_prefix}/payments",
    tags=["payments"]
)

# Mount static files
static_dir = os.path.join(os.path.dirname(__file__), "static")
os.makedirs(static_dir, exist_ok=True)
app.mount("/static", StaticFiles(directory=static_dir), name="static")

# Root path redirects to index.html
@app.get("/")
async def root():
    return FileResponse("static/index.html")

# Print all registered routes for debugging
logger.info("Registered routes:")
for route in app.routes:
    if hasattr(route, 'methods'):
        logger.info(f"Route: {route.path} [{','.join(route.methods)}]")

# Initialize database
init_db()
