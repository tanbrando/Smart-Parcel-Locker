"""
FastAPI Server Root Application [Person 4].
Smart Parcel Locker Central Management API.
"""
import sys
from pathlib import Path

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

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from server.core.config import settings
from server.db.session import engine, Base, SessionLocal
from server.db.models import Locker, LockerStatus
from server.routers import orders, edge, lockers


def init_database_tables():
    """Initializes tables and seeds default physical lockers if not present."""
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        count = db.query(Locker).count()
        if count == 0:
            initial_lockers = [
                Locker(id=1, locker_number="L01", status=LockerStatus.AVAILABLE, max_weight_capacity_grams=5000.0),
                Locker(id=2, locker_number="L02", status=LockerStatus.AVAILABLE, max_weight_capacity_grams=5000.0),
                Locker(id=3, locker_number="L03", status=LockerStatus.AVAILABLE, max_weight_capacity_grams=5000.0),
            ]
            db.add_all(initial_lockers)
            db.commit()
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan context: initialize database on startup."""
    init_database_tables()
    yield


app = FastAPI(
    title=settings.PROJECT_NAME,
    description="Cloud API and IoT Coordinator for Smart Parcel Locker System",
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
