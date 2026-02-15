from typing import List, Optional

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Application
    APP_NAME: str = "kirana"
    APP_ENV: str = "development"
    DEBUG: bool = False
    SECRET_KEY: str = "change-me-in-production"
    API_V1_STR: str = "/v1"

    # CORS
    CORS_ORIGINS: List[str] = ["http://localhost:3000", "http://localhost:8080", "http://localhost:7346"]

    # Database Components
    DB_HOST: str = "localhost"
    DB_PORT: int = 5432
    DB_USER: str = "kirana"
    DB_PASS: str = "kirana"
    DB_NAME: str = "kirana"
    DATABASE_URL: Optional[str] = None

    # Database Pool
    DB_POOL_SIZE: int = 20
    DB_MAX_OVERFLOW: int = 10
    DB_POOL_RECYCLE: int = 3600

    # Redis Components
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_URL: Optional[str] = None

    # LLM Providers (OpenAI & Compatible)
    OPENAI_API_KEY: Optional[str] = None
    OPENAI_BASE_URL: Optional[str] = None
    DEFAULT_MODEL: str = "gpt-4o-mini"

    # LLM Settings
    LLM_TIMEOUT: int = 60
    LLM_MAX_RETRIES: int = 3

    # MCP - Z.AI
    ZAI_API_KEY: Optional[str] = None
    ZAI_MCP_URL: str = "https://api.z.ai/api/mcp/web_search_prime/mcp"

    # Jina AI Reader (for web scraping)
    JINA_API_KEY: Optional[str] = None

    # Rate Limiting
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_REQUESTS_PER_MINUTE: int = 60

    # Session Management
    SESSION_EXPIRY_DAYS: int = 3
    SESSION_DELETION_DAYS: int = 7
    SESSION_CLEANUP_INTERVAL_HOURS: int = 1

    # Admin Panel
    ADMIN_PASSWORD: str = "admin"

    # API Authentication (single-tenant mode)
    KIRANA_API_KEY: str = "kirana-default-api-key-change-me"

    # Upload directory for knowledge files
    UPLOAD_DIR: str = "/app/uploads"

    # Logging
    LOG_LEVEL: str = "INFO"

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=True, extra="ignore")

    @property
    def is_production(self) -> bool:
        return self.APP_ENV == "production"

    @field_validator("DATABASE_URL", mode="before")
    def assemble_db_connection(cls, v: Optional[str], info) -> str:
        if isinstance(v, str) and v:
            return v
        values = info.data
        return f"postgresql+asyncpg://{values.get('DB_USER')}:{values.get('DB_PASS')}@{values.get('DB_HOST')}:{values.get('DB_PORT')}/{values.get('DB_NAME')}"

    @field_validator("REDIS_URL", mode="before")
    def assemble_redis_connection(cls, v: Optional[str], info) -> str:
        if isinstance(v, str) and v:
            return v
        values = info.data
        return f"redis://{values.get('REDIS_HOST')}:{values.get('REDIS_PORT')}/0"

settings = Settings()
