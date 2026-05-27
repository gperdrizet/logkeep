"""Authentication utilities."""
import os
import bcrypt
from datetime import datetime, timedelta
from typing import Optional
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from sqlalchemy.orm import Session
from dotenv import load_dotenv
from src.config import settings
from src.models.user import User
from src.utils.database import get_db

load_dotenv()

# HTTP Bearer for optional cookie-based auth
security = HTTPBearer(auto_error=False)


def is_admin_user(user: User) -> bool:
    """Check if a user is in configured admin usernames."""
    admins = {
        name.strip().lower()
        for name in settings.admin_usernames.split(",")
        if name.strip()
    }
    return user.username.lower() in admins


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash."""
    return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))


def get_password_hash(password: str) -> str:
    """Hash a password using bcrypt."""
    # Bcrypt automatically handles the 72-byte limit
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
    return hashed.decode('utf-8')


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """
    Create a JWT access token.
    
    Args:
        data: Payload to encode in token
        expires_delta: Optional expiration time delta
        
    Returns:
        Encoded JWT token
    """
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now() + expires_delta
    else:
        expire = datetime.now() + timedelta(minutes=settings.access_token_expire_minutes)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.session_secret, algorithm=settings.algorithm)
    return encoded_jwt


def decode_access_token(token: str) -> Optional[dict]:
    """
    Decode a JWT access token.
    
    Args:
        token: JWT token string
        
    Returns:
        Decoded payload or None if invalid
    """
    try:
        payload = jwt.decode(token, settings.session_secret, algorithms=[settings.algorithm])
        return payload
    except JWTError:
        return None


async def get_current_user(
    request: Request,
    db: Session = Depends(get_db)
) -> User:
    """
    Get current authenticated user from session cookie.
    
    Args:
        request: FastAPI request object
        db: Database session
        
    Returns:
        Current user object
        
    Raises:
        HTTPException: If not authenticated or user not found
    """
    # Get token from cookie
    token = request.cookies.get("session")
    
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated"
        )
    
    # Decode token
    payload = decode_access_token(token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials"
        )
    
    # Get user ID from payload
    user_id = payload.get("sub")
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials"
        )
    
    # Convert to int if string
    try:
        user_id = int(user_id)
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid user ID in token"
        )
    
    # Get user from database
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found"
        )
    
    # Check if user is active
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is deactivated"
        )

    # Attach transient admin flag for template/navigation convenience.
    user.is_admin = is_admin_user(user)
    
    return user


async def get_current_admin_user(
    current_user: User = Depends(get_current_user)
) -> User:
    """Require an authenticated admin user."""
    if not is_admin_user(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    return current_user


async def get_current_user_optional(
    request: Request,
    db: Session = Depends(get_db)
) -> Optional[User]:
    """
    Get current authenticated user if available (doesn't raise exception).
    
    Args:
        request: FastAPI request object
        db: Database session
        
    Returns:
        Current user object or None
    """
    try:
        return await get_current_user(request, db)
    except HTTPException:
        return None
