"""Tag model for normalized tag storage."""
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, UniqueConstraint, Index, Table
from sqlalchemy.orm import relationship
from src.models import Base


class Tag(Base):
    """Tag model for user's tag collection."""
    __tablename__ = "tags"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(50), nullable=False)
    count = Column(Integer, nullable=False, default=0)  # Count from journal imports
    created_at = Column(DateTime, default=datetime.now, nullable=False)

    # Relationships
    user = relationship("User", back_populates="tags")

    # Constraints
    __table_args__ = (
        UniqueConstraint('user_id', 'name', name='uix_user_tag_name'),
        Index('ix_tags_user_id', 'user_id'),
        Index('ix_tags_user_id_name', 'user_id', 'name'),
    )

    def __repr__(self):
        return f"<Tag(id={self.id}, user_id={self.user_id}, name='{self.name}', count={self.count})>"


# Association table for many-to-many relationship between links and tags
link_tags = Table(
    'link_tags',
    Base.metadata,
    Column('link_id', Integer, ForeignKey('links.id', ondelete='CASCADE'), primary_key=True),
    Column('tag_id', Integer, ForeignKey('tags.id', ondelete='CASCADE'), primary_key=True),
    Column('created_at', DateTime, default=datetime.now, nullable=False)
)
