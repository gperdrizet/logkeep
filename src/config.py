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
    
    # LLM Configuration (OpenAI-compatible API)
    llm_base_url: str = Field(default="https://api.openai.com/v1", env="LLM_BASE_URL")
    llm_api_key: str = Field(default="", env="LLM_API_KEY")
    llm_model_name: str = Field(default="gpt-4o-mini", env="LLM_MODEL_NAME")
    llm_timeout: int = 180
    llm_max_input_tokens: int = 4000
    llm_max_retries: int = 3
    llm_retry_delays: list = Field(default_factory=lambda: [5, 10, 20])
    llm_temperature: float = 0.3
    summarize_on_submit: bool = True
    summary_max_length: int = Field(default=2000)
    
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

    @property
    def llm_enabled(self) -> bool:
        """Enable LLM only when the minimum API settings are configured."""
        return bool(
            self.llm_base_url.strip()
            and self.llm_model_name.strip()
            and self.llm_api_key.strip()
        )


# Global settings instance
settings = Settings()
