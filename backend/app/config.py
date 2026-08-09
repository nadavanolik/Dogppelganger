"""App settings, read from environment variables (or a local .env file)."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # In Docker this points at the Postgres container; locally it falls back to
    # a throwaway SQLite file so you can run the backend with zero setup.
    DATABASE_URL: str = "sqlite:///./dev.db"
    SECRET_KEY: str = "dev-secret-change-me"

    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 60 * 24  # 1 day


settings = Settings()
