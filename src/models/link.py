"""Link submission model."""
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey, JSON, UniqueConstraint, Index
from sqlalchemy.orm import relationship
from sqlalchemy.types import Enum as SQLEnum
from src.models import Base, LinkStatus


class Link(Base):
    """Link submission tracking model."""
    __tablename__ = "links"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    url = Column(Text, nullable=False)
    title = Column(String(500), nullable=True)  # Nullable until extracted/provided
    selected_tags = Column(JSON, nullable=False, default=list)  # Array of selected tag strings
    status = Column(SQLEnum(LinkStatus), nullable=False, default=LinkStatus.PENDING, index=True)
    retry_count = Column(Integer, nullable=False, default=0)
    error_message = Column(Text, nullable=True)
    submitted_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    processed_at = Column(DateTime, nullable=True)

    # Relationships
    user = relationship("User", back_populates="links")

    # Constraints
    __table_args__ = (
        UniqueConstraint('user_id', 'url', name='uix_user_url'),  # Prevent duplicate URLs per user
        Index('ix_links_status', 'status'),  # Index for status queries
        Index('ix_links_user_id_status', 'user_id', 'status'),  # Composite index for user's link queries
    )

    def __repr__(self):
        return f"<Link(id={self.id}, user_id={self.user_id}, url='{self.url[:50]}...', status={self.status.value})>"
