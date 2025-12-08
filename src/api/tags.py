"""Tags management endpoints."""
import os
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from src.models.user import User
from src.utils.database import get_db
from src.utils.auth import get_current_user
from src.utils.logging import logger
from dotenv import load_dotenv

load_dotenv()

router = APIRouter(prefix="/api/tags", tags=["tags"])

MAX_TAGS_PER_USER = int(os.getenv("MAX_TAGS_PER_USER", "100"))


class AddTagRequest(BaseModel):
    """Add tag request model."""
    tag: str = Field(..., min_length=1, max_length=50, pattern=r'^[a-zA-Z0-9_-]+$')


class TagResponse(BaseModel):
    """Tag response model."""
    tags: List[str]


@router.get("/", response_model=TagResponse)
async def get_tags(
    current_user: User = Depends(get_current_user)
):
    """
    Get user's tag collection.
    
    Args:
        current_user: Authenticated user
        
    Returns:
        User's tags
    """
    return TagResponse(tags=sorted(current_user.tags))


@router.post("/", response_model=TagResponse)
async def add_tag(
    request: AddTagRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Add a new tag to user's collection.
    
    Args:
        request: Tag to add
        current_user: Authenticated user
        db: Database session
        
    Returns:
        Updated tag collection
        
    Raises:
        HTTPException: If tag limit exceeded or tag already exists
    """
    tag = request.tag.lower()
    
    # Check if tag already exists
    if tag in current_user.tags:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Tag '{tag}' already exists in your collection"
        )
    
    # Check tag limit
    if len(current_user.tags) >= MAX_TAGS_PER_USER:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Maximum tag limit ({MAX_TAGS_PER_USER}) reached. Remove unused tags first."
        )
    
    # Add tag
    current_user.tags.append(tag)
    db.commit()
    db.refresh(current_user)
    
    logger.info(f"Tag added by {current_user.username}: {tag}")
    
    return TagResponse(tags=sorted(current_user.tags))


@router.delete("/{tag}", response_model=TagResponse)
async def delete_tag(
    tag: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Remove a tag from user's collection.
    
    Args:
        tag: Tag to remove
        current_user: Authenticated user
        db: Database session
        
    Returns:
        Updated tag collection
        
    Raises:
        HTTPException: If tag not found
    """
    tag = tag.lower()
    
    if tag not in current_user.tags:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tag '{tag}' not found in your collection"
        )
    
    # Remove tag
    current_user.tags.remove(tag)
    db.commit()
    db.refresh(current_user)
    
    logger.info(f"Tag removed by {current_user.username}: {tag}")
    
    return TagResponse(tags=sorted(current_user.tags))
