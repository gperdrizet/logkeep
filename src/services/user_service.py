"""User service for business logic."""
from typing import Optional
from sqlalchemy.orm import Session
from passlib.context import CryptContext

from src.models.user import User
from src.repositories.user_repository import UserRepository
from src.repositories.invite_repository import InviteRepository
from src.exceptions import ValidationError, AuthenticationError, DuplicateError, NotFoundError


pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class UserService:
    """Service for user business logic."""
    
    def __init__(self, db: Session):
        """Initialize service with database session."""
        self.user_repo = UserRepository(db)
        self.invite_repo = InviteRepository(db)
    
    def register_user(
        self,
        username: str,
        password: str,
        invite_code: str,
        repo_owner: Optional[str] = None,
        repo_name: Optional[str] = None,
        github_token: Optional[str] = None
    ) -> User:
        """
        Register a new user.
        
        Args:
            username: Username
            password: Plain text password
            invite_code: Invite code
            repo_owner: GitHub repository owner
            repo_name: GitHub repository name
            github_token: Encrypted GitHub token
            
        Returns:
            Created user
            
        Raises:
            ValidationError: If input validation fails
            DuplicateError: If username already exists
            NotFoundError: If invite code invalid
        """
        # Validate username
        if not username or len(username) < 3:
            raise ValidationError("Username must be at least 3 characters")
        
        # Validate password
        if not password or len(password) < 8:
            raise ValidationError("Password must be at least 8 characters")
        
        # Check for duplicate username
        if self.user_repo.exists_by_username(username):
            raise DuplicateError(f"Username already exists: {username}")
        
        # Validate invite code
        invite = self.invite_repo.get_by_code(invite_code)
        if not invite:
            raise NotFoundError("Invalid invite code")
        
        if invite.is_used:
            raise ValidationError("Invite code already used")
        
        # Hash password
        hashed_password = pwd_context.hash(password)
        
        # Create user
        user = User(
            username=username,
            hashed_password=hashed_password,
            repo_owner=repo_owner,
            repo_name=repo_name,
            encrypted_github_token=github_token,
            tags=[],
            is_active=True
        )
        
        user = self.user_repo.create(user)
        
        # Mark invite as used
        self.invite_repo.mark_as_used(invite, user.id)
        
        return user
    
    def authenticate_user(self, username: str, password: str) -> User:
        """
        Authenticate a user.
        
        Args:
            username: Username
            password: Plain text password
            
        Returns:
            User object if authentication successful
            
        Raises:
            AuthenticationError: If authentication fails
        """
        user = self.user_repo.get_by_username(username)
        
        if not user:
            raise AuthenticationError("Invalid username or password")
        
        if not pwd_context.verify(password, user.password_hash):
            raise AuthenticationError("Invalid username or password")
        
        return user
    
    def get_user(self, user_id: int) -> User:
        """
        Get user by ID.
        
        Args:
            user_id: User ID
            
        Returns:
            User object
            
        Raises:
            NotFoundError: If user not found
        """
        user = self.user_repo.get_by_id(user_id)
        if not user:
            raise NotFoundError(f"User not found: {user_id}")
        return user
    
    def update_github_credentials(
        self,
        user_id: int,
        repo_owner: str,
        repo_name: str,
        github_token: str
    ) -> User:
        """
        Update user's GitHub credentials.
        
        Args:
            user_id: User ID
            repo_owner: GitHub repository owner
            repo_name: GitHub repository name
            github_token: Encrypted GitHub token
            
        Returns:
            Updated user
            
        Raises:
            NotFoundError: If user not found
            ValidationError: If credentials invalid
        """
        user = self.get_user(user_id)
        
        if not repo_owner or not repo_name:
            raise ValidationError("Repository owner and name are required")
        
        if not github_token:
            raise ValidationError("GitHub token is required")
        
        user.repo_owner = repo_owner
        user.repo_name = repo_name
        user.encrypted_github_token = github_token
        
        return self.user_repo.update(user)
