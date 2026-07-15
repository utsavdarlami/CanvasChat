from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from api.endpoints import analysis, chat, upload
from core.config import settings

app = FastAPI(
    title="Semantic Analysis API (Lite)",
    description="API for single-entity semantic extraction and layout agent chat.",
    version="2.0.0-lite",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve static files (images, etc.) from STATIC_DIR
static_dir = Path(settings.STATIC_DIR)
static_dir.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

app.include_router(analysis.router, prefix="/api", tags=["Analysis"])
app.include_router(chat.router, prefix="/api", tags=["Agent Chat"])
app.include_router(upload.router, prefix="/api", tags=["Upload"])


@app.get("/", include_in_schema=False)
async def root():
    return {
        "message": "Semantic Analysis API (Lite) is running. Access /docs for API documentation."
    }
