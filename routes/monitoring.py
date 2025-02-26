from fastapi import APIRouter, Depends, Query, HTTPException
from typing import Dict, List, Optional
from datetime import datetime, timedelta
import json
from middleware.latency import get_latest_latency_records, get_endpoint_statistics
from middleware.db_monitor import get_query_records, get_query_statistics, get_table_statistics
from dependencies.auth import get_current_user
from database.models import User
import logging

# Configure logging
logger = logging.getLogger(__name__)

router = APIRouter()

@router.get("/latency/records")
async def get_latency_records(
    limit: int = Query(100, ge=1, le=1000),
    current_user: User = Depends(get_current_user)
):
    """Get the most recent latency records (requires authentication)"""
    # Only allow authenticated users to access this endpoint
    if not current_user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    return get_latest_latency_records(limit)

@router.get("/latency/stats")
async def get_latency_stats(
    current_user: User = Depends(get_current_user)
):
    """Get latency statistics by endpoint (requires authentication)"""
    # Only allow authenticated users to access this endpoint
    if not current_user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    return get_endpoint_statistics()

@router.get("/latency/slowest")
async def get_slowest_endpoints(
    limit: int = Query(10, ge=1, le=100),
    current_user: User = Depends(get_current_user)
):
    """Get the slowest endpoints by average response time (requires authentication)"""
    # Only allow authenticated users to access this endpoint
    if not current_user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    stats = get_endpoint_statistics()
    
    # Sort endpoints by average time (descending)
    sorted_endpoints = sorted(
        stats.items(), 
        key=lambda x: x[1]["avg_time_ms"], 
        reverse=True
    )
    
    # Return the top N slowest endpoints
    return dict(sorted_endpoints[:limit])

@router.get("/latency/summary")
async def get_latency_summary(
    current_user: User = Depends(get_current_user)
):
    """Get a summary of overall API performance (requires authentication)"""
    # Only allow authenticated users to access this endpoint
    if not current_user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    stats = get_endpoint_statistics()
    
    if not stats:
        return {
            "total_endpoints": 0,
            "total_requests": 0,
            "avg_response_time_ms": 0,
            "p95_response_time_ms": 0,
            "slowest_endpoint": None,
            "fastest_endpoint": None
        }
    
    # Calculate overall statistics
    total_requests = sum(e["count"] for e in stats.values())
    
    # Calculate weighted average response time
    total_weighted_time = sum(e["avg_time_ms"] * e["count"] for e in stats.values())
    avg_response_time = total_weighted_time / total_requests if total_requests > 0 else 0
    
    # Find slowest and fastest endpoints
    endpoints_with_traffic = {k: v for k, v in stats.items() if v["count"] > 0}
    
    if not endpoints_with_traffic:
        return {
            "total_endpoints": len(stats),
            "total_requests": 0,
            "avg_response_time_ms": 0,
            "p95_response_time_ms": 0,
            "slowest_endpoint": None,
            "fastest_endpoint": None
        }
    
    slowest_endpoint = max(endpoints_with_traffic.items(), key=lambda x: x[1]["avg_time_ms"])
    fastest_endpoint = min(endpoints_with_traffic.items(), key=lambda x: x[1]["avg_time_ms"])
    
    # Calculate 95th percentile across all endpoints (weighted by request count)
    # This is a rough approximation - for accuracy we'd need the raw data
    p95_times = [e["p95_time_ms"] for e in stats.values() if e["count"] > 0]
    p95_response_time = max(p95_times) if p95_times else 0
    
    return {
        "total_endpoints": len(stats),
        "total_requests": total_requests,
        "avg_response_time_ms": round(avg_response_time, 2),
        "p95_response_time_ms": round(p95_response_time, 2),
        "slowest_endpoint": {
            "endpoint": slowest_endpoint[0],
            "avg_time_ms": slowest_endpoint[1]["avg_time_ms"],
            "request_count": slowest_endpoint[1]["count"]
        },
        "fastest_endpoint": {
            "endpoint": fastest_endpoint[0],
            "avg_time_ms": fastest_endpoint[1]["avg_time_ms"],
            "request_count": fastest_endpoint[1]["count"]
        }
    }

# Database-specific monitoring endpoints
@router.get("/database/queries")
async def get_database_queries(
    limit: int = Query(100, ge=1, le=500),
    current_user: User = Depends(get_current_user)
):
    """Get the most recent database queries (requires authentication)"""
    if not current_user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    return get_query_records(limit)

@router.get("/database/query-stats")
async def get_database_query_stats(
    current_user: User = Depends(get_current_user)
):
    """Get statistics for database query types (requires authentication)"""
    if not current_user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    return get_query_statistics()

@router.get("/database/table-stats")
async def get_database_table_stats(
    current_user: User = Depends(get_current_user)
):
    """Get statistics for database tables (requires authentication)"""
    if not current_user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    return get_table_statistics()

@router.get("/database/slowest-queries")
async def get_slowest_queries(
    limit: int = Query(10, ge=1, le=100),
    current_user: User = Depends(get_current_user)
):
    """Get the slowest database queries by average execution time (requires authentication)"""
    if not current_user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    stats = get_query_statistics()
    
    # Sort queries by average time (descending)
    sorted_queries = sorted(
        stats.items(), 
        key=lambda x: x[1]["avg_time_ms"], 
        reverse=True
    )
    
    # Return the top N slowest queries
    return dict(sorted_queries[:limit])

@router.get("/database/summary")
async def get_database_summary(
    current_user: User = Depends(get_current_user)
):
    """Get a summary of overall database performance (requires authentication)"""
    if not current_user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    query_stats = get_query_statistics()
    table_stats = get_table_statistics()
    
    # No data yet
    if not query_stats:
        return {
            "total_queries": 0,
            "avg_query_time_ms": 0,
            "total_tables": len(table_stats),
            "most_queried_table": None,
            "slowest_table": None
        }
    
    # Calculate overall database statistics
    total_queries = sum(q["count"] for q in query_stats.values())
    
    # Calculate weighted average query time
    total_weighted_time = sum(q["avg_time_ms"] * q["count"] for q in query_stats.values())
    avg_query_time = total_weighted_time / total_queries if total_queries > 0 else 0
    
    # Identify most queried and slowest tables
    if table_stats:
        most_queried_table = max(table_stats.items(), key=lambda x: x[1]["total_queries"])
        slowest_table = max(table_stats.items(), key=lambda x: x[1]["avg_time_ms"])
    else:
        most_queried_table = None
        slowest_table = None
    
    return {
        "total_queries": total_queries,
        "avg_query_time_ms": round(avg_query_time, 2),
        "total_tables": len(table_stats),
        "most_queried_table": {
            "table": most_queried_table[0],
            "query_count": most_queried_table[1]["total_queries"],
            "read_count": most_queried_table[1]["read_queries"],
            "write_count": most_queried_table[1]["write_queries"]
        } if most_queried_table else None,
        "slowest_table": {
            "table": slowest_table[0],
            "avg_time_ms": slowest_table[1]["avg_time_ms"],
            "query_count": slowest_table[1]["total_queries"]
        } if slowest_table else None
    } 