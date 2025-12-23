"""Add summary_last_retry_at field to links table.

This migration adds a timestamp field to track when summarization was last
attempted for a link. This enables deferred retry logic for LLM failures.

Revision: add_summary_last_retry_at
Date: 2025-12-23
"""

from alembic import op
import sqlalchemy as sa


def upgrade():
    """Add summary_last_retry_at column."""
    op.add_column(
        'links',
        sa.Column('summary_last_retry_at', sa.DateTime(), nullable=True)
    )


def downgrade():
    """Remove summary_last_retry_at column."""
    op.drop_column('links', 'summary_last_retry_at')
