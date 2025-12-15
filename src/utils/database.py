"""Database connection and session management."""
import os
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from dotenv import load_dotenv
from src.config import settings
from src.models import Base
from src.models.user import User
from src.models.link import Link
from src.models.invite import Invite
from src.models.tag import Tag, link_tags

load_dotenv()


def get_database_url() -> str:
    """
    Get database URL from environment or Docker secrets.
    
    Returns:
        Database connection string
    """
    # Check if running in Docker with secrets
    secrets_dir = Path("/run/secrets")
    if secrets_dir.exists():
        db_file = secrets_dir / "postgres_db"
        user_file = secrets_dir / "postgres_user"
        password_file = secrets_dir / "postgres_password"
        
        if db_file.exists() and user_file.exists() and password_file.exists():
            db_name = db_file.read_text().strip()
            db_user = user_file.read_text().strip()
            db_password = password_file.read_text().strip()
            
            # Use postgres service name from docker-compose
            db_host = os.getenv("POSTGRES_HOST", "postgres")
            db_port = os.getenv("POSTGRES_PORT", "5432")
            
            return f"postgresql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"
    
    # Fall back to DATABASE_URL from environment
    return settings.database_url


# Get database URL
database_url = get_database_url()

# Create engine with appropriate settings
if database_url.startswith("postgresql"):
    engine = create_engine(
        database_url,
        pool_size=10,
        max_overflow=20,
        pool_pre_ping=True,  # Verify connections before using
        echo=False  # Set to True for SQL query logging
    )
else:
    # SQLite configuration
    engine = create_engine(
        database_url,
        connect_args={"check_same_thread": False},
        echo=False
    )

# Create session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db():
    """Initialize database tables."""
    # Ensure data directory exists for SQLite
    if settings.database_url.startswith("sqlite"):
        db_path = settings.database_url.replace("sqlite:///", "")
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
    
    # Create all tables (checkfirst=True is default, but making it explicit)
    Base.metadata.create_all(bind=engine, checkfirst=True)
    print("Database initialized successfully")


def get_db() -> Session:
    """
    Get database session.
    
    Yields:
        SQLAlchemy Session object
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


if __name__ == "__main__":
    """Run database initialization when called as a module."""
    init_db()