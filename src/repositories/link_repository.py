"""Link repository for database operations."""
from typing import List, Optional
from sqlalchemy.orm import Session
from src.models.link import Link
from src.models import LinkStatus


class LinkRepository:
    """Repository for Link database operations."""
    
    def __init__(self, db: Session):
        """Initialize repository with database session."""
        self.db = db
    
    def create(self, link: Link) -> Link:
        """
        Create a new link.
        
        Args:
            link: Link object to create
            
        Returns:
            Created link with ID
        """
        self.db.add(link)
        self.db.commit()
        self.db.refresh(link)
        return link
    
    def get_by_id(self, link_id: int, user_id: int) -> Optional[Link]:
        """
        Get link by ID and user ID.
        
        Args:
            link_id: Link ID
            user_id: User ID (for authorization)
            
        Returns:
            Link object or None if not found
        """
        return self.db.query(Link).filter(
            Link.id == link_id,
            Link.user_id == user_id
        ).first()
    
    def get_by_url(self, url: str, user_id: int) -> Optional[Link]:
        """
        Get link by URL and user ID.
        
        Args:
            url: Link URL
            user_id: User ID
            
        Returns:
            Link object or None if not found
        """
        return self.db.query(Link).filter(
            Link.user_id == user_id,
            Link.url == url
        ).first()
    
    def get_user_links(
        self,
        user_id: int,
        limit: int = 50,
        offset: int = 0,
        status: Optional[LinkStatus] = None
    ) -> List[Link]:
        """
        Get links for a user.
        
        Args:
            user_id: User ID
            limit: Maximum number of links to return
            offset: Offset for pagination
            status: Optional status filter
            
        Returns:
            List of links
        """
        query = self.db.query(Link).filter(Link.user_id == user_id)
        
        if status:
            query = query.filter(Link.status == status)
        
        return query.order_by(
            Link.submitted_at.desc()
        ).limit(limit).offset(offset).all()
    
    def get_pending_links(self, max_retries: int) -> List[Link]:
        """
        Get all pending links that haven't exceeded retry limit.
        
        Args:
            max_retries: Maximum number of retries allowed
            
        Returns:
            List of pending links
        """
        return self.db.query(Link).filter(
            Link.status == LinkStatus.PENDING,
            Link.retry_count < max_retries
        ).all()
    
    def get_stale_processing_links(self, stale_threshold, max_retries: int) -> List[Link]:
        """
        Get links stuck in processing state.
        
        Args:
            stale_threshold: DateTime threshold for stale links
            max_retries: Maximum number of retries allowed
            
        Returns:
            List of stale links
        """
        return self.db.query(Link).filter(
            Link.status == LinkStatus.PROCESSING,
            Link.submitted_at < stale_threshold,
            Link.retry_count < max_retries
        ).all()
    
    def update(self, link: Link) -> Link:
        """
        Update a link.
        
        Args:
            link: Link object to update
            
        Returns:
            Updated link
        """
        self.db.commit()
        self.db.refresh(link)
        return link
    
    def exists(self, url: str, user_id: int) -> bool:
        """
        Check if a link exists for a user.
        
        Args:
            url: Link URL
            user_id: User ID
            
        Returns:
            True if link exists, False otherwise
        """
        return self.db.query(Link).filter(
            Link.user_id == user_id,
            Link.url == url
        ).first() is not None
    
    def get_user_links_by_tags(
        self,
        user_id: int,
        tag_names: List[str],
        limit: int = 50,
        offset: int = 0
    ) -> List[Link]:
        """
        Get links for a user filtered by tags.
        
        Args:
            user_id: User ID
            tag_names: List of tag names (all must match)
            limit: Maximum number of links to return
            offset: Offset for pagination
            
        Returns:
            List of links that have ALL specified tags
        """
        from src.models.tag import Tag, link_tags
        
        # Build query with joins for each tag
        query = self.db.query(Link).filter(Link.user_id == user_id)
        
        for tag_name in tag_names:
            # Join through link_tags and tags tables for each tag
            query = query.join(
                link_tags,
                Link.id == link_tags.c.link_id
            ).join(
                Tag,
                (link_tags.c.tag_id == Tag.id) & (Tag.name == tag_name) & (Tag.user_id == user_id)
            )
        
        return query.order_by(
            Link.submitted_at.desc()
        ).limit(limit).offset(offset).all()
