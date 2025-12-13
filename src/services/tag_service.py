"""Tag service for business logic."""
from typing import List, Set
from sqlalchemy.orm import Session

from src.models.user import User
from src.repositories.user_repository import UserRepository
from src.exceptions import ValidationError, NotFoundError
from src.config import settings


class TagService:
    """Service for tag business logic."""
    
    def __init__(self, db: Session):
        """Initialize service with database session."""
        self.user_repo = UserRepository(db)
    
    def add_tag(self, user_id: int, tag: str) -> List[str]:
        """
        Add a tag to user's tag collection.
        
        Args:
            user_id: User ID
            tag: Tag to add
            
        Returns:
            Updated list of user tags
            
        Raises:
            NotFoundError: If user not found
            ValidationError: If tag invalid or limit exceeded
        """
        user = self.user_repo.get_by_id(user_id)
        if not user:
            raise NotFoundError(f"User not found: {user_id}")
        
        # Validate tag
        tag = tag.strip().lstrip('#')
        if not tag:
            raise ValidationError("Tag cannot be empty")
        
        if len(tag) > 50:
            raise ValidationError("Tag must be less than 50 characters")
        
        # Get existing tags
        user_tags = user.tags or []
        
        # Check if tag already exists
        if tag in user_tags:
            return user_tags
        
        # Check tag limit
        if len(user_tags) >= settings.max_tags_per_user:
            raise ValidationError(
                f"Maximum {settings.max_tags_per_user} tags allowed per user"
            )
        
        # Add tag
        user_tags.append(tag)
        user.tags = user_tags
        
        self.user_repo.update(user)
        return user_tags
    
    def delete_tag(self, user_id: int, tag: str) -> List[str]:
        """
        Delete a tag from user's tag collection.
        
        Args:
            user_id: User ID
            tag: Tag to delete
            
        Returns:
            Updated list of user tags
            
        Raises:
            NotFoundError: If user not found
            ValidationError: If tag not found
        """
        user = self.user_repo.get_by_id(user_id)
        if not user:
            raise NotFoundError(f"User not found: {user_id}")
        
        # Get existing tags
        user_tags = user.tags or []
        
        # Check if tag exists
        if tag not in user_tags:
            raise ValidationError(f"Tag not found: {tag}")
        
        # Remove tag
        user_tags.remove(tag)
        user.tags = user_tags
        
        self.user_repo.update(user)
        return user_tags
    
    def get_user_tags(self, user_id: int) -> List[str]:
        """
        Get user's tag collection.
        
        Args:
            user_id: User ID
            
        Returns:
            List of user tags
            
        Raises:
            NotFoundError: If user not found
        """
        user = self.user_repo.get_by_id(user_id)
        if not user:
            raise NotFoundError(f"User not found: {user_id}")
        
        return user.tags or []
    
    def validate_tags(self, tags: List[str], user_tags: List[str]) -> List[str]:
        """
        Validate and normalize tags.
        
        Args:
            tags: Tags to validate
            user_tags: User's tag collection
            
        Returns:
            Validated and normalized tags
            
        Raises:
            ValidationError: If tag validation fails
        """
        if not tags:
            return []
        
        validated = []
        user_tags_set = set(user_tags)
        
        for tag in tags:
            # Normalize
            tag = tag.strip().lstrip('#')
            
            if not tag:
                continue
            
            if len(tag) > 50:
                raise ValidationError(f"Tag too long (max 50 chars): {tag}")
            
            # Note: We now allow tags not in user's collection
            # They will be auto-created on submit
            validated.append(tag)
        
        return validated
    
    def extract_unique_tags_from_links(self, links) -> Set[str]:
        """
        Extract unique tags from a list of links.
        
        Args:
            links: List of Link objects
            
        Returns:
            Set of unique tags
        """
        all_tags = set()
        for link in links:
            if link.tags:
                all_tags.update(link.tags)
        return all_tags
