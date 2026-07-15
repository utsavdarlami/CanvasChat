from pathlib import Path
from typing import List

from fastapi import APIRouter, UploadFile, File, HTTPException
from pydantic import BaseModel

from core.config import settings
from core.logger import logger

router: APIRouter = APIRouter()

ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg"}


class UploadedFile(BaseModel):
    filename: str
    url: str


class UploadResponse(BaseModel):
    uploaded: List[UploadedFile]


@router.post(
    "/upload-files",
    response_model=UploadResponse,
    tags=["Upload"],
)
async def upload_files(files: List[UploadFile] = File(...)):
    """
    Upload image files to the static directory.

    Accepts multiple image files and stores them in STATIC_DIR.
    Returns the served URL paths for each uploaded file.
    """
    static_dir = Path(settings.STATIC_DIR)
    static_dir.mkdir(parents=True, exist_ok=True)

    uploaded: List[UploadedFile] = []

    for file in files:
        if not file.filename:
            continue

        ext = Path(file.filename).suffix.lower()
        if ext not in ALLOWED_IMAGE_EXTENSIONS:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported file type '{ext}' for '{file.filename}'. Allowed: {', '.join(sorted(ALLOWED_IMAGE_EXTENSIONS))}",
            )

        # Flatten to just the filename (no subdirectories from client)
        safe_name = Path(file.filename).name
        dest = static_dir / safe_name

        logger.info(f"Saving uploaded file: {safe_name} -> {dest}")
        content = await file.read()
        dest.write_bytes(content)

        uploaded.append(UploadedFile(
            filename=safe_name,
            url=f"/static/{safe_name}",
        ))

    logger.info(f"Uploaded {len(uploaded)} files to {static_dir}")
    return UploadResponse(uploaded=uploaded)
