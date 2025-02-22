from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import os
from routes import character_routes
from routes import user_routes
from routes import conversation_routes
from database.init_db import init_db

app = FastAPI(title="PersonaAI API")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",  # Local frontend
        "http://localhost:8000",  # Local backend static files
        "https://backend-persona-da6c29e3bf72.herokuapp.com"  # Heroku domain
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Create static directory if it doesn't exist
static_dir = os.path.join(os.path.dirname(__file__), "static")
os.makedirs(static_dir, exist_ok=True)

# Mount static files
app.mount("/static", StaticFiles(directory=static_dir), name="static")

# Initialize database
init_db()

# Include routers
app.include_router(character_routes.router)
app.include_router(user_routes.router)
app.include_router(conversation_routes.router)

@app.get("/")
async def root():
    return {"message": "Welcome to PersonaAI API"}
