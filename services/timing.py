import time
import logging
from datetime import datetime
from typing import Dict, Optional, List
from sqlalchemy.orm import Session
from functools import wraps
import inspect

# Configure logging
logger = logging.getLogger(__name__)

class RequestTiming:
    """Class to track timing for a specific request"""
    
    def __init__(self, request_id: str, endpoint: str, method: str, user_id: Optional[int] = None):
        self.request_id = request_id
        self.endpoint = endpoint
        self.method = method
        self.user_id = user_id
        self.start_time = time.time()
        self.end_time = None
        self.llm_start_time = None
        self.llm_end_time = None
        self.db_time = 0.0  # Cumulative DB time
        self.db_operations = 0  # Count of DB operations
        self.is_complete = False
        self.markers = {}  # Custom timing markers
        self.network_time = 0.0  # Time spent in network operations
    
    def mark(self, marker_name: str):
        """Mark a specific point in time during request processing"""
        self.markers[marker_name] = time.time() - self.start_time
    
    def start_llm(self):
        """Mark start of LLM processing"""
        self.llm_start_time = time.time()
    
    def end_llm(self):
        """Mark end of LLM processing"""
        if self.llm_start_time:
            self.llm_end_time = time.time()
    
    def add_db_time(self, db_time: float):
        """Add time spent in database operations"""
        self.db_time += db_time
        self.db_operations += 1
    
    def add_network_time(self, network_time: float):
        """Add time spent in network operations"""
        self.network_time += network_time
    
    def complete(self):
        """Mark request as complete and calculate final timing"""
        self.end_time = time.time()
        self.is_complete = True
    
    def get_total_time(self) -> float:
        """Get total request time in seconds"""
        end = self.end_time or time.time()
        return end - self.start_time
    
    def get_llm_time(self) -> float:
        """Get time spent in LLM processing in seconds"""
        if not self.llm_start_time:
            return 0.0
        end = self.llm_end_time or time.time()
        return end - self.llm_start_time
    
    def get_app_time(self) -> float:
        """Get time spent in application code (excluding DB, LLM, and network)"""
        total = self.get_total_time()
        llm = self.get_llm_time()
        return total - (self.db_time + llm + self.network_time)
    
    def to_dict(self) -> Dict:
        """Convert timing data to dictionary"""
        return {
            "request_id": self.request_id,
            "endpoint": self.endpoint,
            "method": self.method,
            "user_id": self.user_id,
            "start_time": datetime.fromtimestamp(self.start_time).isoformat(),
            "end_time": datetime.fromtimestamp(self.end_time).isoformat() if self.end_time else None,
            "total_time_ms": round(self.get_total_time() * 1000, 2),
            "llm_time_ms": round(self.get_llm_time() * 1000, 2),
            "db_time_ms": round(self.db_time * 1000, 2),
            "db_operations": self.db_operations,
            "network_time_ms": round(self.network_time * 1000, 2),
            "app_time_ms": round(self.get_app_time() * 1000, 2),
            "markers": {k: round(v * 1000, 2) for k, v in self.markers.items()},
            "is_complete": self.is_complete
        }

class TimingService:
    """Service to manage request timing"""
    
    def __init__(self, db: Session):
        self.db = db
        self.active_timings = {}  # Store active request timings
    
    def start_request(self, request_id: str, endpoint: str, method: str, user_id: Optional[int] = None) -> RequestTiming:
        """Start timing a new request"""
        timing = RequestTiming(request_id, endpoint, method, user_id)
        self.active_timings[request_id] = timing
        return timing
    
    def get_timing(self, request_id: str) -> Optional[RequestTiming]:
        """Get timing for a request by ID"""
        return self.active_timings.get(request_id)
    
    def complete_request(self, request_id: str) -> Optional[Dict]:
        """Complete timing for a request and save to database"""
        timing = self.active_timings.get(request_id)
        if not timing:
            return None
        
        timing.complete()
        
        # Store in database
        try:
            from database.models import RequestLog  # Import here to avoid circular imports
            
            log_entry = RequestLog(
                request_id=timing.request_id,
                endpoint=timing.endpoint,
                method=timing.method,
                user_id=timing.user_id,
                timestamp=datetime.fromtimestamp(timing.start_time),
                total_time_ms=round(timing.get_total_time() * 1000, 2),
                llm_time_ms=round(timing.get_llm_time() * 1000, 2),
                db_time_ms=round(timing.db_time * 1000, 2),
                db_operations=timing.db_operations,
                network_time_ms=round(timing.network_time * 1000, 2),
                app_time_ms=round(timing.get_app_time() * 1000, 2),
                markers=timing.markers
            )
            
            self.db.add(log_entry)
            self.db.commit()
            
        except Exception as e:
            logger.error(f"Failed to save timing data: {str(e)}")
            self.db.rollback()
        
        # Return timing data and remove from active timings
        timing_data = timing.to_dict()
        del self.active_timings[request_id]
        return timing_data
    
    def get_recent_logs(self, limit: int = 100) -> List[Dict]:
        """Get recent request logs from database"""
        try:
            from database.models import RequestLog
            
            logs = self.db.query(RequestLog).order_by(
                RequestLog.timestamp.desc()
            ).limit(limit).all()
            
            return [log.to_dict() for log in logs]
            
        except Exception as e:
            logger.error(f"Failed to retrieve request logs: {str(e)}")
            return []
    
    def get_endpoint_stats(self, endpoint: Optional[str] = None) -> Dict:
        """Get statistics for endpoints"""
        try:
            from database.models import RequestLog
            from sqlalchemy import func, desc
            
            query = self.db.query(
                RequestLog.endpoint,
                func.count(RequestLog.id).label('count'),
                func.avg(RequestLog.total_time_ms).label('avg_total_time'),
                func.avg(RequestLog.llm_time_ms).label('avg_llm_time'),
                func.avg(RequestLog.db_time_ms).label('avg_db_time'),
                func.avg(RequestLog.network_time_ms).label('avg_network_time'),
                func.avg(RequestLog.app_time_ms).label('avg_app_time'),
                func.min(RequestLog.total_time_ms).label('min_time'),
                func.max(RequestLog.total_time_ms).label('max_time')
            )
            
            if endpoint:
                query = query.filter(RequestLog.endpoint == endpoint)
                
            stats = query.group_by(RequestLog.endpoint).order_by(desc('count')).all()
            
            result = {}
            for stat in stats:
                result[stat.endpoint] = {
                    "count": stat.count,
                    "avg_total_time_ms": round(float(stat.avg_total_time), 2),
                    "avg_llm_time_ms": round(float(stat.avg_llm_time), 2),
                    "avg_db_time_ms": round(float(stat.avg_db_time), 2),
                    "avg_network_time_ms": round(float(stat.avg_network_time), 2),
                    "avg_app_time_ms": round(float(stat.avg_app_time), 2),
                    "min_time_ms": round(float(stat.min_time), 2),
                    "max_time_ms": round(float(stat.max_time), 2),
                }
            
            return result
            
        except Exception as e:
            logger.error(f"Failed to get endpoint stats: {str(e)}")
            return {}

