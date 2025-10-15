#!/usr/bin/env python3

"""Parse the expanded city attraction datasets under data/in."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Union

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
INPUT_GLOB = PROJECT_ROOT / "data" / "in" / "*_attractions.json"
OUTPUT_FILE = PROJECT_ROOT / "data" / "out" / "parsed_in_attractions.json"

CITY_LABELS = {
    "appenzell": "appenzell",
    "bern": "bern",
    "geneva": "geneva",
    "interlaken": "interlaken",
    "lucerne": "luzern",
    "lugano": "lugano",
    "montreux": "montreux",
    "schwyz": "schwyz",
    "zermatt": "zermatt",
    "zurich": "zurich",
}

SeasonType = Union[List[str], Dict[str, Optional[str]]]


def load_file(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def extract_identifier(item: Dict[str, Any], fallback_seed: str) -> str:
    identifier = item.get("identifier")
    if identifier:
        return str(identifier)
    for key in ("url", "@id"):
        candidate = item.get(key)
        if candidate:
            return str(candidate)
    name = (item.get("name") or "").strip()
    seed = f"{fallback_seed}|{name}"
    return hashlib.sha1(seed.encode("utf-8")).hexdigest()


ADDRESS_KEYS = (
    "name",
    "streetAddress",
    "postalCode",
    "addressLocality",
    "addressRegion",
    "addressCountry",
)


def flatten_address(item: Dict[str, Any]) -> Optional[str]:
    address = item.get("address")
    parts: List[str] = []

    def add_from_obj(obj: Dict[str, Any]) -> None:
        for key in ADDRESS_KEYS:
            value = obj.get(key)
            if value:
                parts.append(str(value))

    if isinstance(address, list):
        for entry in address:
            if isinstance(entry, dict):
                add_from_obj(entry)
                break
    elif isinstance(address, dict):
        add_from_obj(address)

    if parts:
        return ", ".join(parts)
    return None


def extract_season(item: Dict[str, Any]) -> Optional[SeasonType]:
    classifications = item.get("classification")
    if isinstance(classifications, list):
        seasons: List[str] = []
        for entry in classifications:
            if not isinstance(entry, dict):
                continue
            if entry.get("name") != "seasons":
                continue
            for value in entry.get("values") or []:
                if not isinstance(value, dict):
                    continue
                label = value.get("title") or value.get("name")
                if label:
                    seasons.append(str(label))
        if seasons:
            return seasons
    recommended = item.get("recommendedSeason")
    if isinstance(recommended, dict):
        start = recommended.get("start")
        end = recommended.get("end")
        if start or end:
            return {"start": start, "end": end}
    return None


def extract_top_flag(item: Dict[str, Any]) -> Optional[bool]:
    if "top" not in item:
        return None
    value = item.get("top")
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lower = value.strip().lower()
        if lower in {"true", "1"}:
            return True
        if lower in {"false", "0"}:
            return False
    return None


def build_entry(item: Dict[str, Any], fallback_seed: str, city: str) -> Dict[str, Any]:
    return {
        "id": extract_identifier(item, fallback_seed),
        "name": item.get("name"),
        "address": flatten_address(item),
        "classification": item.get("classification"),
        "season": extract_season(item),
        "top": extract_top_flag(item),
        "city": city,
    }


def iter_input_files() -> Iterable[Path]:
    yield from sorted(INPUT_GLOB.parent.glob(INPUT_GLOB.name))


def main() -> None:
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    entries: List[Dict[str, Any]] = []
    seen_ids = set()

    for path in iter_input_files():
        payload = load_file(path)
        data = payload.get("data")
        if not isinstance(data, list):
            continue

        slug = path.stem.replace("_attractions", "")
        city = CITY_LABELS.get(slug.lower())
        if not city:
            continue

        fallback_seed = path.stem
        for item in data:
            if not isinstance(item, dict):
                continue
            entry = build_entry(item, fallback_seed, city)
            entry_id = entry["id"]
            if entry_id in seen_ids:
                continue
            seen_ids.add(entry_id)
            entries.append(entry)

    with OUTPUT_FILE.open("w", encoding="utf-8") as handle:
        json.dump(entries, handle, ensure_ascii=False, indent=2)

    print(f"Parsed {len(entries)} POIs -> {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
