#!/usr/bin/env python3

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
INPUT_FILE = PROJECT_ROOT / "data" / "allData.json"
OUTPUT_FILE = PROJECT_ROOT / "data" / "out" / "parsed_allData.json"


SeasonType = Union[List[str], Dict[str, Optional[str]]]


def load_payload(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def extract_identifier(item: Dict[str, Any]) -> Optional[str]:
    identifier = item.get("identifier")
    if identifier:
        return str(identifier)
    fallback = item.get("url") or item.get("@id")
    return str(fallback) if fallback else None


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


def extract_address(item: Dict[str, Any]) -> Optional[List[Dict[str, Any]]]:
    address = item.get("address")
    if isinstance(address, list):
        filtered: List[Dict[str, Any]] = []
        for entry in address:
            if isinstance(entry, dict):
                filtered.append(entry)
        if filtered:
            return filtered
        return None
    if isinstance(address, dict):
        return [address]
    return None


def build_entry(item: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": extract_identifier(item),
        "name": item.get("name"),
        "address": extract_address(item),
        "classification": item.get("classification"),
        "season": extract_season(item),
        "top": item.get("top"),
    }


def main() -> None:
    payload = load_payload(INPUT_FILE)
    records = payload.get("data")
    if not isinstance(records, list):
        raise ValueError("Expected 'data' to be a list in allData.json")

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    cleaned = [build_entry(item) for item in records if isinstance(item, dict)]

    with OUTPUT_FILE.open("w", encoding="utf-8") as handle:
        json.dump(cleaned, handle, ensure_ascii=False, indent=2)

    print(f"Parsed {len(cleaned)} POIs -> {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
