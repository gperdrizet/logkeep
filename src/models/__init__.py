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


# Import models to ensure they're registered with Base
from src.models.tag import Tag, link_tags  # noqa: E402, F401
from src.models.user import User  # noqa: E402, F401
from src.models.link import Link  # noqa: E402, F401
from src.models.invite import Invite  # noqa: E402, F401
from src.models.invite_delivery import InviteDelivery  # noqa: E402, F401
