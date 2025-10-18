"""
Download POI cover photos and update the dataset to reference local copies.

Reads ``data/out/selected_city_pois_llm_season_labeled.json``, downloads any
remote URLs stored in the ``photo`` field into ``web/public/poi_photos`` and
rewrites the ``photo`` value to point to ``/poi_photos/<identifier>.<ext>``.
"""

from __future__ import annotations

import json
import mimetypes
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional
from urllib.error import URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

POI_PATH = Path("data/out/selected_city_pois_llm_season_labeled.json")
OUTPUT_DIR = Path("web/public/poi_photos")
LOCAL_PREFIX = "/poi_photos"

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
CONTENT_TYPE_EXTENSION = {
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/123.0.0.0 Safari/537.36"
    ),
    "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.8",
}


def load_pois(path: Path) -> List[Dict]:
    if not path.exists():
        raise FileNotFoundError(f"POI file not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def ensure_output_dir() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def safe_identifier(identifier: str) -> str:
    cleaned = re.sub(r"[^\w\-]+", "-", identifier.strip())
    return cleaned or "poi"


def existing_asset_path(safe_id: str) -> Optional[Path]:
    for ext in ALLOWED_EXTENSIONS:
        candidate = OUTPUT_DIR / f"{safe_id}{ext}"
        if candidate.exists():
            return candidate
    return None


def infer_extension(url: str, content_type: str) -> str:
    parsed = urlparse(url)
    url_ext = Path(parsed.path).suffix.lower()
    if url_ext in ALLOWED_EXTENSIONS:
        return url_ext
    if content_type:
        ext = CONTENT_TYPE_EXTENSION.get(content_type.lower())
        if ext:
            return ext
        guessed = mimetypes.guess_extension(content_type)
        if guessed and guessed.lower() in ALLOWED_EXTENSIONS:
            return guessed.lower()
    return ".jpg"


def download_photo(url: str) -> tuple[bytes, str]:
    request = Request(url, headers=HEADERS)
    with urlopen(request, timeout=30) as response:
        content_type = response.headers.get("Content-Type", "").split(";")[0].strip()
        data = response.read()
    extension = infer_extension(url, content_type)
    return data, extension


def main() -> None:
    ensure_output_dir()
    pois = load_pois(POI_PATH)

    downloaded = 0
    skipped_missing_url = 0
    reused_existing = 0
    failed: List[str] = []

    for poi in pois:
        photo_url = poi.get("photo")
        if not photo_url or not isinstance(photo_url, str):
            skipped_missing_url += 1
            continue

        identifier = poi.get("identifier") or poi.get("name") or "poi"
        safe_id = safe_identifier(str(identifier))

        existing_path = existing_asset_path(safe_id)
        if existing_path:
            poi["photo"] = f"{LOCAL_PREFIX}/{existing_path.name}"
            reused_existing += 1
            continue

        try:
            data, extension = download_photo(photo_url)
        except (URLError, TimeoutError) as error:
            failed.append(f"{identifier}: {error}")
            continue

        asset_path = OUTPUT_DIR / f"{safe_id}{extension}"
        asset_path.write_bytes(data)
        poi["photo"] = f"{LOCAL_PREFIX}/{asset_path.name}"
        downloaded += 1

        print(f"Saved {asset_path} ({len(data)} bytes)")

    POI_PATH.write_text(json.dumps(pois, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Downloaded {downloaded} photos.")
    print(f"Reused {reused_existing} existing files.")
    print(f"Skipped {skipped_missing_url} POIs without photo URLs.")

    if failed:
        print("Failed downloads:", file=sys.stderr)
        for entry in failed:
            print(f"- {entry}", file=sys.stderr)


if __name__ == "__main__":
    main()
