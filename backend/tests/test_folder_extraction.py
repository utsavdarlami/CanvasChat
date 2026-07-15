"""
Batch semantic extraction from FOLDER_DATA.

Reads all files from FOLDER_DATA/:
  - .json → Vega-Lite spec (type="visual")
  - .txt/.md → text document (type="text")
  - .jpg/.jpeg/.png/.gif/.webp → image (type="image", uploaded to /api/upload-files)

Caches each response individually in FOLDER_DATA/_cache/.
Assembles final output matching analyzed_entities format.

Usage:
    python tests/test_folder_extraction.py
    python tests/test_folder_extraction.py --folder /path/to/folder
"""

import argparse
import asyncio
import json
from pathlib import Path

import httpx

BASE_URL = "http://127.0.0.1:8000/api"
DEFAULT_FOLDER = Path(__file__).parent / "FOLDER_DATA"

TEXT_EXTENSIONS = {".txt", ".md"}
VISUAL_EXTENSIONS = {".json"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}


def build_request(file_path: Path) -> dict | None:
    """Build request payload from a file (text/visual only; images handled separately)."""
    ext = file_path.suffix.lower()

    if ext in IMAGE_EXTENSIONS:
        # Images are handled via upload + extract_image_one
        return None

    content = file_path.read_text(encoding="utf-8")

    if ext in VISUAL_EXTENSIONS:
        try:
            spec = json.loads(content)
        except json.JSONDecodeError:
            print(f"  SKIP {file_path.name}: invalid JSON")
            return None
        return {"type": "visual", "content": spec}

    if ext in TEXT_EXTENSIONS:
        if not content.strip():
            print(f"  SKIP {file_path.name}: empty file")
            return None
        return {"type": "text", "content": content, "metadata": {"filename": file_path.name}}

    return None


async def upload_image(client: httpx.AsyncClient, file_path: Path) -> str | None:
    """Upload an image file to the backend static dir. Returns the served filename."""
    print(f"  UPLOAD {file_path.name}")
    try:
        with open(file_path, "rb") as f:
            resp = await client.post(
                f"{BASE_URL}/upload-files",
                files=[("files", (file_path.name, f, f"image/{file_path.suffix.lstrip('.')}"))],
                timeout=30.0,
            )
        resp.raise_for_status()
        data = resp.json()
        uploaded = data.get("uploaded", [])
        if uploaded:
            return uploaded[0]["filename"]
    except (httpx.HTTPStatusError, httpx.RequestError) as e:
        print(f"  UPLOAD FAILED {file_path.name}: {e}")
    return None


async def extract_image_one(
    client: httpx.AsyncClient, file_path: Path, uploaded_filename: str, cache_dir: Path
) -> dict | None:
    """Extract semantics for an uploaded image file. Returns cached result if available."""
    # Use full name (e.g. "movie_1.jpg.json") to avoid collision with "movie_1.txt" → "movie_1.json"
    cache_file = cache_dir / f"{file_path.name}.json"

    if cache_file.exists():
        print(f"  CACHED {file_path.name}")
        return json.loads(cache_file.read_text())

    payload = {
        "type": "image",
        "content": uploaded_filename,
        "metadata": {"filename": file_path.name},
    }

    print(f"  -> {file_path.name} (image)")
    try:
        resp = await client.post(f"{BASE_URL}/extract-semantics", json=payload, timeout=60.0)
        resp.raise_for_status()
        result = resp.json()
        cache_file.write_text(json.dumps(result, indent=2))
        return result
    except (httpx.HTTPStatusError, httpx.RequestError) as e:
        print(f"  FAILED {file_path.name}: {e}")
        return None


async def extract_one(client: httpx.AsyncClient, file_path: Path, cache_dir: Path) -> dict | None:
    """Extract semantics for one text/visual file. Returns cached result if available."""
    cache_file = cache_dir / f"{file_path.stem}.json"

    # Return cached
    if cache_file.exists():
        print(f"  CACHED {file_path.name}")
        return json.loads(cache_file.read_text())

    payload = build_request(file_path)
    if payload is None:
        return None

    print(f"  -> {file_path.name} ({payload['type']})")
    try:
        resp = await client.post(f"{BASE_URL}/extract-semantics", json=payload, timeout=60.0)
        resp.raise_for_status()
        result = resp.json()

        # Cache individual response
        cache_file.write_text(json.dumps(result, indent=2))
        return result

    except (httpx.HTTPStatusError, httpx.RequestError) as e:
        print(f"  FAILED {file_path.name}: {e}")
        return None


async def run(folder: Path):
    """Process all files and assemble analyzed_entities output."""
    if not folder.is_dir():
        print(f"Folder not found: {folder}")
        print(f"Create it and add .json / .txt / .md / .jpg files.")
        return

    supported = TEXT_EXTENSIONS | VISUAL_EXTENSIONS | IMAGE_EXTENSIONS
    files = sorted(f for f in folder.iterdir() if f.is_file() and f.suffix.lower() in supported)

    if not files:
        print(f"No supported files in {folder}")
        return

    cache_dir = folder / "_cache"
    cache_dir.mkdir(exist_ok=True)

    print(f"Processing {len(files)} file(s) from {folder.name}/\n")

    analyzed_entities = []
    async with httpx.AsyncClient() as client:
        # First pass: upload all image files so they're available for extraction
        image_upload_map: dict[str, str] = {}  # file_path.name -> uploaded filename
        image_files = [f for f in files if f.suffix.lower() in IMAGE_EXTENSIONS]
        if image_files:
            print(f"Uploading {len(image_files)} image file(s)...\n")
            for img_file in image_files:
                uploaded_name = await upload_image(client, img_file)
                if uploaded_name:
                    image_upload_map[img_file.name] = uploaded_name
            print()

        for i, file_path in enumerate(files):
            ext = file_path.suffix.lower()

            if ext in IMAGE_EXTENSIONS:
                # Handle image extraction
                uploaded_name = image_upload_map.get(file_path.name)
                if not uploaded_name:
                    print(f"  SKIP {file_path.name}: upload failed earlier")
                    continue

                semantics = await extract_image_one(client, file_path, uploaded_name, cache_dir)
                if semantics is None:
                    continue

                # For images, value is the filename (frontend rewrites to full URL on load)
                analyzed_entities.append({
                    "id": f"entity-{i}",
                    "name": semantics.get("title") or file_path.stem,
                    "display_name": semantics.get("title") or file_path.stem,
                    "semantics": semantics,
                    "value": file_path.name,
                    "type": "image",
                })
            else:
                # Handle text/visual extraction
                semantics = await extract_one(client, file_path, cache_dir)
                if semantics is None:
                    continue

                raw = file_path.read_text(encoding="utf-8")
                entity_type = "visual" if ext in VISUAL_EXTENSIONS else "text"
                value = json.loads(raw) if entity_type == "visual" else raw

                analyzed_entities.append({
                    "id": f"entity-{i}",
                    "name": semantics.get("title") or file_path.stem,
                    "display_name": semantics.get("title") or file_path.stem,
                    "semantics": semantics,
                    "value": value,
                    "type": entity_type,
                })

    # Write final output
    output = {"analyzed_entities": analyzed_entities}
    output_path = folder / "_analyzed_output.json"
    output_path.write_text(json.dumps(output, indent=2))

    print(f"\n{len(analyzed_entities)} entities extracted")
    print(f"Output: {output_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Batch semantic extraction")
    parser.add_argument("--folder", type=Path, default=DEFAULT_FOLDER)
    args = parser.parse_args()
    asyncio.run(run(args.folder))
