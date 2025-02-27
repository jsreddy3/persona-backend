#!/usr/bin/env python
"""
Script to get user statistics including language distribution.
Run from project root with: python -m backend_persona.scripts.user_stats
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from sqlalchemy import func
from backend_persona.database.database import SessionLocal
from backend_persona.database.models import User

def get_language_stats():
    """Get user statistics by language"""
    db = SessionLocal()
    try:
        # Count users by language
        result = db.query(
            User.language,
            func.count(User.id).label('user_count')
        ).group_by(
            User.language
        ).order_by(
            func.count(User.id).desc()
        ).all()
        
        # Print formatted results
        total_users = sum(count for _, count in result)
        
        print(f"\n{'=' * 50}")
        print(f"USER LANGUAGE STATISTICS - TOTAL USERS: {total_users}")
        print(f"{'=' * 50}")
        print(f"{'LANGUAGE':<10} | {'COUNT':<8} | {'PERCENTAGE':<10}")
        print(f"{'-' * 10} | {'-' * 8} | {'-' * 10}")
        
        for language, count in result:
            percentage = (count / total_users) * 100 if total_users > 0 else 0
            print(f"{language:<10} | {count:<8} | {percentage:.2f}%")
            
        print(f"{'=' * 50}\n")
        
    finally:
        db.close()

if __name__ == "__main__":
    get_language_stats() 