import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.api.ws.router import router as ws_router
from app.api.rest.auth import router as auth_router
from app.api.rest.documents import router as doc_router
from app.api.sse.analysis import router as sse_router
from app.models.base import Base
from app.core.db import engine
from app.core.metrics import instrument_app
from app.core.telemetry import setup_telemetry, instrument_app_telemetry, instrument_db_telemetry

# Configure Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)

# 1. Initialize FastAPI Application
app = FastAPI(
    title=settings.PROJECT_NAME,
    description="Production-ready real-time collaborative document platform with OT and debounced AI analysis.",
    version="1.0.0"
)

# 2. CORS Middleware configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Adjust for production restrictions
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

# 3. Mount REST, WS, and SSE Routers
app.include_router(auth_router, prefix=settings.API_V1_STR)
app.include_router(doc_router, prefix=settings.API_V1_STR)
app.include_router(sse_router, prefix=settings.API_V1_STR)
app.include_router(ws_router)  # Mounted at root for WebSocket /ws/doc/{id} endpoint


@app.on_event("startup")
async def startup_event():
    """
    Service startup initialization:
    - Sets up OpenTelemetry tracing.
    - Automates database migrations (table creation).
    """
    logger.info("Initializing CollabStream service...")
    
    # Setup OpenTelemetry
    setup_telemetry()
    instrument_app_telemetry(app)
    instrument_db_telemetry(engine)

    # Initialize SQL database tables automatically
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables initialized successfully.")


# 4. Attach Prometheus performance monitoring instrumentations
instrument_app(app)


@app.get("/")
async def root():
    return {
        "status": "healthy",
        "service": settings.PROJECT_NAME,
        "version": "1.0.0",
        "documentation": "/docs"
    }

# PEP8 clean audit update 7
