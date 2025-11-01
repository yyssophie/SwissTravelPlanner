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
    from route_planner import DayPlan, RoutePlanner  # type: ignore
    from evaluator import evaluate_itinerary  # type: ignore
else:
    from .data_store import CATEGORIES, TravelDataStore
    from .route_planner import DayPlan, RoutePlanner
    from .evaluator import evaluate_itinerary


def prompt_preferences() -> Dict[str, float]:
    print("Enter preference weights for the four categories so they sum to 1.")
    print("Order:", ", ".join(CATEGORIES))
    raw = input("Provide four numbers separated by commas (e.g., 0.4,0.3,0.2,0.1): ").strip()
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


def prompt_city(planner: RoutePlanner, label: str) -> str:
    options = ", ".join(planner.available_cities())
    print(f"Available cities: {options}")
    while True:
        raw = input(f"{label}: ").strip()
        if not planner.is_known_city(raw):
            print("Unknown city. Please choose from the available options.", file=sys.stderr)
            continue
        display = planner.display_for(raw)
        return display


def prompt_days() -> int:
    while True:
        raw = input("Number of travel days: ").strip()
        try:
            value = int(raw)
        except ValueError:
            print("Please enter a valid integer.", file=sys.stderr)
            continue
        if value <= 0:
            print("Number of days must be positive.", file=sys.stderr)
            continue
        return value


def prompt_mtu() -> int:
    while True:
        raw = input("Maximum time units per day (4–10 hours): ").strip()
        try:
            mtu = int(raw)
        except ValueError:
            print("Please enter an integer between 4 and 10.", file=sys.stderr)
            continue
        if mtu < 4 or mtu > 10:
            print("MTU must be between 4 and 10.", file=sys.stderr)
            continue
        return mtu


def print_itinerary(itinerary: list[DayPlan]) -> None:
    print("\nSuggested itinerary:")
    for day in itinerary:
        print("=" * 60)
        header = f"Day {day.day}: {day.display_city}"
        if day.travel_from:
            header += f" (travelled from {day.travel_from}, {day.travel_minutes:.0f} min)"
        else:
            header += " (trip start)"
        print(header)
        if day.note:
            print(f"  Note: {day.note}")
        for poi in day.pois:
            categories = [cat for cat in CATEGORIES if poi.has_label(cat)]
            category_text = ", ".join(categories) if categories else "no categories"
            print(f"  • {poi.name} [{category_text}]")
            if poi.abstract:
                print(f"      Abstract: {poi.abstract}")
            if poi.description:
                print(f"      Description: {poi.description}")
            if getattr(poi, "seasons", None):
                seasons_text = ", ".join(poi.seasons)
                print(f"      Seasons: {seasons_text}")
        print()


def main() -> None:
    datastore = TravelDataStore.from_files()
    planner = RoutePlanner(datastore)
    start_city = prompt_city(planner, "Enter start city")
    end_city = prompt_city(planner, "Enter end city")
    num_days = prompt_days()
    preferences = prompt_preferences()
    season = prompt_season(datastore)
    mtu = prompt_mtu()

    rng = random.Random()
    try:
        itinerary = planner.plan_route(
            start_city=start_city,
            end_city=end_city,
            num_days=num_days,
            preference_weights=preferences,
            season=season,
            rng=rng,
        )
    except ValueError as exc:
        print(f"Could not build itinerary: {exc}", file=sys.stderr)
        sys.exit(1)

    print_itinerary(itinerary)

    # Evaluate itinerary according to the scoring rules
    score = evaluate_itinerary(
        day_plans=itinerary,
        start_city=start_city,
        end_city=end_city,
        interests=preferences,
        mtu=mtu,
        season=season,
    )

    print("\nEvaluation Results")
    print(f"Total score: {score.total:.2f}/100")
    for name, value in score.components.items():
        print(f"  {name}: {value:.3f}")
    if score.hard_violations:
        print("Hard constraint violations detected:")
        for issue in score.hard_violations:
            print(f"  - {issue}")


if __name__ == "__main__":
    main()
