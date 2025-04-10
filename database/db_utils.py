from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
import logging

logger = logging.getLogger(__name__)

def increment_counter(db, table, user_id, counter_field, amount=1):
    """
    Atomically increment a counter without using the read-modify-write pattern.
    Uses direct SQL execution to minimize roundtrips and avoid conflicts.
    
    Args:
        db: SQLAlchemy session
        table: Table name (string)
        user_id: ID of the user/record to update
        counter_field: Name of the counter field to increment
        amount: Amount to increment by (default 1)
    """
    sql = text(f"""
        UPDATE {table} 
        SET {counter_field} = {counter_field} + :amount 
        WHERE id = :user_id
    """)
    db.execute(sql, {"amount": amount, "user_id": user_id})

def batch_update(db, updates):
    """
    Execute multiple updates in a single transaction.
    
    Args:
        db: SQLAlchemy session
        updates: List of (sql_statement, params_dict) tuples
    """
    try:
        for sql, params in updates:
            db.execute(text(sql), params)
        db.commit()
        return True
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Batch update failed: {str(e)}")
        return False

def update_with_lock(db, model_class, id_value, update_func):
    """
    Update a record with row-level locking to prevent conflicts.
    
    Args:
        db: SQLAlchemy session
        model_class: SQLAlchemy model class
        id_value: ID of the record to update
        update_func: Function that takes the record and updates it
    
    Returns:
        The updated record
    """
    record = db.query(model_class).with_for_update().filter(model_class.id == id_value).first()
    if not record:
        return None
    
    update_func(record)
    return record

def deduct_user_credits(db, user_id, amount=1):
    """
    Safely deduct user credits with proper locking to prevent conflicts.
    
    Args:
        db: SQLAlchemy session
        user_id: User ID
        amount: Amount to deduct (default 1)
    
    Returns:
        Success status and message
    """
    from database.models import User
    
    sql = text("""
        UPDATE users 
        SET credits = credits - :amount 
        WHERE id = :user_id AND credits >= :amount
        RETURNING credits
    """)
    
    result = db.execute(sql, {"amount": amount, "user_id": user_id}).first()
    
    if not result:
        return False, "Insufficient credits"
    
    return True, f"Credits updated. Remaining: {result[0]}"

def attach_to_conversation(db, user_id, conversation_id):
    """
    Safely attach a user to a conversation, handling potential conflicts.
    
    Args:
        db: SQLAlchemy session
        user_id: User ID
        conversation_id: Conversation ID
    """
    from database.models import UserConversation
    
    # Check if the association already exists
    sql = text("""
        INSERT INTO user_conversations (user_id, conversation_id)
        VALUES (:user_id, :conversation_id)
        ON CONFLICT (user_id, conversation_id) DO NOTHING
    """)
    
    db.execute(sql, {"user_id": user_id, "conversation_id": conversation_id})
