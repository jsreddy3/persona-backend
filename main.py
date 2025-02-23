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

app = FastAPI(title="PersonaAI API")

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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

# Print all registered routes for debugging
for route in app.routes:
    if hasattr(route, 'methods'):  # Only log actual routes, not mounted apps
        logger.info(f"Registered route: {route.path} [{','.join(route.methods)}]")

# Initialize database
init_db()
