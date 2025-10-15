"""
Simple command-line launcher for testing the POI selection logic.
"""

from __future__ import annotations

import random
import sys
from pathlib import Path
from typing import Dict

if __package__ is None or __package__ == "":
    # Allow running via `python src/run_planner.py`
    CURRENT_DIR = Path(__file__).resolve().parent
    sys.path.append(str(CURRENT_DIR.parent))
    from data_store import CATEGORIES, TravelDataStore  # type: ignore
    from poi_selection import select_pois_for_cities  # type: ignore
else:
    from .data_store import CATEGORIES, TravelDataStore
    from .poi_selection import select_pois_for_cities


def prompt_cities(datastore: TravelDataStore) -> list[str]:
    valid_cities = datastore.cities()
    valid_lookup = {city.lower(): city for city in valid_cities}
    print("Available cities:", ", ".join(valid_cities))

    while True:
        raw = input("Enter the cities to visit (comma separated, e.g., zurich, bern): ").strip()
        if not raw:
            print("No cities provided. Please try again.", file=sys.stderr)
            continue

        requested = [city.strip() for city in raw.split(",") if city.strip()]
        if not requested:
            print("No valid city names found. Please try again.", file=sys.stderr)
            continue

        normalised = []
        invalid = []
        for city in requested:
            key = city.lower()
            if key in valid_lookup:
                normalised.append(valid_lookup[key])
            else:
                invalid.append(city)

        if invalid:
            print(
                f"Unrecognised city names: {', '.join(invalid)}. "
                "Please choose from the available list.",
                file=sys.stderr,
            )
            continue

        # Remove duplicates while preserving order.
        seen = set()
        ordered_unique = []
        for city in normalised:
            if city not in seen:
                seen.add(city)
                ordered_unique.append(city)

        return ordered_unique


def prompt_preferences() -> Dict[str, float]:
    print("Enter preference weights for the five categories so they sum to 1.")
    print("Order:", ", ".join(CATEGORIES))
    raw = input("Provide five numbers separated by commas (e.g., 0.3,0.2,0.2,0.2,0.1): ").strip()
    parts = [part.strip() for part in raw.split(",") if part.strip()]
    if len(parts) != len(CATEGORIES):
        print(f"Expected {len(CATEGORIES)} values.", file=sys.stderr)
        sys.exit(1)
    try:
        weights = [float(x) for x in parts]
    except ValueError:
        print("All weights must be numeric.", file=sys.stderr)
        sys.exit(1)
    total = sum(weights)
    if total <= 0:
        print("Sum of weights must be positive.", file=sys.stderr)
        sys.exit(1)
    if abs(total - 1.0) > 1e-6:
        print("Weights did not sum to 1. Normalising them.", file=sys.stderr)
    weights = [w / total for w in weights]
    return dict(zip(CATEGORIES, weights))


def prompt_season(datastore: TravelDataStore) -> str:
    seasons = datastore.seasons()
    print("Available seasons:", ", ".join(seasons))
    while True:
        raw = input("Enter desired season (spring/summer/autumn/winter): ").strip()
        try:
            season = datastore.normalize_season(raw)
        except ValueError:
            print("Invalid season. Please choose from the listed options.", file=sys.stderr)
            continue
        if season not in seasons:
            print(f"Season '{raw}' has no matching POIs in the dataset; please choose again.", file=sys.stderr)
            continue
        return season


def main() -> None:
    datastore = TravelDataStore.from_files()
    cities = prompt_cities(datastore)
    preferences = prompt_preferences()
    season = prompt_season(datastore)

    rng = random.Random()
    itinerary = select_pois_for_cities(datastore, cities, preferences, rng, season=season)

    print("\nSuggested POIs:")
    separator = "=" * 60
    for city, pois in itinerary.items():
        print(separator)
        print(f"City: {city}")
        print(separator)
        if not pois:
            print("  (No matching POIs found)\n")
            continue
        for poi in pois:
            categories = [cat for cat in CATEGORIES if poi.has_label(cat)]
            categories_text = ", ".join(categories) if categories else "no label matches"
            print(f"  • {poi.name} ({categories_text})")
            if poi.abstract:
                print(f"    Abstract: {poi.abstract}")
            if poi.description:
                print(f"    Description: {poi.description}")
            if poi.seasons:
                seasons_text = ", ".join(poi.seasons)
                print(f"    Seasons: {seasons_text}")
            if poi.season_reason:
                print(f"    Season reason: {poi.season_reason}")
            print()


if __name__ == "__main__":
    main()
