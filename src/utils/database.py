"""Database connection and session management."""
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from dotenv import load_dotenv
from src.config import settings
from src.models import Base
from src.models.user import User
from src.models.link import Link
from src.models.invite import Invite

load_dotenv()

# Create engine
engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False} if settings.database_url.startswith("sqlite") else {},
    echo=False  # Set to True for SQL query logging
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
