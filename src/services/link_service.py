"""Link service for business logic."""
from typing import List, Optional
from datetime import datetime
from sqlalchemy.orm import Session

from src.models.link import Link
from src.models.tag import Tag
from src.models import LinkStatus
from src.repositories.link_repository import LinkRepository
from src.exceptions import ValidationError, DuplicateError, NotFoundError


class LinkService:
    """Service for link business logic."""
    
    def __init__(self, db: Session):
        """Initialize service with database session."""
        self.repository = LinkRepository(db)
        self.db = db
    
    def submit_link(
        self,
        user_id: int,
        url: str,
        score: float,
        tag_objects: List[Tag],
        manual_title: Optional[str] = None
    ) -> Link:
        """
        Submit a new link.
        
        Args:
            user_id: User ID
            url: Link URL
            score: Link score (0.00-1.00)
            tag_objects: List of Tag objects to associate with link
            manual_title: Optional manual title
            
        Returns:
            Created link
            
        Raises:
            ValidationError: If input validation fails
            DuplicateError: If URL already exists
        """
        # Validate score
        if not (0 <= score <= 1):
            raise ValidationError("Score must be between 0.00 and 1.00")
        
        # Check for duplicate
        if self.repository.exists(url, user_id):
            raise DuplicateError(f"Link already exists: {url}")
        
        # Create link
        link = Link(
            user_id=user_id,
            url=url,
            score=score,
            status=LinkStatus.PENDING,
            submitted_at=datetime.utcnow()
        )
        
        if manual_title:
            link.title = manual_title
        
        # Add to session first to get ID
        self.db.add(link)
        self.db.flush()
        
        # Assign tags
        link.tags = tag_objects
        
        self.db.commit()
        self.db.refresh(link)
        return link
    
    def get_link(self, link_id: int, user_id: int) -> Link:
        """
        Get link by ID.
        
        Args:
            link_id: Link ID
            user_id: User ID (for authorization)
            
        Returns:
            Link object
            
        Raises:
            NotFoundError: If link not found
        """
        link = self.repository.get_by_id(link_id, user_id)
        if not link:
            raise NotFoundError(f"Link not found: {link_id}")
        return link
    
    def update_link(
        self,
        link_id: int,
        user_id: int,
        title: Optional[str] = None,
        score: Optional[float] = None,
        tag_objects: Optional[List[Tag]] = None
    ) -> Link:
        """
        Update link details.
        
        Args:
            link_id: Link ID
            user_id: User ID (for authorization)
            title: Optional new title
            score: Optional new score
            tag_objects: Optional new Tag objects list
            
        Returns:
            Updated link
            
        Raises:
            NotFoundError: If link not found
            ValidationError: If input validation fails
        """
        link = self.get_link(link_id, user_id)
        
        if title is not None:
            link.title = title
        
        if score is not None:
            if not (0 <= score <= 1):
                raise ValidationError("Score must be between 0.00 and 1.00")
            link.score = score
        
        if tag_objects is not None:
            link.tags = tag_objects
        
        return self.repository.update(link)
    
    def update_link_status(
        self,
        link_id: int,
        user_id: int,
        status: LinkStatus,
        error_message: Optional[str] = None
    ) -> Link:
        """
        Update link status.
        
        Args:
            link_id: Link ID
            user_id: User ID (for authorization)
            status: New status
            error_message: Optional error message
            
        Returns:
            Updated link
            
        Raises:
            NotFoundError: If link not found
        """
        link = self.get_link(link_id, user_id)
        link.status = status
        
        if error_message:
            link.error_message = error_message
        
        if status == LinkStatus.COMPLETED:
            link.processed_at = datetime.utcnow()
        
        return self.repository.update(link)
    
    def increment_retry_count(self, link_id: int, user_id: int) -> Link:
        """
        Increment retry count for a link.
        
        Args:
            link_id: Link ID
            user_id: User ID (for authorization)
            
        Returns:
            Updated link
            
        Raises:
            NotFoundError: If link not found
        """
        link = self.get_link(link_id, user_id)
        link.retry_count += 1
        return self.repository.update(link)
    
    def get_user_links(
        self,
        user_id: int,
        limit: int = 50,
        offset: int = 0,
        status: Optional[LinkStatus] = None,
        tag_names: Optional[List[str]] = None
    ) -> List[Link]:
        """
        Get links for a user.
        
        Args:
            user_id: User ID
            limit: Maximum number of links to return
            offset: Offset for pagination
            status: Optional status filter
            tag_names: Optional list of tag names to filter by (all must match)
            
        Returns:
            List of links
        """
        if tag_names:
            return self.repository.get_user_links_by_tags(user_id, tag_names, limit, offset)
        return self.repository.get_user_links(user_id, limit, offset, status)
    
    def get_pending_links(self, max_retries: int) -> List[Link]:
        """
        Get all pending links that haven't exceeded retry limit.
        
        Args:
            max_retries: Maximum number of retries allowed
            
        Returns:
            List of pending links
        """
        return self.repository.get_pending_links(max_retries)
    
    def get_stale_processing_links(self, stale_threshold, max_retries: int) -> List[Link]:
        """
        Get links stuck in processing state.
        
        Args:
            stale_threshold: DateTime threshold for stale links
            max_retries: Maximum number of retries allowed
            
        Returns:
            List of stale links
        """
        return self.repository.get_stale_processing_links(stale_threshold, max_retries)
    
    def delete_link(self, link_id: int, user_id: int) -> None:
        """
        Delete a link.
        
        Args:
            link_id: Link ID
            user_id: User ID (for authorization)
            
        Raises:
            NotFoundError: If link not found
        """
        link = self.get_link(link_id, user_id)
        self.db.delete(link)
        self.db.commit()