# Decorators for easy timing
def time_db_operation(func):
    """Decorator to time database operations"""
    if inspect.iscoroutinefunction(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            from fastapi import Request
            
            # Try to get request from args or kwargs
            request = next((arg for arg in args if isinstance(arg, Request)), kwargs.get('request'))
            
            start_time = time.time()
            result = await func(*args, **kwargs)
            db_time = time.time() - start_time
            
            # Update request timing if available
            if request and hasattr(request.state, 'timing'):
                request.state.timing.add_db_time(db_time)
            else:
                # Log but continue if no request or timing available
                logger.debug(f"DB operation timed: {func.__name__} took {db_time:.4f}s (no request context)")
            
            return result
        return async_wrapper
    else:
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            from fastapi import Request
            
            # Try to get request from args or kwargs
            request = next((arg for arg in args if isinstance(arg, Request)), kwargs.get('request'))
            
            start_time = time.time()
            result = func(*args, **kwargs)
            db_time = time.time() - start_time
            
            # Update request timing if available
            if request and hasattr(request.state, 'timing'):
                request.state.timing.add_db_time(db_time)
            else:
                # Log but continue if no request or timing available
                logger.debug(f"DB operation timed: {func.__name__} took {db_time:.4f}s (no request context)")
            
            return result
        return sync_wrapper

def time_llm_operation(func):
    """Decorator to time LLM operations"""
    if inspect.iscoroutinefunction(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            from fastapi import Request
            
            # Try to get request from args or kwargs
            request = next((arg for arg in args if isinstance(arg, Request)), kwargs.get('request'))
            
            # Mark LLM start
            if request and hasattr(request.state, 'timing'):
                request.state.timing.start_llm()
            
            result = await func(*args, **kwargs)
            
            # Mark LLM end
            if request and hasattr(request.state, 'timing'):
                request.state.timing.end_llm()
            
            return result
        return async_wrapper
    else:
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            from fastapi import Request
            
            # Try to get request from args or kwargs
            request = next((arg for arg in args if isinstance(arg, Request)), kwargs.get('request'))
            
            # Mark LLM start
            if request and hasattr(request.state, 'timing'):
                request.state.timing.start_llm()
            
            result = func(*args, **kwargs)
            
            # Mark LLM end
            if request and hasattr(request.state, 'timing'):
                request.state.timing.end_llm()
            
            return result
        return sync_wrapper

def time_network_operation(func):
    """Decorator to time network operations"""
    if inspect.iscoroutinefunction(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            from fastapi import Request
            
            # Try to get request from args or kwargs
            request = next((arg for arg in args if isinstance(arg, Request)), kwargs.get('request'))
            
            start_time = time.time()
            result = await func(*args, **kwargs)
            network_time = time.time() - start_time
            
            # Update request timing if available
            if request and hasattr(request.state, 'timing'):
                request.state.timing.add_network_time(network_time)
            else:
                # Log but continue if no request or timing available
                logger.debug(f"Network operation timed: {func.__name__} took {network_time:.4f}s (no request context)")
            
            return result
        return async_wrapper
    else:
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            from fastapi import Request
            
            # Try to get request from args or kwargs
            request = next((arg for arg in args if isinstance(arg, Request)), kwargs.get('request'))
            
            start_time = time.time()
            result = func(*args, **kwargs)
            network_time = time.time() - start_time
            
            # Update request timing if available
            if request and hasattr(request.state, 'timing'):
                request.state.timing.add_network_time(network_time)
            else:
                # Log but continue if no request or timing available
                logger.debug(f"Network operation timed: {func.__name__} took {network_time:.4f}s (no request context)")
            
            return result
        return sync_wrapper 