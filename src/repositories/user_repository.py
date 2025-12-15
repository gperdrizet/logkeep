"""User repository for database operations."""
from typing import Optional
from sqlalchemy.orm import Session
from src.models.user import User


class UserRepository:
    """Repository for User database operations."""
    
    def __init__(self, db: Session):
        """Initialize repository with database session."""
        self.db = db
    
    def create(self, user: User) -> User:
        """
        Create a new user.
        
        Args:
            user: User object to create
            
        Returns:
            Created user with ID
        """
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        return user
    
    def get_by_id(self, user_id: int) -> Optional[User]:
        """
        Get user by ID.
        
        Args:
            user_id: User ID
            
        Returns:
            User object or None if not found
        """
        return self.db.query(User).filter(User.id == user_id).first()
    
    def get_by_username(self, username: str) -> Optional[User]:
        """
        Get user by username.
        
        Args:
            username: Username
            
        Returns:
            User object or None if not found
        """
        return self.db.query(User).filter(User.username == username).first()
    
    def exists_by_username(self, username: str) -> bool:
        """
        Check if a user exists by username.
        
        Args:
            username: Username
            
        Returns:
            True if user exists, False otherwise
        """
        return self.db.query(User).filter(User.username == username).first() is not None
    
    def update(self, user: User) -> User:
        """
        Update a user.
        
        Args:
            user: User object to update
            
        Returns:
            Updated user
        """
        self.db.commit()
        self.db.refresh(user)
        return user
