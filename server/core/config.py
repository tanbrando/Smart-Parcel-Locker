"""
Server Configuration Settings using Pydantic Settings.
"""
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    APP_ENV: str = "development"
    PROJECT_NAME: str = "Smart Parcel Locker Server"
    API_V1_STR: str = "/api/v1"
    SECRET_KEY: str = "supersecretkey-smart-parcel-locker-change-in-production"

    # Database
    DATABASE_URL: str = "sqlite:///./parcel_locker.db"

    # Telegram Bot
    TELEGRAM_BOT_TOKEN: Optional[str] = None
    TELEGRAM_DEFAULT_CHAT_ID: Optional[str] = None

    # OTP and Locker rules
    OTP_VALID_MINUTES: int = 30
    OTP_LENGTH: int = 6
    MAX_OTP_ATTEMPTS: int = 3
    WEIGHT_TOLERANCE_GRAMS: float = 150.0

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()

