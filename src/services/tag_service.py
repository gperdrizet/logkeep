"""Tag service for business logic."""
from typing import List, Set
from sqlalchemy.orm import Session

from src.models.tag import Tag
from src.repositories.tag_repository import TagRepository
from src.repositories.user_repository import UserRepository
from src.exceptions import ValidationError, NotFoundError
from src.config import settings


class TagService:
    """Service for tag business logic."""
    
    def __init__(self, db: Session):
        """Initialize service with database session."""
        self.tag_repo = TagRepository(db)
        self.user_repo = UserRepository(db)
    
    def add_tag(self, user_id: int, tag_name: str) -> Tag:
        """
        Add a tag to user's tag collection.
        
        Args:
            user_id: User ID
            tag_name: Tag name to add
            
        Returns:
            Created or existing Tag object
            
        Raises:
            NotFoundError: If user not found
            ValidationError: If tag invalid or limit exceeded
        """
        # Validate tag
        tag_name = tag_name.strip().lstrip('#')
        if not tag_name:
            raise ValidationError("Tag cannot be empty")
        
        if len(tag_name) > 50:
            raise ValidationError("Tag must be less than 50 characters")
        
        # Check if tag already exists
        existing_tag = self.tag_repo.get_by_name(user_id, tag_name)
        if existing_tag:
            return existing_tag
        
        # Check tag limit
        tag_count = self.tag_repo.count_user_tags(user_id)
        if tag_count >= settings.max_tags_per_user:
            raise ValidationError(
                f"Maximum {settings.max_tags_per_user} tags allowed per user"
            )
        
        # Create tag
        tag = Tag(user_id=user_id, name=tag_name, count=0)
        return self.tag_repo.create(tag)
    
    def delete_tag(self, user_id: int, tag_name: str):
        """
        Delete a tag from user's tag collection.
        
        Args:
            user_id: User ID
            tag_name: Tag name to delete
            
        Raises:
            NotFoundError: If user not found
            ValidationError: If tag not found
        """
        tag = self.tag_repo.get_by_name(user_id, tag_name)
        if not tag:
            raise ValidationError(f"Tag not found: {tag_name}")
        
        self.tag_repo.delete(tag)
    
    def get_user_tags(self, user_id: int) -> List[Tag]:
        """
        Get user's tag collection.
        
        Args:
            user_id: User ID
            
        Returns:
            List of Tag objects
        """
        return self.tag_repo.get_user_tags(user_id)
    
    def validate_tags(self, tag_names: List[str]) -> List[str]:
        """
        Validate and normalize tag names.
        
        Args:
            tag_names: Tag names to validate
            
        Returns:
            Validated and normalized tag names
            
        Raises:
            ValidationError: If tag validation fails
        """
        if not tag_names:
            return []
        
        validated = []
        
        for tag in tag_names:
            # Normalize
            tag = tag.strip().lstrip('#')
            
            if not tag:
                continue
            
            if len(tag) > 50:
                raise ValidationError(f"Tag too long (max 50 chars): {tag}")
            
            validated.append(tag)
        
        return validated
    
    def extract_unique_tags_from_links(self, links) -> Set[str]:
        """
        Extract unique tag names from a list of links.
        
        Args:
            links: List of Link objects
            
        Returns:
            Set of unique tag names
        """
        all_tags = set()
        for link in links:
            if link.tags:
                all_tags.update(tag.name for tag in link.tags)
        return all_tags    
    def get_or_create_tags(self, user_id: int, tag_names: List[str]) -> List[Tag]:
        """
        Get or create Tag objects for the given tag names.
        
        Args:
            user_id: User ID
            tag_names: List of tag names
            
        Returns:
            List of Tag objects
        """
        tags = []
        for name in tag_names:
            tag = self.tag_repo.get_or_create(user_id, name)
            tags.append(tag)
        return tags
    
    def search_tags(self, user_id: int, query: str, limit: int = 50) -> List[Tag]:
        """
        Search user's tags by name.
        
        Args:
            user_id: User ID
            query: Search query
            limit: Maximum results
            
        Returns:
            List of matching Tag objects
        """
        return self.tag_repo.search_user_tags(user_id, query, limit)