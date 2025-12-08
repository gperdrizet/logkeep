"""Links management endpoints."""
from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from pydantic import BaseModel, Field, HttpUrl
from sqlalchemy.orm import Session
from src.models.user import User
from src.models.link import Link
from src.models import LinkStatus
from src.utils.database import get_db
from src.utils.auth import get_current_user
from src.services.processor import validate_url, check_duplicate_url, process_link
from src.utils.logging import logger

router = APIRouter(prefix="/api/links", tags=["links"])


class SubmitLinkRequest(BaseModel):
    """Submit link request model."""
    url: str = Field(..., min_length=10)
    title: Optional[str] = Field(None, max_length=500)
    tags: List[str] = Field(default_factory=list)


class UpdateTitleRequest(BaseModel):
    """Update title request model."""
    title: str = Field(..., min_length=1, max_length=500)


class LinkResponse(BaseModel):
    """Link response model."""
    id: int
    url: str
    title: Optional[str]
    selected_tags: List[str]
    status: str
    retry_count: int
    error_message: Optional[str]
    submitted_at: datetime
    processed_at: Optional[datetime]

    class Config:
        from_attributes = True


@router.post("/submit", response_model=LinkResponse)
async def submit_link(
    request: SubmitLinkRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Submit a new link for processing.
    
    Args:
        request: Link submission data
        background_tasks: FastAPI background tasks
        current_user: Authenticated user
        db: Database session
        
    Returns:
        Created link data
        
    Raises:
        HTTPException: If URL invalid or duplicate
    """
    # Validate URL
    if not validate_url(request.url):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid URL format"
        )
    
    # Check for duplicate
    if check_duplicate_url(db, current_user.id, request.url):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This URL has already been submitted. Check your dashboard for the existing entry."
        )
    
    # Validate tags exist in user's collection
    invalid_tags = [tag for tag in request.tags if tag not in current_user.tags]
    if invalid_tags:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid tags: {', '.join(invalid_tags)}. Add them to your tag collection first."
        )
    
    # Create link
    link = Link(
        user_id=current_user.id,
        url=request.url,
        title=request.title,  # May be None
        selected_tags=request.tags,
        status=LinkStatus.PENDING,
        retry_count=0
    )
    
    db.add(link)
    db.commit()
    db.refresh(link)
    
    logger.info(f"Link submitted by {current_user.username}: {link.url} (ID: {link.id})")
    
    # Queue background processing
    background_tasks.add_task(process_link, link.id, db)
    
    return LinkResponse(
        id=link.id,
        url=link.url,
        title=link.title,
        selected_tags=link.selected_tags,
        status=link.status.value,
        retry_count=link.retry_count,
        error_message=link.error_message,
        submitted_at=link.submitted_at,
        processed_at=link.processed_at
    )


@router.get("/", response_model=List[LinkResponse])
async def get_links(
    limit: int = 50,
    offset: int = 0,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get user's link history.
    
    Args:
        limit: Maximum number of links to return
        offset: Offset for pagination
        current_user: Authenticated user
        db: Database session
        
    Returns:
        List of links
    """
    links = db.query(Link).filter(
        Link.user_id == current_user.id
    ).order_by(
        Link.submitted_at.desc()
    ).limit(limit).offset(offset).all()
    
    return [
        LinkResponse(
            id=link.id,
            url=link.url,
            title=link.title,
            selected_tags=link.selected_tags,
            status=link.status.value,
            retry_count=link.retry_count,
            error_message=link.error_message,
            submitted_at=link.submitted_at,
            processed_at=link.processed_at
        )
        for link in links
    ]


@router.get("/{link_id}", response_model=LinkResponse)
async def get_link(
    link_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get specific link details.
    
    Args:
        link_id: Link ID
        current_user: Authenticated user
        db: Database session
        
    Returns:
        Link data
        
    Raises:
        HTTPException: If link not found or not owned by user
    """
    link = db.query(Link).filter(
        Link.id == link_id,
        Link.user_id == current_user.id
    ).first()
    
    if not link:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Link not found"
        )
    
    return LinkResponse(
        id=link.id,
        url=link.url,
        title=link.title,
        selected_tags=link.selected_tags,
        status=link.status.value,
        retry_count=link.retry_count,
        error_message=link.error_message,
        submitted_at=link.submitted_at,
        processed_at=link.processed_at
    )


@router.patch("/{link_id}/title", response_model=LinkResponse)
async def update_title(
    link_id: int,
    request: UpdateTitleRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Update title for a link that needs manual title.
    
    Args:
        link_id: Link ID
        request: Title update data
        background_tasks: FastAPI background tasks
        current_user: Authenticated user
        db: Database session
        
    Returns:
        Updated link data
        
    Raises:
        HTTPException: If link not found, not owned, or wrong status
    """
    link = db.query(Link).filter(
        Link.id == link_id,
        Link.user_id == current_user.id
    ).first()
    
    if not link:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Link not found"
        )
    
    # Only allow title update for links in needs_title status
    if link.status != LinkStatus.NEEDS_TITLE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot update title for link with status: {link.status.value}"
        )
    
    # Update title and reset to pending for processing
    link.title = request.title
    link.status = LinkStatus.PENDING
    link.error_message = None
    
    db.commit()
    db.refresh(link)
    
    logger.info(f"Title updated for link {link_id} by {current_user.username}: {link.title}")
    
    # Requeue for processing
    background_tasks.add_task(process_link, link.id, db)
    
    return LinkResponse(
        id=link.id,
        url=link.url,
        title=link.title,
        selected_tags=link.selected_tags,
        status=link.status.value,
        retry_count=link.retry_count,
        error_message=link.error_message,
        submitted_at=link.submitted_at,
        processed_at=link.processed_at
    )
