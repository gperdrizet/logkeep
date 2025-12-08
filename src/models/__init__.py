"""Database models for LogKeep."""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, ForeignKey, JSON, Enum as SQLEnum, UniqueConstraint, Index
from sqlalchemy.orm import declarative_base, relationship
import enum

Base = declarative_base()


class LinkStatus(enum.Enum):
    """Status of a link submission."""
    PENDING = "pending"
    PROCESSING = "processing"
    NEEDS_TITLE = "needs_title"
    COMPLETED = "completed"
    FAILED = "failed"
