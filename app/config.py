"""Application configuration from environment variables."""
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # App
    APP_NAME: str = "MusicRec"
    APP_ENV: str = "development"
    APP_DEBUG: bool = True

    # MySQL
    MYSQL_HOST: str = "localhost"
    MYSQL_PORT: int = 13307
    MYSQL_USER: str = "music_app"
    MYSQL_PASSWORD: str = "music_app_pass_2026"
    MYSQL_DATABASE: str = "music_rec"

    # Redis
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 16379
    REDIS_PASSWORD: str = "redis_music_2026"

    # JWT
    JWT_SECRET_KEY: str = "super-secret-key-change-in-production-2026"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    @property
    def DATABASE_URL(self) -> str:
        return (
            f"mysql+aiomysql://{self.MYSQL_USER}:{self.MYSQL_PASSWORD}"
            f"@{self.MYSQL_HOST}:{self.MYSQL_PORT}/{self.MYSQL_DATABASE}"
        )

    @property
    def DATABASE_URL_SYNC(self) -> str:
        return (
            f"mysql+pymysql://{self.MYSQL_USER}:{self.MYSQL_PASSWORD}"
            f"@{self.MYSQL_HOST}:{self.MYSQL_PORT}/{self.MYSQL_DATABASE}"
        )

    @property
    def REDIS_URL(self) -> str:
        return f"redis://:{self.REDIS_PASSWORD}@{self.REDIS_HOST}:{self.REDIS_PORT}/0"

    class Config:
        # .env.local 后加载，优先级更高，本地开发覆盖 Docker 专用配置
        env_file = (".env", ".env.local")
        extra = "ignore"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
