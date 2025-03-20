import logging
import time
import functools
from typing import Any, Callable, Dict, Optional, TypeVar, cast
from datetime import datetime, timedelta
from sqlalchemy import text
from sqlalchemy.orm import Session

# Set up logging
logger = logging.getLogger(__name__)

# Simple in-memory cache
_cache: Dict[str, Dict[str, Any]] = {}

T = TypeVar('T')

def cached(
    ttl_seconds: int = 300,  # Default: 5 minutes
    key_prefix: str = "admin_cache"
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """
    Decorator to cache the result of a function.
    
    Args:
        ttl_seconds: Time to live in seconds
        key_prefix: Prefix for the cache key
        
    Returns:
        Decorated function with caching
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            # Generate cache key
            cache_key = f"{key_prefix}:{func.__name__}"
            
            # Check if the result is in the cache and not expired
            if cache_key in _cache:
                cache_data = _cache[cache_key]
                if cache_data["expires"] > time.time():
                    logger.info(f"Cache hit for {cache_key}")
                    return cast(T, cache_data["data"])
                else:
                    logger.info(f"Cache expired for {cache_key}")
                    del _cache[cache_key]
            
            # Execute the function
            start_time = time.time()
            result = func(*args, **kwargs)
            execution_time = time.time() - start_time
            
            # Store the result in the cache
            _cache[cache_key] = {
                "data": result,
                "expires": time.time() + ttl_seconds,
                "execution_time": execution_time
            }
            
            logger.info(f"Cached result for {cache_key} (took {execution_time:.2f}s)")
            return result
        
        return wrapper
    
    return decorator

def clear_cache(key_prefix: Optional[str] = None) -> None:
    """
    Clear the cache for a specific prefix or all cached items.
    
    Args:
        key_prefix: Prefix to clear, or None to clear all
    """
    global _cache
    
    if key_prefix:
        # Clear only keys with the specified prefix
        keys_to_remove = [k for k in _cache.keys() if k.startswith(key_prefix)]
        for key in keys_to_remove:
            del _cache[key]
        logger.info(f"Cleared {len(keys_to_remove)} items from cache with prefix '{key_prefix}'")
    else:
        # Clear the entire cache
        _cache = {}
        logger.info("Cleared entire cache")

def execute_with_timeout(
    db: Session, 
    query: str, 
    params: Optional[Dict[str, Any]] = None,
    timeout_seconds: int = 5
) -> Any:
    """
    Execute a SQL query with a timeout.
    
    Args:
        db: Database session
        query: SQL query string
        params: Query parameters
        timeout_seconds: Query timeout in seconds
        
    Returns:
        Query result
    """
    try:
        # Add timeout to the query execution options
        result = db.execute(
            text(query).execution_options(timeout=timeout_seconds), 
            params or {}
        )
        
        # Return result (fetchall for multiple rows, scalar for single value)
        return result
        
    except Exception as e:
        logger.error(f"Database query failed: {str(e)}")
        raise 

async def execute_query(db: Session, query, params=None):
    """
    Execute a SQL query with a timeout.
    
    Args:
        db: Database session
        query: SQL query object (text)
        params: Query parameters
        
    Returns:
        Query result
    """
    try:
        # Add timeout to the query execution options (5 seconds)
        result = db.execute(
            query.execution_options(timeout=5), 
            params or {}
        )
        return result
        
    except Exception as e:
        logger.error(f"Database query failed: {str(e)}")
        raise

def get_cached_result(key):
    """Get a result from the cache by key"""
    if key in _cache and _cache[key]["expires"] > time.time():
        logger.info(f"Cache hit for {key}")
        return _cache[key]["data"]
    return None

def cache_result(key, data, ttl_seconds=300):
    """Store a result in the cache"""
    _cache[key] = {
        "data": data,
        "expires": time.time() + ttl_seconds,
        "timestamp": time.time()
    }
    logger.info(f"Cached result for {key} (expires in {ttl_seconds}s)")

def invalidate_cache(key_pattern=None):
    """Invalidate cache entries matching a pattern"""
    global _cache
    
    if key_pattern:
        # Clear only keys with the specified pattern
        keys_to_remove = [k for k in list(_cache.keys()) if key_pattern in k]
        for key in keys_to_remove:
            del _cache[key]
        logger.info(f"Invalidated {len(keys_to_remove)} cache entries matching '{key_pattern}'")
    else:
        # Clear the entire cache
        _cache = {}
        logger.info("Invalidated entire cache") 