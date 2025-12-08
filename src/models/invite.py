"""Invite code model."""
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from src.models import Base
import uuid


class Invite(Base):
    """Invite code model for user registration."""
    __tablename__ = "invites"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(36), unique=True, nullable=False, index=True, default=lambda: str(uuid.uuid4()))
    created_by_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    used_by_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, unique=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    used_at = Column(DateTime, nullable=True)

    # Relationships
    creator = relationship("User", foreign_keys=[created_by_user_id], back_populates="invites_created")
    used_by_user = relationship("User", foreign_keys=[used_by_user_id], back_populates="invite_used")

    @property
    def is_used(self):
        """Check if invite code has been used."""
        return self.used_by_user_id is not None

    def __repr__(self):
        status = "used" if self.is_used else "unused"
        return f"<Invite(code='{self.code}', status='{status}')>"
