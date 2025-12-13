"""Invite repository for database operations."""
from typing import Optional
from sqlalchemy.orm import Session
from src.models.invite import Invite


class InviteRepository:
    """Repository for Invite database operations."""
    
    def __init__(self, db: Session):
        """Initialize repository with database session."""
        self.db = db
    
    def create(self, invite: Invite) -> Invite:
        """
        Create a new invite.
        
        Args:
            invite: Invite object to create
            
        Returns:
            Created invite with ID
        """
        self.db.add(invite)
        self.db.commit()
        self.db.refresh(invite)
        return invite
    
    def get_by_code(self, code: str) -> Optional[Invite]:
        """
        Get invite by code.
        
        Args:
            code: Invite code
            
        Returns:
            Invite object or None if not found
        """
        return self.db.query(Invite).filter(Invite.code == code).first()
    
    def mark_as_used(self, invite: Invite, used_by: int) -> Invite:
        """
        Mark an invite as used.
        
        Args:
            invite: Invite object to mark as used
            used_by: User ID who used the invite
            
        Returns:
            Updated invite
        """
        from datetime import datetime
        invite.used_by_user_id = used_by
        invite.used_at = datetime.now()
        self.db.commit()
        self.db.refresh(invite)
        return invite
