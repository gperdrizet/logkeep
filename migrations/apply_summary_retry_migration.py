#!/usr/bin/env python3
"""Apply summary_last_retry_at migration directly using SQLAlchemy."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from sqlalchemy import text
from utils.database import engine


def main():
    """Add summary_last_retry_at column to links table."""
    
    with engine.connect() as conn:
        # Check if column already exists
        result = conn.execute(text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name='links' 
            AND column_name='summary_last_retry_at'
        """))
        
        if result.fetchone():
            print("Column 'summary_last_retry_at' already exists. Skipping migration.")
            return
        
        # Add the column
        print("Adding column 'summary_last_retry_at' to links table...")
        conn.execute(text("""
            ALTER TABLE links 
            ADD COLUMN summary_last_retry_at TIMESTAMP NULL
        """))
        conn.commit()
        print("✓ Migration complete!")


if __name__ == "__main__":
    main()
