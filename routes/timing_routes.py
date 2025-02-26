from fastapi import APIRouter, Depends, Query, HTTPException
from typing import Dict, List, Optional
from sqlalchemy.orm import Session
from database.database import get_db
from database.models import User, RequestLog
from services.timing import TimingService
from dependencies.auth import get_current_user
import logging

# Configure logging
logger = logging.getLogger(__name__)

router = APIRouter()

@router.get("/logs")
async def get_request_logs(
    limit: int = Query(100, ge=1, le=1000),
    endpoint: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get recent request timing logs (requires authentication)"""
    if not current_user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    service = TimingService(db)
    
    # Filter by endpoint if specified
    if endpoint:
        logs = db.query(RequestLog).filter(
            RequestLog.endpoint == endpoint
        ).order_by(RequestLog.timestamp.desc()).limit(limit).all()
    else:
        logs = db.query(RequestLog).order_by(
            RequestLog.timestamp.desc()
        ).limit(limit).all()
    
    return [log.to_dict() for log in logs]

@router.get("/stats")
async def get_timing_stats(
    endpoint: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get timing statistics by endpoint (requires authentication)"""
    if not current_user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    service = TimingService(db)
    return service.get_endpoint_stats(endpoint)

@router.get("/message-operations")
async def get_message_operation_stats(
    limit: int = Query(100, ge=1, le=500),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get detailed stats about message operation timings (requires authentication)"""
    if not current_user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    # Query for message-related endpoints
    logs = db.query(RequestLog).filter(
        RequestLog.endpoint.like('%/messages%') 
    ).order_by(RequestLog.timestamp.desc()).limit(limit).all()
    
    # Aggregate timing data across network, LLM, and db operations
    if not logs:
        return {
            "total_operations": 0,
            "avg_total_time_ms": 0,
            "avg_network_time_ms": 0,
            "avg_llm_time_ms": 0,
            "avg_db_time_ms": 0,
            "distribution": {
                "network_pct": 0,
                "llm_pct": 0,
                "db_pct": 0,
                "app_pct": 0
            },
            "operations": []
        }
    
    # Calculate distributions and averages
    total_time = sum(log.total_time_ms for log in logs)
    network_time = sum(log.network_time_ms for log in logs)
    llm_time = sum(log.llm_time_ms for log in logs)
    db_time = sum(log.db_time_ms for log in logs)
    app_time = sum(log.app_time_ms for log in logs)
    
    count = len(logs)
    
    return {
        "total_operations": count,
        "avg_total_time_ms": round(total_time / count, 2),
        "avg_network_time_ms": round(network_time / count, 2),
        "avg_llm_time_ms": round(llm_time / count, 2),
        "avg_db_time_ms": round(db_time / count, 2),
        "distribution": {
            "network_pct": round((network_time / total_time) * 100, 2) if total_time > 0 else 0,
            "llm_pct": round((llm_time / total_time) * 100, 2) if total_time > 0 else 0,
            "db_pct": round((db_time / total_time) * 100, 2) if total_time > 0 else 0,
            "app_pct": round((app_time / total_time) * 100, 2) if total_time > 0 else 0
        },
        "operations": [log.to_dict() for log in logs]
    } 