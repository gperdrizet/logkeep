#!/usr/bin/env python3
"""
Migration script to transfer data from SQLite to PostgreSQL.

This script:
1. Connects to the SQLite database
2. Exports all data from users, invites, tags, links, and link_tags tables
3. Connects to PostgreSQL
4. Creates all tables using SQLAlchemy
5. Imports all data preserving relationships and IDs
6. Verifies the migration was successful
"""
import os
import sys
from pathlib import Path
from datetime import datetime

# Add src directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from src.models import Base
from src.models.user import User
from src.models.invite import Invite
from src.models.link import Link
from src.models.tag import Tag, link_tags


def get_postgres_url() -> str:
    """Get PostgreSQL connection URL from Docker secrets."""
    secrets_dir = Path("/run/secrets")
    
    if not secrets_dir.exists():
        # For local testing outside Docker
        db_name = os.getenv("POSTGRES_DB", "logkeep")
        db_user = os.getenv("POSTGRES_USER", "logkeep_user")
        db_password = os.getenv("POSTGRES_PASSWORD", "")
        db_host = os.getenv("POSTGRES_HOST", "localhost")
        db_port = os.getenv("POSTGRES_PORT", "5432")
    else:
        db_file = secrets_dir / "postgres_db"
        user_file = secrets_dir / "postgres_user"
        password_file = secrets_dir / "postgres_password"
        
        if not all([db_file.exists(), user_file.exists(), password_file.exists()]):
            raise FileNotFoundError("PostgreSQL secrets not found")
        
        db_name = db_file.read_text().strip()
        db_user = user_file.read_text().strip()
        db_password = password_file.read_text().strip()
        db_host = os.getenv("POSTGRES_HOST", "postgres")
        db_port = os.getenv("POSTGRES_PORT", "5432")
    
    return f"postgresql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"


