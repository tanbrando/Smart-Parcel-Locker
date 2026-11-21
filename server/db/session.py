"""
Database Session and Engine Setup using SQLAlchemy.
"""
from typing import Generator
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker, Session

from server.core.config import settings

# Handle SQLite check_same_thread requirement
connect_args = {}
if settings.DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False, "timeout": 15}

engine = create_engine(
    settings.DATABASE_URL,
    connect_args=connect_args,
    echo=(settings.APP_ENV == "development" and False),
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db() -> Generator[Session, None, None]:
    """FastAPI Dependency providing database session lifecycle."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

