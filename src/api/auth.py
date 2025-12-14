"""Authentication endpoints."""
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from src.models.user import User
from src.models.invite import Invite
from src.utils.database import get_db
from src.utils.auth import (
    verify_password,
    get_password_hash,
    create_access_token,
    get_current_user,
    get_current_user_optional
)
from src.utils.encryption import encrypt_token
from src.utils.logging import logger

router = APIRouter(prefix="/api/auth", tags=["auth"])


class RegisterRequest(BaseModel):
    """Registration request model."""
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=8, max_length=100)
    invite_code: str = Field(..., min_length=36, max_length=36)
    github_enabled: bool = Field(default=False)
    github_token: str | None = Field(default=None)
    repo_owner: str | None = Field(default=None)
    repo_name: str | None = Field(default=None)


class LoginRequest(BaseModel):
    """Login request model."""
    username: str
    password: str


class UserResponse(BaseModel):
    """User response model."""
    id: int
    username: str
    github_enabled: bool
    repo_owner: str | None = None
    repo_name: str | None = None
    tag_count: int

    class Config:
        from_attributes = True


@router.post("/register", response_model=UserResponse)
async def register(
    request: RegisterRequest,
    db: Session = Depends(get_db)
):
    """
    Register a new user with invite code.
    
    Args:
        request: Registration request data
        db: Database session
        
    Returns:
        Created user data
        
    Raises:
        HTTPException: If username exists, invite invalid, or registration fails
    """
    # Check if username already exists
    existing_user = db.query(User).filter(User.username == request.username).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already exists"
        )
    
    # Validate invite code
    invite = db.query(Invite).filter(Invite.code == request.invite_code).first()
    if not invite:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid invite code"
        )
    
    if invite.is_used:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invite code already used"
        )
    
    # Validate GitHub fields if GitHub is enabled
    if request.github_enabled:
        if not request.github_token or not request.repo_owner or not request.repo_name:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="GitHub token, repository owner, and repository name are required when GitHub integration is enabled"
            )
        encrypted_token = encrypt_token(request.github_token)
    else:
        encrypted_token = None
    
    # Create user
    user = User(
        username=request.username,
        hashed_password=get_password_hash(request.password),
        github_enabled=request.github_enabled,
        encrypted_github_token=encrypted_token,
        repo_owner=request.repo_owner,
        repo_name=request.repo_name,
        tags=[],
        is_active=True
    )
    
    db.add(user)
    db.flush()  # Get user ID
    
    # Mark invite as used
    invite.used_by_user_id = user.id
    invite.used_at = datetime.now()
    
    db.commit()
    db.refresh(user)
    
    logger.info(f"New user registered: {user.username} (GitHub enabled: {user.github_enabled})")
    
    return UserResponse(
        id=user.id,
        username=user.username,
        github_enabled=user.github_enabled,
        repo_owner=user.repo_owner,
        repo_name=user.repo_name,
        tag_count=len(user.tags)
    )


@router.post("/login")
async def login(
    request: LoginRequest,
    response: Response,
    db: Session = Depends(get_db)
):
    """
    Login user and set session cookie.
    
    Args:
        request: Login credentials
        response: FastAPI response object
        db: Database session
        
    Returns:
        Success message
        
    Raises:
        HTTPException: If credentials invalid
    """
    # Get user
    user = db.query(User).filter(User.username == request.username).first()
    if not user or not verify_password(request.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password"
        )
    
    # Check if active
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is deactivated"
        )
    
    # Create access token
    access_token = create_access_token(data={"sub": user.id})
    
    # Set cookie
    response.set_cookie(
        key="session",
        value=access_token,
        httponly=True,
        max_age=60 * 60 * 24 * 7,  # 7 days
        samesite="lax"
    )
    
    logger.info(f"User logged in: {user.username}")
    
    return {"message": "Login successful", "username": user.username}


@router.post("/logout")
async def logout(response: Response):
    """
    Logout user by clearing session cookie.
    
    Args:
        response: FastAPI response object
        
    Returns:
        Success message
    """
    response.delete_cookie(key="session")
    return {"message": "Logout successful"}


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    """
    Get current user information.
    
    Args:
        current_user: Authenticated user
        
    Returns:
        User data
    """
    return UserResponse(
        id=current_user.id,
        username=current_user.username,
        github_enabled=current_user.github_enabled,
        repo_owner=current_user.repo_owner,
        repo_name=current_user.repo_name,
        tag_count=len(current_user.tags)
    )
