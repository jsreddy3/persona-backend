import time
import uuid
import logging
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from services.timing import TimingService
from database.database import SessionLocal

# Configure logging
logger = logging.getLogger(__name__)

class TimingMiddleware(BaseHTTPMiddleware):
    """Middleware to track request timing"""
    
    async def dispatch(self, request: Request, call_next):
        # Generate a unique ID for this request
        request_id = str(uuid.uuid4())
        
        # Extract endpoint and method
        endpoint = request.url.path
        method = request.method
        
        # Create DB session for this request
        db = SessionLocal()
        
        try:
            # Initialize timing service
            timing_service = TimingService(db)
            
            # Start timing
            timing = timing_service.start_request(request_id, endpoint, method)
            
            # Store timing object in request state
            request.state.timing = timing
            request.state.timing_service = timing_service
            
            # Process request
            response = await call_next(request)
            
            # Extract user ID if available
            user_id = getattr(request.state, "user_id", None)
            if user_id:
                timing.user_id = user_id
            
            # Complete timing and save to database
            timing_data = timing_service.complete_request(request_id)
            
            # Add timing headers to response
            if timing_data:
                response.headers["X-Total-Time"] = str(timing_data["total_time_ms"])
                response.headers["X-DB-Time"] = str(timing_data["db_time_ms"])
                response.headers["X-LLM-Time"] = str(timing_data["llm_time_ms"])
                response.headers["X-Network-Time"] = str(timing_data["network_time_ms"])
                response.headers["X-App-Time"] = str(timing_data["app_time_ms"])
            
            return response
            
        except Exception as e:
            logger.error(f"Error in timing middleware: {str(e)}")
            # Make sure to continue processing the request even if timing fails
            return await call_next(request) if call_next else Response(status_code=500)
            
        finally:
            # Close DB session
            db.close() 