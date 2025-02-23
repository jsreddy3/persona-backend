"""add credits and payments

Revision ID: add_credits_and_payments
Revises: previous_revision
Create Date: 2025-02-22 23:00:22.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'add_credits_and_payments'
down_revision = None  # Update this to your last migration
branch_labels = None
depends_on = None

def upgrade():
    # Add credits column to users table
    op.add_column('users', sa.Column('credits', sa.Integer(), nullable=False, server_default='0'))
    
    # Create payments table
    op.create_table('payments',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('reference', sa.String(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('amount', sa.Integer(), nullable=False),
        sa.Column('transaction_id', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_payments_reference'), 'payments', ['reference'], unique=True)

def downgrade():
    op.drop_index(op.f('ix_payments_reference'), table_name='payments')
    op.drop_table('payments')
    op.drop_column('users', 'credits')