def migrate():
    """Perform the migration from SQLite to PostgreSQL."""
    # SQLite connection
    sqlite_path = Path("/app/data/logkeep.db")
    if not sqlite_path.exists():
        # Try local path
        sqlite_path = Path(__file__).parent.parent / "data" / "logkeep.db"
    
    if not sqlite_path.exists():
        print(f"Error: SQLite database not found at {sqlite_path}")
        sys.exit(1)
    
    print(f"Connecting to SQLite database: {sqlite_path}")
    sqlite_engine = create_engine(f"sqlite:///{sqlite_path}")
    SQLiteSession = sessionmaker(bind=sqlite_engine)
    
    # PostgreSQL connection
    postgres_url = get_postgres_url()
    print(f"Connecting to PostgreSQL: {postgres_url.split('@')[1]}")  # Hide password
    postgres_engine = create_engine(postgres_url)
    PostgresSession = sessionmaker(bind=postgres_engine)
    
    # Create all tables in PostgreSQL
    print("\nCreating tables in PostgreSQL...")
    Base.metadata.create_all(postgres_engine)
    print("Tables created successfully")
    
    # Start migration
    print("\nStarting data migration...")
    sqlite_session = SQLiteSession()
    postgres_session = PostgresSession()
    
    try:
        # Migrate Users
        print("\n1. Migrating users...")
        users = sqlite_session.query(User).all()
        print(f"   Found {len(users)} users")
        
        for user in users:
            new_user = User(
                id=user.id,
                username=user.username,
                hashed_password=user.hashed_password,
                github_enabled=user.github_enabled if hasattr(user, 'github_enabled') else False,
                encrypted_github_token=user.encrypted_github_token,
                repo_owner=user.repo_owner,
                repo_name=user.repo_name,
                is_active=user.is_active if hasattr(user, 'is_active') else True,
                created_at=user.created_at
            )
            postgres_session.add(new_user)
        
        postgres_session.flush()
        print(f"   Migrated {len(users)} users")
        
        # Migrate Invites
        print("\n2. Migrating invites...")
        invites = sqlite_session.query(Invite).all()
        print(f"   Found {len(invites)} invites")
        
        for invite in invites:
            new_invite = Invite(
                id=invite.id,
                code=invite.code,
                created_by_user_id=invite.created_by_user_id if hasattr(invite, 'created_by_user_id') else (invite.created_by if hasattr(invite, 'created_by') else None),
                used_by_user_id=invite.used_by_user_id if hasattr(invite, 'used_by_user_id') else (invite.used_by if hasattr(invite, 'used_by') else None),
                created_at=invite.created_at,
                used_at=invite.used_at
            )
            postgres_session.add(new_invite)
        
        postgres_session.flush()
        print(f"   Migrated {len(invites)} invites")
        
        # Migrate Tags
        print("\n3. Migrating tags...")
        tags = sqlite_session.query(Tag).all()
        print(f"   Found {len(tags)} tags")
        
        for tag in tags:
            new_tag = Tag(
                id=tag.id,
                name=tag.name,
                user_id=tag.user_id,
                created_at=tag.created_at
            )
            postgres_session.add(new_tag)
        
        postgres_session.flush()
        print(f"   Migrated {len(tags)} tags")
        
        # Migrate Links
        print("\n4. Migrating links...")
        links = sqlite_session.query(Link).all()
        print(f"   Found {len(links)} links")
        
        for link in links:
            # Handle different schema versions
            from src.models import LinkStatus
            
            # Determine status from old 'processed' field if present
            if hasattr(link, 'status'):
                status = link.status
            elif hasattr(link, 'processed'):
                status = LinkStatus.COMPLETED if link.processed else LinkStatus.PENDING
            else:
                status = LinkStatus.PENDING
            
            # Handle different timestamp field names
            submitted_at = link.submitted_at if hasattr(link, 'submitted_at') else (link.created_at if hasattr(link, 'created_at') else datetime.now())
            
            new_link = Link(
                id=link.id,
                user_id=link.user_id,
                url=link.url,
                title=link.title,
                summary=link.summary if hasattr(link, 'summary') else None,
                score=link.score if hasattr(link, 'score') else None,
                status=status,
                retry_count=link.retry_count if hasattr(link, 'retry_count') else 0,
                error_message=link.error_message if hasattr(link, 'error_message') else None,
                submitted_at=submitted_at,
                processed_at=link.processed_at if hasattr(link, 'processed_at') else None,
                summarized_at=link.summarized_at if hasattr(link, 'summarized_at') else None,
                llm_model=link.llm_model if hasattr(link, 'llm_model') else None,
                summary_error=link.summary_error if hasattr(link, 'summary_error') else None,
                summary_retry_count=link.summary_retry_count if hasattr(link, 'summary_retry_count') else 0
            )
            postgres_session.add(new_link)
        
        postgres_session.flush()
        print(f"   Migrated {len(links)} links")
        
        # Migrate Link-Tag relationships
        print("\n5. Migrating link-tag relationships...")
        result = sqlite_session.execute(text("SELECT link_id, tag_id, created_at FROM link_tags"))
        link_tag_rows = result.fetchall()
        print(f"   Found {len(link_tag_rows)} relationships")
        
        for row in link_tag_rows:
            # Handle both old (no created_at) and new (with created_at) schemas
            created_at = row[2] if len(row) > 2 and row[2] is not None else datetime.now()
            postgres_session.execute(
                text("INSERT INTO link_tags (link_id, tag_id, created_at) VALUES (:link_id, :tag_id, :created_at)"),
                {"link_id": row[0], "tag_id": row[1], "created_at": created_at}
            )
        
        postgres_session.flush()
        print(f"   Migrated {len(link_tag_rows)} link-tag relationships")
        
        # Commit all changes
        print("\nCommitting changes to PostgreSQL...")
        postgres_session.commit()
        print("Commit successful")
        
        # Verify migration
        print("\n" + "=" * 60)
        print("VERIFICATION")
        print("=" * 60)
        
        sqlite_counts = {
            "users": sqlite_session.query(User).count(),
            "invites": sqlite_session.query(Invite).count(),
            "tags": sqlite_session.query(Tag).count(),
            "links": sqlite_session.query(Link).count(),
            "link_tags": len(link_tag_rows)
        }
        
        postgres_counts = {
            "users": postgres_session.query(User).count(),
            "invites": postgres_session.query(Invite).count(),
            "tags": postgres_session.query(Tag).count(),
            "links": postgres_session.query(Link).count(),
            "link_tags": postgres_session.execute(text("SELECT COUNT(*) FROM link_tags")).scalar()
        }
        
        print("\nRecord counts:")
        all_match = True
        for table in sqlite_counts:
            sqlite_count = sqlite_counts[table]
            postgres_count = postgres_counts[table]
            match = "✓" if sqlite_count == postgres_count else "✗"
            print(f"  {match} {table:15} SQLite: {sqlite_count:5d}  PostgreSQL: {postgres_count:5d}")
            if sqlite_count != postgres_count:
                all_match = False
        
        if all_match:
            print("\n" + "=" * 60)
            print("✓ MIGRATION SUCCESSFUL - All records migrated correctly")
            print("=" * 60)
            return 0
        else:
            print("\n" + "=" * 60)
            print("✗ MIGRATION INCOMPLETE - Record counts do not match")
            print("=" * 60)
            return 1
            
    except Exception as e:
        print(f"\n✗ Error during migration: {e}")
        postgres_session.rollback()
        import traceback
        traceback.print_exc()
        return 1
    finally:
        sqlite_session.close()
        postgres_session.close()


if __name__ == "__main__":
    print("=" * 60)
    print("SQLite to PostgreSQL Migration")
    print("=" * 60)
    print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    exit_code = migrate()
    
    print()
    print(f"Finished at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    
    sys.exit(exit_code)
