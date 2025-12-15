"""Link submission model."""
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey, UniqueConstraint, Index, Float
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
    score = Column(Float, nullable=True)  # User rating 0.0-1.0
    status = Column(SQLEnum(LinkStatus), nullable=False, default=LinkStatus.PENDING)
    retry_count = Column(Integer, nullable=False, default=0)
    error_message = Column(Text, nullable=True)
    submitted_at = Column(DateTime, default=datetime.now, nullable=False)
    processed_at = Column(DateTime, nullable=True)
    
    # LLM Summarization fields
    summary = Column(Text, nullable=True)  # Generated article summary
    summarized_at = Column(DateTime, nullable=True)  # When summary was generated
    llm_model = Column(String(100), nullable=True)  # Model used for summarization
    summary_error = Column(String(500), nullable=True)  # User-friendly error message
    summary_retry_count = Column(Integer, nullable=False, default=0)  # Summarization retry attempts

    # Relationships
    user = relationship("User", back_populates="links")
    tags = relationship("Tag", secondary="link_tags", backref="links", lazy="selectin")

    # Constraints
    __table_args__ = (
        UniqueConstraint('user_id', 'url', name='uix_user_url'),  # Prevent duplicate URLs per user
        Index('ix_links_status', 'status'),  # Index for status queries
        Index('ix_links_user_id_status', 'user_id', 'status'),  # Composite index for user's link queries
        Index('ix_links_user_id_submitted', 'user_id', 'submitted_at'),  # Optimize dashboard ordering
    )

    def __repr__(self):
        return f"<Link(id={self.id}, user_id={self.user_id}, url='{self.url[:50]}...', status={self.status.value})>"
