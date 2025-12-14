"""User settings endpoints."""
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from src.models.user import User
from src.utils.database import get_db
from src.utils.auth import get_current_user, verify_password, get_password_hash
from src.utils.encryption import encrypt_token
from src.utils.logging import logger

router = APIRouter(prefix="/api/settings", tags=["settings"])


class UpdateGitHubSettingsRequest(BaseModel):
    """Update GitHub settings request."""
    github_enabled: bool
    github_token: str | None = None
    repo_owner: str | None = None
    repo_name: str | None = None


class UpdatePasswordRequest(BaseModel):
    """Update password request."""
    current_password: str
    new_password: str = Field(..., min_length=8, max_length=100)


class SettingsResponse(BaseModel):
    """Settings response model."""
    username: str
    github_enabled: bool
    repo_owner: str | None = None
    repo_name: str | None = None
    has_github_token: bool

    class Config:
        from_attributes = True


@router.get("", response_model=SettingsResponse)
async def get_settings(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get current user settings.
    
    Args:
        current_user: Authenticated user
        db: Database session
        
    Returns:
        User settings
    """
    return SettingsResponse(
        username=current_user.username,
        github_enabled=current_user.github_enabled,
        repo_owner=current_user.repo_owner,
        repo_name=current_user.repo_name,
        has_github_token=current_user.encrypted_github_token is not None
    )


@router.put("/github", response_model=SettingsResponse)
async def update_github_settings(
    request: UpdateGitHubSettingsRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Update GitHub integration settings.
    
    Args:
        request: GitHub settings update request
        current_user: Authenticated user
        db: Database session
        
    Returns:
        Updated settings
        
    Raises:
        HTTPException: If validation fails
    """
    # Validate: if enabling GitHub, all fields must be provided
    if request.github_enabled:
        if not request.github_token or not request.repo_owner or not request.repo_name:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="GitHub token, repository owner, and repository name are required when enabling GitHub integration"
            )
        
        # Encrypt and store token
        current_user.encrypted_github_token = encrypt_token(request.github_token)
        current_user.repo_owner = request.repo_owner
        current_user.repo_name = request.repo_name
        current_user.github_enabled = True
        
        logger.info(f"User {current_user.username} enabled GitHub integration")
    else:
        # Disable GitHub (keep data but disable feature)
        current_user.github_enabled = False
        logger.info(f"User {current_user.username} disabled GitHub integration")
    
    db.commit()
    db.refresh(current_user)
    
    return SettingsResponse(
        username=current_user.username,
        github_enabled=current_user.github_enabled,
        repo_owner=current_user.repo_owner,
        repo_name=current_user.repo_name,
        has_github_token=current_user.encrypted_github_token is not None
    )


@router.put("/password")
async def update_password(
    request: UpdatePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Update user password.
    
    Args:
        request: Password update request
        current_user: Authenticated user
        db: Database session
        
    Returns:
        Success message
        
    Raises:
        HTTPException: If current password is incorrect
    """
    # Verify current password
    if not verify_password(request.current_password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect"
        )
    
    # Update password
    current_user.hashed_password = get_password_hash(request.new_password)
    db.commit()
    
    logger.info(f"User {current_user.username} updated password")
    
    return {"message": "Password updated successfully"}
