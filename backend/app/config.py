"""App settings, read from environment variables (or a local .env file)."""
from pydantic_settings import BaseSettings, SettingsConfigDict

# Values that ship in the repo as placeholders. Fine for a laptop, fatal in
# production once tokens are real — see `Settings.check_production_secrets`.
INSECURE_SECRET_KEYS = frozenset(
    {"", "change-me", "change-me-too", "dev-secret-change-me", "change-me-in-production"}
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # In Docker this points at the Postgres container; locally it falls back to
    # a throwaway SQLite file so you can run the backend with zero setup.
    DATABASE_URL: str = "sqlite:///./dev.db"
    SECRET_KEY: str = "dev-secret-change-me"

    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 60 * 24  # 1 day

    # Media tokens ride in query strings (an <img> or <video> element cannot
    # send an Authorization header), so they land in nginx access logs and
    # browser history. Short-lived and scope-limited to compensate — long
    # enough for a viewing session, including the Range requests a <video>
    # fires minutes later when someone drags the scrub bar.
    MEDIA_TOKEN_EXPIRE_MINUTES: int = 15

    def check_production_secrets(self) -> None:
        """Refuse to boot with a placeholder signing key against a real database.

        Harmless while nothing verified a token; once `/api/auth` issues them
        for real, a known SECRET_KEY means anyone can mint a token for any
        account. SQLite is exempt: that's the zero-setup local path, and
        failing there would just make the project hostile to run.
        """
        if self.DATABASE_URL.startswith("sqlite"):
            return
        if self.SECRET_KEY.strip() in INSECURE_SECRET_KEYS:
            raise RuntimeError(
                "SECRET_KEY is still the placeholder value. Anyone who reads this "
                "repo could forge a login token. Set a real one in the .env beside "
                "docker-compose.yml:\n\n    SECRET_KEY=$(openssl rand -hex 32)\n"
            )


settings = Settings()
