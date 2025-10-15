"""
Fetch driving distances between selected Swiss cities using the Google Maps
Distance Matrix API and persist the results to JSON.

Before running:
- Enable the Distance Matrix API in your Google Cloud project.
- Export GOOGLE_MAPS_API_KEY with a key that has the API enabled.

The script requests distances and durations for all city pairs in a single API
call (10 origins × 10 destinations = 100 elements, within the API limits) and
writes the output to ``data/out/google_city_distances.json``.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

import requests

CITIES: List[str] = [
    "Appenzell, Switzerland",
    "Bern, Switzerland",
    "Geneva, Switzerland",
    "Interlaken, Switzerland",
    "Lucerne, Switzerland",
    "Lugano, Switzerland",
    "Montreux, Switzerland",
    "Schwyz, Switzerland",
    "Zermatt, Switzerland",
    "Zurich, Switzerland",
]

OUTPUT_PATH = Path("data/out/google_city_distances.json")
DISTANCE_MATRIX_URL = "https://maps.googleapis.com/maps/api/distancematrix/json"


def request_distance_matrix(api_key: str) -> Dict:
    params = {
        "origins": "|".join(CITIES),
        "destinations": "|".join(CITIES),
        "mode": "driving",
        "units": "metric",
        "key": api_key,
    }

    response = requests.get(DISTANCE_MATRIX_URL, params=params, timeout=20)
    response.raise_for_status()

    payload = response.json()
    if payload.get("status") != "OK":
        raise RuntimeError(f"API error: {payload}")
    return payload


def build_distance_table(matrix_payload: Dict) -> Dict[str, Dict[str, Dict[str, float]]]:
    rows = matrix_payload.get("rows", [])
    table: Dict[str, Dict[str, Dict[str, float]]] = {}

    for origin, row in zip(CITIES, rows):
        elements = row.get("elements", [])
        table[origin] = {}
        for destination, element in zip(CITIES, elements):
            status = element.get("status")
            if status != "OK":
                table[origin][destination] = {"distance_km": None, "duration_minutes": None, "status": status}
                continue

            distance_m = element["distance"]["value"]
            duration_s = element["duration"]["value"]
            table[origin][destination] = {
                "distance_km": round(distance_m / 1000.0, 2),
                "duration_minutes": round(duration_s / 60.0, 1),
                "status": "OK",
            }

    return table


def persist_results(table: Dict[str, Dict[str, Dict[str, float]]]) -> None:
    payload = {
        "provider": "Google Distance Matrix API",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "units": {"distance": "km", "duration": "minutes"},
        "distances": table,
    }
    OUTPUT_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
    print(f"Wrote {OUTPUT_PATH}")


def main() -> None:
    api_key = ""
    matrix_payload = request_distance_matrix(api_key)
    distance_table = build_distance_table(matrix_payload)
    persist_results(distance_table)


if __name__ == "__main__":
    main()
