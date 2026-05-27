"""Invite delivery metadata model."""
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from src.models import Base


class InviteDelivery(Base):
    """Tracks where an invite code was sent."""
    __tablename__ = "invite_deliveries"

    id = Column(Integer, primary_key=True, index=True)
    invite_id = Column(Integer, ForeignKey("invites.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    recipient_email = Column(String(320), nullable=False)
    sent_at = Column(DateTime, default=datetime.now, nullable=False)

    invite = relationship("Invite", back_populates="delivery")

    def __repr__(self):
        return f"<InviteDelivery(invite_id={self.invite_id}, recipient='{self.recipient_email}')>"
