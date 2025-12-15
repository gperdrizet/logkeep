"""Tag repository for database operations."""
from typing import List, Optional
from sqlalchemy.orm import Session
from src.models.tag import Tag
from src.models.link import Link


class TagRepository:
    """Repository for Tag database operations."""
    
    def __init__(self, db: Session):
        """Initialize repository with database session."""
        self.db = db
    
    def create(self, tag: Tag) -> Tag:
        """
        Create a new tag.
        
        Args:
            tag: Tag object to create
            
        Returns:
            Created tag with ID
        """
        self.db.add(tag)
        self.db.commit()
        self.db.refresh(tag)
        return tag
    
    def get_by_id(self, tag_id: int) -> Optional[Tag]:
        """
        Get tag by ID.
        
        Args:
            tag_id: Tag ID
            
        Returns:
            Tag object or None if not found
        """
        return self.db.query(Tag).filter(Tag.id == tag_id).first()
    
    def get_by_name(self, user_id: int, name: str) -> Optional[Tag]:
        """
        Get tag by user ID and name.
        
        Args:
            user_id: User ID
            name: Tag name
            
        Returns:
            Tag object or None if not found
        """
        return self.db.query(Tag).filter(
            Tag.user_id == user_id,
            Tag.name == name
        ).first()
    
    def get_user_tags(self, user_id: int) -> List[Tag]:
        """
        Get all tags for a user.
        
        Args:
            user_id: User ID
            
        Returns:
            List of tags ordered by name
        """
        return self.db.query(Tag).filter(
            Tag.user_id == user_id
        ).order_by(Tag.name).all()
    
    def search_user_tags(self, user_id: int, query: str, limit: int = 50) -> List[Tag]:
        """
        Search user's tags by name.
        
        Args:
            user_id: User ID
            query: Search query
            limit: Maximum results to return
            
        Returns:
            List of matching tags
        """
        return self.db.query(Tag).filter(
            Tag.user_id == user_id,
            Tag.name.like(f"%{query}%")
        ).order_by(Tag.name).limit(limit).all()
    
    def update(self, tag: Tag) -> Tag:
        """
        Update a tag.
        
        Args:
            tag: Tag object to update
            
        Returns:
            Updated tag
        """
        self.db.commit()
        self.db.refresh(tag)
        return tag
    
    def delete(self, tag: Tag):
        """
        Delete a tag.
        
        Args:
            tag: Tag object to delete
        """
        self.db.delete(tag)
        self.db.commit()
    
    def exists(self, user_id: int, name: str) -> bool:
        """
        Check if a tag exists for a user.
        
        Args:
            user_id: User ID
            name: Tag name
            
        Returns:
            True if tag exists, False otherwise
        """
        return self.db.query(Tag).filter(
            Tag.user_id == user_id,
            Tag.name == name
        ).first() is not None
    
    def count_user_tags(self, user_id: int) -> int:
        """
        Count number of tags for a user.
        
        Args:
            user_id: User ID
            
        Returns:
            Number of tags
        """
        return self.db.query(Tag).filter(Tag.user_id == user_id).count()
    
    def get_or_create(self, user_id: int, name: str) -> Tag:
        """
        Get existing tag or create new one.
        
        Args:
            user_id: User ID
            name: Tag name
            
        Returns:
            Tag object
        """
        tag = self.get_by_name(user_id, name)
        if tag:
            return tag
        
        tag = Tag(user_id=user_id, name=name, count=0)
        return self.create(tag)
