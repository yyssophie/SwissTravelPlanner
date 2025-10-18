"""
Merge image metadata from the raw POI export into the LLM-labelled dataset.

For every POI entry in ``data/out/selected_city_pois_llm_season_labeled.json``,
look up the matching record in ``data/out/selected_city_pois.json`` using the
``identifier`` field and copy over the ``image`` array as well as the ``photo``
URL when available.
"""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Dict, List

SOURCE_PATH = Path("data/out/selected_city_pois.json")
TARGET_PATH = Path("data/out/selected_city_pois_llm_season_labeled.json")


def load_json(path: Path):
    if not path.exists():
        raise FileNotFoundError(f"Expected file at {path} does not exist.")
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    source_pois: List[Dict] = load_json(SOURCE_PATH)
    target_pois: List[Dict] = load_json(TARGET_PATH)

    source_by_id = {
        poi.get("identifier"): poi for poi in source_pois if poi.get("identifier")
    }

    updated = 0
    missing_source = []
    missing_identifier = []

    for poi in target_pois:
        identifier = poi.get("identifier")
        if not identifier:
            missing_identifier.append(poi)
            continue

        source_match = source_by_id.get(identifier)
        if not source_match:
            missing_source.append(identifier)
            continue

        if "image" in source_match:
            poi["image"] = deepcopy(source_match["image"])
            updated += 1
        if "photo" in source_match:
            poi["photo"] = source_match["photo"]

    TARGET_PATH.write_text(
        json.dumps(target_pois, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"Updated image metadata for {updated} POIs.")
    if missing_source:
        print(f"Skipped {len(missing_source)} POIs without a matching source record.")
    if missing_identifier:
        print(f"Skipped {len(missing_identifier)} POIs without an identifier.")


if __name__ == "__main__":
    main()
