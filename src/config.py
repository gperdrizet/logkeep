"""Application configuration management."""
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class Settings(BaseSettings):
    """Application settings with type validation."""
    
    # Database
    database_url: str = Field(default="sqlite:///data/logkeep.db", env="DATABASE_URL")
    
    # Security
    session_secret: str = Field(..., env="SESSION_SECRET")
    encryption_key: str = Field(..., env="ENCRYPTION_KEY")
    
    # Application
    max_tags_per_user: int = Field(default=1000, env="MAX_TAGS_PER_USER")
    max_retries: int = Field(default=3, env="MAX_RETRIES")
    processing_timeout_minutes: int = Field(default=5, env="PROCESSING_TIMEOUT_MINUTES")
    
    # Logging
    log_level: str = Field(default="INFO", env="LOG_LEVEL")
    
    # Environment
    environment: str = Field(default="development", env="ENVIRONMENT")
    
    # Server
    host: str = Field(default="0.0.0.0", env="HOST")
    port: int = Field(default=8000, env="PORT")
    
    # JWT
    access_token_expire_minutes: int = Field(default=60 * 24 * 7, env="ACCESS_TOKEN_EXPIRE_MINUTES")  # 7 days
    algorithm: str = Field(default="HS256", env="ALGORITHM")
    
    # Content extraction
    request_timeout: int = Field(default=10, env="REQUEST_TIMEOUT")
    
    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
        extra="ignore"
    )
    
    @property
    def is_production(self) -> bool:
        """Check if running in production environment."""
        return str(self.environment).lower() == "production"
    
    @property
    def is_development(self) -> bool:
        """Check if running in development environment."""
        return str(self.environment).lower() == "development"


# Global settings instance
settings = Settings()
