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
    TELEGRAM_DEFAULT_CHAT_ID: Optional[int] = None
    TELEGRAM_BOT_USERNAME: str = "SmartParcelLockerBot"
    ENABLE_TELEGRAM_BOT_POLLING: bool = True

    # OTP and Locker rules
    OTP_VALID_HOURS: int = 72
    OTP_LENGTH: int = 6
    MAX_OTP_ATTEMPTS: int = 3
    LOCKOUT_SECONDS: int = 60
    WEIGHT_TOLERANCE_GRAMS: int = 150

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
