#!/usr/bin/env python3
"""Migration script to convert JSON tag storage to normalized relational schema."""
import sys
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from datetime import datetime

# Add src to path
sys.path.insert(0, '/mnt/arkk/logkeep')

from src.config import settings
from src.models import Base
from src.models.user import User
from src.models.link import Link
from src.models.tag import Tag, link_tags
from src.models.invite import Invite  # Import to resolve relationship references
from src.utils.logging import logger


def migrate_tags():
    """Migrate from JSON tag storage to normalized schema."""
    
    logger.info("Starting tag migration...")
    
    # Create engine and session
    engine = create_engine(settings.database_url)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    
    try:
        # Step 1: Create new tables (tags and link_tags)
        logger.info("Creating new tables...")
        Base.metadata.create_all(bind=engine, tables=[
            Base.metadata.tables['tags'],
            Base.metadata.tables['link_tags']
        ])
        logger.info("✓ New tables created")
        
        # Step 2: Get old data from users table (JSON columns)
        logger.info("Reading existing user tag data...")
        result = db.execute(text("SELECT id, tags, tag_counts FROM users")).fetchall()
        
        user_tag_data = {}
        for row in result:
            user_id, tags_json, counts_json = row
            # Parse JSON - SQLite stores as strings
            import json
            try:
                tags = json.loads(tags_json) if isinstance(tags_json, str) else (tags_json or [])
                counts = json.loads(counts_json) if isinstance(counts_json, str) else (counts_json or {})
            except:
                tags = []
                counts = {}
            
            user_tag_data[user_id] = {
                'tags': tags,
                'counts': counts
            }
        
        logger.info(f"✓ Found {len(user_tag_data)} users with tag data")
        
        # Step 3: Migrate user tags to normalized Tag table
        logger.info("Migrating user tags...")
        tag_id_map = {}  # Map (user_id, tag_name) -> tag_id
        
        for user_id, data in user_tag_data.items():
            tags = data['tags']
            counts = data['counts']
            
            for tag_name in tags:
                # Create Tag record
                tag = Tag(
                    user_id=user_id,
                    name=tag_name,
                    count=counts.get(tag_name, 0),
                    created_at=datetime.now()
                )
                db.add(tag)
                db.flush()  # Get the ID
                
                tag_id_map[(user_id, tag_name)] = tag.id
                
            if tags:
                logger.info(f"  User {user_id}: migrated {len(tags)} tags")
        
        db.commit()
        logger.info(f"✓ Migrated {len(tag_id_map)} total tags")
        
        # Step 4: Get link tag data (selected_tags JSON column)
        logger.info("Reading existing link tag assignments...")
        result = db.execute(text("SELECT id, user_id, selected_tags FROM links")).fetchall()
        
        link_tag_data = []
        for row in result:
            link_id, user_id, selected_tags_json = row
            # Parse JSON
            import json
            try:
                selected_tags = json.loads(selected_tags_json) if isinstance(selected_tags_json, str) else (selected_tags_json or [])
            except:
                selected_tags = []
            
            if selected_tags:
                link_tag_data.append((link_id, user_id, selected_tags))
        
        logger.info(f"✓ Found {len(link_tag_data)} links with tags")
        
        # Step 5: Migrate link-tag associations to link_tags table
        logger.info("Migrating link-tag associations...")
        associations_created = 0
        
        for link_id, user_id, tag_names in link_tag_data:
            for tag_name in tag_names:
                tag_id = tag_id_map.get((user_id, tag_name))
                
                if tag_id is None:
                    # Tag doesn't exist in user's collection - create it
                    logger.warning(f"  Link {link_id} references non-existent tag '{tag_name}' - creating it")
                    tag = Tag(
                        user_id=user_id,
                        name=tag_name,
                        count=0,
                        created_at=datetime.now()
                    )
                    db.add(tag)
                    db.flush()
                    tag_id = tag.id
                    tag_id_map[(user_id, tag_name)] = tag_id
                
                # Create link-tag association
                db.execute(
                    link_tags.insert().values(
                        link_id=link_id,
                        tag_id=tag_id,
                        created_at=datetime.now()
                    )
                )
                associations_created += 1
        
        db.commit()
        logger.info(f"✓ Created {associations_created} link-tag associations")
        
        # Step 6: Drop old JSON columns from users table
        logger.info("Dropping old JSON columns from users table...")
        with engine.begin() as conn:
            # SQLite doesn't support DROP COLUMN, need to recreate table
            conn.execute(text("""
                CREATE TABLE users_new (
                    id INTEGER PRIMARY KEY,
                    username VARCHAR(255) NOT NULL UNIQUE,
                    hashed_password VARCHAR(255) NOT NULL,
                    encrypted_github_token TEXT NOT NULL,
                    repo_owner VARCHAR(255) NOT NULL,
                    repo_name VARCHAR(255) NOT NULL,
                    is_active BOOLEAN NOT NULL DEFAULT 1,
                    created_at DATETIME NOT NULL
                )
            """))
            
            conn.execute(text("""
                INSERT INTO users_new (id, username, hashed_password, encrypted_github_token, 
                                       repo_owner, repo_name, is_active, created_at)
                SELECT id, username, hashed_password, encrypted_github_token,
                       repo_owner, repo_name, is_active, created_at
                FROM users
            """))
            
            conn.execute(text("DROP TABLE users"))
            conn.execute(text("ALTER TABLE users_new RENAME TO users"))
            
            # Recreate indexes
            conn.execute(text("CREATE UNIQUE INDEX ix_users_username ON users (username)"))
            conn.execute(text("CREATE INDEX ix_users_id ON users (id)"))
        
        logger.info("✓ Dropped old JSON columns from users table")
        
        # Step 7: Drop selected_tags column from links table
        logger.info("Dropping selected_tags column from links table...")
        with engine.begin() as conn:
            # SQLite doesn't support DROP COLUMN, need to recreate table
            conn.execute(text("""
                CREATE TABLE links_new (
                    id INTEGER PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    url TEXT NOT NULL,
                    title VARCHAR(500),
                    score FLOAT,
                    status VARCHAR(20) NOT NULL,
                    retry_count INTEGER NOT NULL DEFAULT 0,
                    error_message TEXT,
                    submitted_at DATETIME NOT NULL,
                    processed_at DATETIME,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                    CONSTRAINT uix_user_url UNIQUE (user_id, url)
                )
            """))
            
            conn.execute(text("""
                INSERT INTO links_new (id, user_id, url, title, score, status, retry_count, 
                                       error_message, submitted_at, processed_at)
                SELECT id, user_id, url, title, score, status, retry_count,
                       error_message, submitted_at, processed_at
                FROM links
            """))
            
            conn.execute(text("DROP TABLE links"))
            conn.execute(text("ALTER TABLE links_new RENAME TO links"))
            
            # Recreate indexes
            conn.execute(text("CREATE INDEX ix_links_user_id ON links (user_id)"))
            conn.execute(text("CREATE INDEX ix_links_status ON links (status)"))
            conn.execute(text("CREATE INDEX ix_links_user_id_status ON links (user_id, status)"))
            conn.execute(text("CREATE INDEX ix_links_user_id_submitted ON links (user_id, submitted_at)"))
            conn.execute(text("CREATE INDEX ix_links_id ON links (id)"))
        
        logger.info("✓ Dropped selected_tags column from links table")
        
        logger.info("=" * 60)
        logger.info("Migration completed successfully!")
        logger.info(f"  - Migrated {len(tag_id_map)} tags")
        logger.info(f"  - Created {associations_created} link-tag associations")
        logger.info(f"  - Removed old JSON columns from users and links tables")
        logger.info("=" * 60)
        
    except Exception as e:
        logger.error(f"Migration failed: {str(e)}")
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    print("LogKeep Tag Schema Migration")
    print("=" * 60)
    print("This will migrate from JSON tag storage to normalized schema.")
    print("Make sure you have backed up your database!")
    print("=" * 60)
    
    response = input("Continue with migration? (yes/no): ")
    if response.lower() == 'yes':
        migrate_tags()
    else:
        print("Migration cancelled.")
