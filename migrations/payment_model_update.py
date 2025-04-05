"""
Migration script to update the Payment model with new fields for token support

Usage: python migrations/payment_model_update.py
"""

import sys
import os
import alembic.config
from alembic import command
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, Column, String, Integer, MetaData, Table

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.database import DATABASE_URL

def upgrade_payment_table():
    """Add new columns to payment table for token support"""
    
    # Connect to the database
    engine = create_engine(DATABASE_URL)
    connection = engine.connect()
    
    try:
        # Create migration context
        context = MigrationContext.configure(connection)
        op = Operations(context)
        
        # Check if the table has the new columns
        metadata = MetaData()
        payment_table = Table('payments', metadata, autoload_with=engine)
        existing_columns = {c.name for c in payment_table.columns}
        
        # Rename 'amount' to 'credits_amount' if it exists
        if 'amount' in existing_columns and 'credits_amount' not in existing_columns:
            op.alter_column('payments', 'amount', new_column_name='credits_amount')
            print("Renamed 'amount' column to 'credits_amount'")
        elif 'amount' in existing_columns and 'credits_amount' in existing_columns:
            # Handle case where both exist during migration
            print("Both 'amount' and 'credits_amount' exist. Please manually migrate data.")
        
        # Add new columns if they don't exist
        columns_to_add = {
            'token_type': Column(String, nullable=True),
            'token_amount': Column(String, nullable=True),
            'token_decimal_places': Column(Integer, nullable=True),
            'transaction_hash': Column(String, nullable=True),
            'chain': Column(String, server_default="worldchain"),
            'sender_address': Column(String, nullable=True),
            'recipient_address': Column(String, nullable=True),
            'updated_at': Column(String, nullable=True),
        }
        
        for col_name, col in columns_to_add.items():
            if col_name not in existing_columns:
                op.add_column('payments', col)
                print(f"Added column '{col_name}' to payments table")
        
        print("Payment table migration completed successfully")
        
    finally:
        connection.close()
        
if __name__ == "__main__":
    upgrade_payment_table()
