"""Add summary fields to links table.

This migration adds LLM summarization support to the links table.

Fields added:
- summary: Text field for the generated article summary
- summarized_at: DateTime field for when the summary was generated
- llm_model: String field for the model name used
- summary_error: String field for user-friendly error messages
- summary_retry_count: Integer field for tracking retry attempts

Index added:
- idx_links_summary_status: Composite index on (status, summary) for efficient queries

To apply this migration:
    python migrations/add_summary_fields_to_links.py

To rollback this migration:
    python migrations/add_summary_fields_to_links.py --rollback
"""
import sys
import os
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import create_engine, text
from src.config import settings
from src.utils.logging import logger


def upgrade(engine):
    """Apply the migration."""
    logger.info("Starting migration: add_summary_fields_to_links")
    
    with engine.connect() as conn:
        # Add new columns
        logger.info("Adding summary column...")
        conn.execute(text("ALTER TABLE links ADD COLUMN summary TEXT"))
        
        logger.info("Adding summarized_at column...")
        conn.execute(text("ALTER TABLE links ADD COLUMN summarized_at DATETIME"))
        
        logger.info("Adding llm_model column...")
        conn.execute(text("ALTER TABLE links ADD COLUMN llm_model VARCHAR(100)"))
        
        logger.info("Adding summary_error column...")
        conn.execute(text("ALTER TABLE links ADD COLUMN summary_error VARCHAR(500)"))
        
        logger.info("Adding summary_retry_count column...")
        conn.execute(text("ALTER TABLE links ADD COLUMN summary_retry_count INTEGER NOT NULL DEFAULT 0"))
        
        # Create composite index for efficient queries
        logger.info("Creating composite index idx_links_summary_status...")
        conn.execute(text("CREATE INDEX idx_links_summary_status ON links(status, summary)"))
        
        conn.commit()
    
    logger.info("Migration completed successfully")


def downgrade(engine):
    """Rollback the migration."""
    logger.info("Rolling back migration: add_summary_fields_to_links")
    
    with engine.connect() as conn:
        # Drop index first
        logger.info("Dropping index idx_links_summary_status...")
        conn.execute(text("DROP INDEX IF EXISTS idx_links_summary_status"))
        
        # Drop columns (SQLite doesn't support DROP COLUMN directly in older versions,
        # but we'll use a workaround if needed)
        try:
            logger.info("Dropping summary_retry_count column...")
            conn.execute(text("ALTER TABLE links DROP COLUMN summary_retry_count"))
            
            logger.info("Dropping summary_error column...")
            conn.execute(text("ALTER TABLE links DROP COLUMN summary_error"))
            
            logger.info("Dropping llm_model column...")
            conn.execute(text("ALTER TABLE links DROP COLUMN llm_model"))
            
            logger.info("Dropping summarized_at column...")
            conn.execute(text("ALTER TABLE links DROP COLUMN summarized_at"))
            
            logger.info("Dropping summary column...")
            conn.execute(text("ALTER TABLE links DROP COLUMN summary"))
        except Exception as e:
            logger.error(f"Error dropping columns (SQLite may not support DROP COLUMN): {e}")
            logger.info("For SQLite, you may need to manually recreate the table without these columns")
        
        conn.commit()
    
    logger.info("Rollback completed")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Add summary fields to links table")
    parser.add_argument("--rollback", action="store_true", help="Rollback the migration")
    args = parser.parse_args()
    
    # Create engine
    engine = create_engine(settings.database_url)
    
    try:
        if args.rollback:
            downgrade(engine)
        else:
            upgrade(engine)
        print("Migration operation completed successfully")
    except Exception as e:
        logger.error(f"Migration failed: {e}", exc_info=True)
        print(f"ERROR: Migration failed - {e}")
        sys.exit(1)
