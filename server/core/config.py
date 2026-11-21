"""
Server Configuration Settings using Pydantic Settings.
"""
import os
from pathlib import Path
from typing import Optional
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_FACE_MODELS_DIR = REPO_ROOT / "edge" / "models" / "face"


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

    # Face ID (YuNet + SFace ONNX models & Edge Device Key)
    FACE_DEVICE_KEY: Optional[str] = None
    FACE_YUNET: str = str(DEFAULT_FACE_MODELS_DIR / "face_detection_yunet_2023mar.onnx")
    FACE_SFACE: str = str(DEFAULT_FACE_MODELS_DIR / "face_recognition_sface_2021dec.onnx")

    # OTP and Locker rules
    OTP_VALID_HOURS: int = 72
    OTP_LENGTH: int = 6
    MAX_OTP_ATTEMPTS: int = 3
    LOCKOUT_SECONDS: int = 60
    WEIGHT_TOLERANCE_GRAMS: int = 150

    @field_validator("TELEGRAM_DEFAULT_CHAT_ID", mode="before")
    @classmethod
    def _empty_str_to_none_int(cls, v):
        if isinstance(v, str) and not v.strip():
            return None
        return v

    @field_validator("TELEGRAM_BOT_TOKEN", mode="before")
    @classmethod
    def _empty_str_to_none_str(cls, v):
        if isinstance(v, str) and not v.strip():
            return None
        return v

    model_config = SettingsConfigDict(
        env_file=(str(REPO_ROOT / ".env"), str(REPO_ROOT / "server" / ".env")),
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()

# Export configured Face ID env vars into os.environ if not already overridden externally
if settings.FACE_DEVICE_KEY and not os.environ.get("FACE_DEVICE_KEY"):
    os.environ["FACE_DEVICE_KEY"] = settings.FACE_DEVICE_KEY
if settings.FACE_YUNET and not os.environ.get("FACE_YUNET"):
    os.environ["FACE_YUNET"] = settings.FACE_YUNET
if settings.FACE_SFACE and not os.environ.get("FACE_SFACE"):
    os.environ["FACE_SFACE"] = settings.FACE_SFACE
