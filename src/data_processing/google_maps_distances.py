"""
Fetch driving distances between selected Swiss cities using the Google Maps
Distance Matrix API and persist the results to JSON.

Before running:
- Enable the Distance Matrix API in your Google Cloud project.
- Export GOOGLE_MAPS_API_KEY with a key that has the API enabled.

The script batches requests so the product ``origins × destinations`` never
exceeds the Distance Matrix API limit of 100 elements. Results are merged and
written to ``data/out/google_city_distances.json``.
"""

from __future__ import annotations

import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List

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
    "Lausanne, Switzerland",
    "Kandersteg, Switzerland",
    "Sion, Switzerland",
    "St. Gallen, Switzerland",
    "St. Moritz, Switzerland",
    "Zermatt, Switzerland",
    "Zurich, Switzerland",
]

OUTPUT_PATH = Path("data/out/google_city_distances.json")
DISTANCE_MATRIX_URL = "https://maps.googleapis.com/maps/api/distancematrix/json"


def chunked(sequence: Iterable[str], size: int) -> Iterable[List[str]]:
    seq = list(sequence)
    for index in range(0, len(seq), size):
        yield seq[index : index + size]


def request_distance_matrix(api_key: str, origins: List[str], destinations: List[str]) -> Dict:
    params = {
        "origins": "|".join(origins),
        "destinations": "|".join(destinations),
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


def build_distance_table(
    origins: List[str],
    destinations: List[str],
    matrix_payload: Dict,
) -> Dict[str, Dict[str, Dict[str, float]]]:
    rows = matrix_payload.get("rows", [])
    table: Dict[str, Dict[str, Dict[str, float]]] = {}

    for origin, row in zip(origins, rows):
        elements = row.get("elements", [])
        origin_map = table.setdefault(origin, {})
        for destination, element in zip(destinations, elements):
            status = element.get("status")
            if status != "OK":
                origin_map[destination] = {"distance_km": None, "duration_minutes": None, "status": status}
                continue

            distance_m = element["distance"]["value"]
            duration_s = element["duration"]["value"]
            origin_map[destination] = {
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
    api_key = "AIzaSyAgZc7cr42xIdz72oVuSDdCt7YxC1Jx-o0"

    destinations = CITIES
    max_origins_per_request = max(1, min(len(CITIES), 100 // len(destinations)))
    if max_origins_per_request * len(destinations) > 100:
        max_origins_per_request = max(1, 100 // len(destinations))

    master_table: Dict[str, Dict[str, Dict[str, float]]] = {city: {} for city in CITIES}

    for origin_batch in chunked(CITIES, max_origins_per_request):
        payload = request_distance_matrix(api_key, origin_batch, destinations)
        partial = build_distance_table(origin_batch, destinations, payload)
        for origin, mapping in partial.items():
            master_table[origin].update(mapping)

    persist_results(master_table)


if __name__ == "__main__":
    main()
