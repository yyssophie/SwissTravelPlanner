"""Evaluate an LLM-generated itinerary JSON using the project scoring logic."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, List

from data_store import TravelDataStore
from route_planner import DayPlan
from evaluator import evaluate_itinerary


def load_itinerary_json(path: Path) -> List[Dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if "itinerary" not in data or not isinstance(data["itinerary"], list):
        raise ValueError("Input JSON must contain an 'itinerary' array.")
    return data["itinerary"]


def build_day_plans(itinerary: List[Dict], datastore: TravelDataStore) -> List[DayPlan]:
    day_plans: List[DayPlan] = []
    for entry in itinerary:
        pois = []
        for poi_entry in entry.get("pois", []):
            poi_id = poi_entry.get("identifier")
            if not poi_id:
                raise ValueError(f"POI entry missing 'identifier': {poi_entry}")
            poi = datastore.poi_by_id(poi_id)
            if poi is None:
                raise ValueError(f"Unknown POI identifier '{poi_id}'")
            pois.append(poi)

        distance_city = entry["distance_city"]
        display_city = distance_city.split(",")[0]
        day_plans.append(
            DayPlan(
                day=int(entry.get("day", len(day_plans) + 1)),
                distance_city=distance_city,
                poi_city=display_city.lower(),
                display_city=display_city,
                travel_from=entry.get("travel_from"),
                travel_minutes=float(entry.get("travel_minutes", 0.0)),
                pois=pois,
                note=entry.get("note"),
            )
        )
    return day_plans


def parse_preferences(raw: str) -> Dict[str, float]:
    prefs = json.loads(raw)
    if not isinstance(prefs, dict):
        raise ValueError("Preferences must be a JSON object mapping labels to floats.")
    return {str(k): float(v) for k, v in prefs.items()}


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate an LLM-generated itinerary JSON.")
    parser.add_argument("plan_file", type=Path, help="Path to the JSON file produced by the LLM")
    parser.add_argument("--start", required=True, help="Start city name")
    parser.add_argument("--end", required=True, help="End city name")
    parser.add_argument("--days", type=int, required=True, help="Number of trip days")
    parser.add_argument("--season", required=True, help="Season (spring/summer/autumn/winter)")
    parser.add_argument("--mtu", type=int, required=True, help="Maximum time units per day")
    parser.add_argument(
        "--preferences",
        required=True,
        help="Preference weights as JSON, e.g. '{\"nature\":0.4,\"culture\":0.3,\"food\":0.2,\"sport\":0.1}'",
    )
    args = parser.parse_args()

    itinerary_json = load_itinerary_json(args.plan_file)
    datastore = TravelDataStore.from_files()
    day_plans = build_day_plans(itinerary_json, datastore)
    preferences = parse_preferences(args.preferences)

    score = evaluate_itinerary(
        day_plans=day_plans,
        start_city=args.start,
        end_city=args.end,
        interests=preferences,
        mtu=args.mtu,
        season=args.season,
    )

    print(f"Total score: {score.total:.7f}")
    print("Components:")
    for name, value in score.components.items():
        print(f"  {name}: {value:.7f}")
    if score.hard_violations:
        print("Hard constraint violations detected:")
        for issue in score.hard_violations:
            print(f"  - {issue}")
    else:
        print("No hard constraint violations.")


if __name__ == "__main__":
    main()
