"""
Main FastAPI application entry point.
Configures database table creation via lifespan context, router inclusion, and health checks.
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.files import router as files_router
from app.db import Base, engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Ensure database schema is created on startup
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title="Geo Measurement API",
    description="API for measuring geospatial features from KML and Shapefile archives via UTM projection.",
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(files_router)


@app.get("/health", tags=["system"])
def health():
    return {"status": "ok"}
