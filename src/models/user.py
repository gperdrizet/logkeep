"""User model."""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text
from sqlalchemy.orm import relationship
from src.models import Base


class User(Base):
    """User model with optional GitHub token storage."""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(255), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    github_enabled = Column(Boolean, default=False, nullable=False)
    encrypted_github_token = Column(Text, nullable=True)
    repo_owner = Column(String(255), nullable=True)
    repo_name = Column(String(255), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.now, nullable=False)

    # Relationships
    tags = relationship("Tag", back_populates="user", cascade="all, delete-orphan", lazy="selectin")
    links = relationship("Link", back_populates="user", cascade="all, delete-orphan")
    invites_created = relationship("Invite", foreign_keys="Invite.created_by_user_id", back_populates="creator")
    invite_used = relationship("Invite", foreign_keys="Invite.used_by_user_id", back_populates="used_by_user", uselist=False)

    def __repr__(self):
        if self.github_enabled:
            return f"<User(id={self.id}, username='{self.username}', repo='{self.repo_owner}/{self.repo_name}')>"
        return f"<User(id={self.id}, username='{self.username}')>"
