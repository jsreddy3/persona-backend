"""
New optimized and modular admin routes for the Persona application.

This file serves as a wrapper module to transition from the original admin_routes.py to
the new modular structure without requiring changes to the main application file.
"""

from fastapi import APIRouter
from routes.admin import router as admin_router

# Re-export the router for use in the main application
router = admin_router 