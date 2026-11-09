"""
FastAPI Server Root Application [Person 4].
Smart Parcel Locker Central Management API.
"""
import sys
import warnings
from pathlib import Path

# Suppress Starlette/FastAPI deprecation warnings for cleaner console output
warnings.filterwarnings("ignore", category=DeprecationWarning)

# Compatibility shim for environments with Starlette 1.x where on_startup was removed from Router
try:
    import starlette.routing
    _orig_router_init = starlette.routing.Router.__init__
    def _patched_router_init(self, *args, **kwargs):
        kwargs.pop("on_startup", None)
        kwargs.pop("on_shutdown", None)
        _orig_router_init(self, *args, **kwargs)
        if not hasattr(self, "on_startup"):
            self.on_startup = []
        if not hasattr(self, "on_shutdown"):
            self.on_shutdown = []
    starlette.routing.Router.__init__ = _patched_router_init
except Exception:
    pass

# Ensure monorepo root is in sys.path so 'contracts' and 'server' import cleanly
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from server.core.config import settings
from server.db.session import engine, Base, SessionLocal
from server.db.models import Locker, LockerStatus, User
from server.routers import orders, edge, lockers, telegram
from server.services.telegram import start_telegram_polling_safe


def init_database_tables():
    """Initializes tables and seeds default users & physical lockers if not present."""
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        # Seed default users
        if db.query(User).count() == 0:
            default_users = [
                User(
                    id=1,
                    full_name="Nguyễn Minh Tấn",
                    phone="0912343456",
                    phone_last4="3456",
                    telegram_chat_id=123456789,
                ),
                User(
                    id=2,
                    full_name="Trần Thị Hoa",
                    phone="0987654321",
                    phone_last4="4321",
                    telegram_chat_id=987654321,
                ),
            ]
            db.add_all(default_users)
            db.commit()

        # Seed default lockers
        if db.query(Locker).count() == 0:
            default_lockers = [
                Locker(id=1, locker_number=1, current_weight=0, max_weight=5000, status=LockerStatus.EMPTY),
                Locker(id=2, locker_number=2, current_weight=0, max_weight=5000, status=LockerStatus.EMPTY),
                Locker(id=3, locker_number=3, current_weight=0, max_weight=5000, status=LockerStatus.EMPTY),
            ]
            db.add_all(default_lockers)
            db.commit()
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan context: initialize database & start bot polling safely."""
    init_database_tables()

    # Start Telegram polling loop in background if token is configured
    bot_stop_event = asyncio.Event()
    bot_task = None
    if settings.TELEGRAM_BOT_TOKEN and settings.ENABLE_TELEGRAM_BOT_POLLING:
        bot_task = asyncio.create_task(start_telegram_polling_safe(bot_stop_event))

    yield

    # Clean shutdown of bot polling task
    if bot_task:
        bot_stop_event.set()
        try:
            await asyncio.wait_for(bot_task, timeout=4.0)
        except Exception:
            pass


app = FastAPI(
    title=settings.PROJECT_NAME,
    description="Cloud API and IoT Coordinator for Smart Parcel Locker System (Person 4)",
    version="1.0.0",
    lifespan=lifespan,
)

# Enable CORS for Web Dashboard
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", tags=["Health"])
def health_check():
    """Service liveness probe."""
    return {"status": "ok", "app": settings.PROJECT_NAME, "env": settings.APP_ENV}


# Include Routers
app.include_router(orders.router, prefix=settings.API_V1_STR)
app.include_router(edge.router, prefix=settings.API_V1_STR)
app.include_router(lockers.router, prefix=settings.API_V1_STR)
app.include_router(telegram.router, prefix=settings.API_V1_STR)


# Mount static files for Web Dashboard (CSS, JS, Assets)
web_dir = REPO_ROOT / "web"
if web_dir.exists():
    app.mount("/static", StaticFiles(directory=web_dir), name="static")


@app.get("/", include_in_schema=False)
def serve_dashboard():
    """Serves the Overview Bento Dashboard."""
    dashboard_path = REPO_ROOT / "web" / "index.html"
    if dashboard_path.exists():
        return FileResponse(dashboard_path)
    return {"message": "Smart Parcel Locker API is running. Visit /docs for Swagger UI."}


@app.get("/lockers", include_in_schema=False)
def serve_lockers():
    """Serves the Lockers Management Page."""
    return FileResponse(REPO_ROOT / "web" / "lockers.html")


@app.get("/orders", include_in_schema=False)
def serve_orders():
    """Serves the Orders & Anti-Fraud Verification Page."""
    return FileResponse(REPO_ROOT / "web" / "orders.html")


@app.get("/users", include_in_schema=False)
def serve_users():
    """Serves the Users & Telegram Accounts Page."""
    return FileResponse(REPO_ROOT / "web" / "users.html")


@app.get("/logs", include_in_schema=False)
def serve_logs():
    """Serves the Access & Audit Logs Page."""
    return FileResponse(REPO_ROOT / "web" / "logs.html")


@app.get("/simulator", include_in_schema=False)
def serve_simulator():
    """Serves the Testing & Simulator Console Page."""
    return FileResponse(REPO_ROOT / "web" / "simulator.html")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server.main:app", host="0.0.0.0", port=8000, reload=True)

