"""
Run four predefined scenarios with the main RoutePlanner and report scores.

Usage:
  PYTHONPATH=src python tools/experiment_four_trips.py --output experiments/four_trips_results.csv --seed 1337
"""

from __future__ import annotations

import argparse
import csv
import time
from pathlib import Path
from typing import Dict, Iterable, List, Mapping

from data_store import TravelDataStore
from evaluator import evaluate_itinerary
from route_planner import RoutePlanner


def scenarios() -> Iterable[Dict[str, object]]:
    return [
        {
            "label": "Zurich-Zurich Culture tour",
            "start": "Zurich, Switzerland",
            "end": "Zurich, Switzerland",
            "days": 7,
            "season": "summer",
            "mtu": 8,
            "preferences": {"nature": 0.2, "culture": 0.4, "food": 0.3, "sport": 0.1},
        },
        {
            "label": "Long winter sports tour",
            "start": "St. Moritz, Switzerland",
            "end": "Zermatt, Switzerland",
            "days": 21,
            "season": "winter",
            "mtu": 9,
            "preferences": {"nature": 0.3, "culture": 0.1, "food": 0.2, "sport": 0.4},
        },
        {
            "label": "2-week nature tour",
            "start": "Zurich, Switzerland",
            "end": "Lugano, Switzerland",
            "days": 15,
            "season": "summer",
            "mtu": 10,
            "preferences": {"nature": 0.4, "culture": 0.2, "food": 0.1, "sport": 0.3},
        },
        {
            "label": "Central winter food tour",
            "start": "Geneva, Switzerland",
            "end": "Interlaken, Switzerland",
            "days": 9,
            "season": "winter",
            "mtu": 7,
            "preferences": {"nature": 0.3, "culture": 0.2, "food": 0.4, "sport": 0.1},
        },
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate four predefined trips with RoutePlanner.")
    parser.add_argument("--output", default="experiments/four_trips_results.csv", help="Path to CSV output file")
    parser.add_argument("--seed", type=int, default=1337, help="RNG seed (default: 1337)")
    args = parser.parse_args()

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    datastore = TravelDataStore.from_files()
    planner = RoutePlanner(datastore)

    fieldnames = [
        "label",
        "start_city",
        "end_city",
        "days",
        "season",
        "mtu",
        "nature",
        "culture",
        "food",
        "sport",
        "total_score",
        "interest_matching",
        "tu_utilization",
        "city_visit_efficiency",
        "geographic_coverage",
        "long_travel_penalty",
        "travel_streak_smoothness",
        "stay_streak_smoothness",
        "runtime_seconds",
        "violations",
    ]

    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for sc in scenarios():
            start = sc["start"]  # type: ignore[assignment]
            end = sc["end"]  # type: ignore[assignment]
            days = int(sc["days"])  # type: ignore[arg-type]
            season = str(sc["season"])  # type: ignore[arg-type]
            mtu = int(sc["mtu"])  # type: ignore[arg-type]
            prefs: Mapping[str, float] = sc["preferences"]  # type: ignore[assignment]

            t0 = time.perf_counter()
            try:
                plan = planner.plan_route(
                    start_city=start,
                    end_city=end,
                    num_days=days,
                    preference_weights=prefs,
                    season=season,
                    mtu_per_day=mtu,
                    seed=args.seed,
                )
            except Exception as exc:
                elapsed = time.perf_counter() - t0
                writer.writerow(
                    {
                        "label": sc["label"],
                        "start_city": start,
                        "end_city": end,
                        "days": days,
                        "season": season,
                        "mtu": mtu,
                        "nature": prefs.get("nature", 0.0),
                        "culture": prefs.get("culture", 0.0),
                        "food": prefs.get("food", 0.0),
                        "sport": prefs.get("sport", 0.0),
                        "total_score": 0.0,
                        "interest_matching": 0.0,
                        "tu_utilization": 0.0,
                        "city_visit_efficiency": 0.0,
                        "geographic_coverage": 0.0,
                        "long_travel_penalty": 0.0,
                        "travel_streak_smoothness": 0.0,
                        "stay_streak_smoothness": 0.0,
                        "runtime_seconds": round(elapsed, 6),
                        "violations": f"planner_error: {exc}",
                    }
                )
                continue

            elapsed = time.perf_counter() - t0
            score = evaluate_itinerary(
                day_plans=plan,
                start_city=start,
                end_city=end,
                interests=prefs,
                mtu=mtu,
                season=season,
            )

            comps = score.components
            writer.writerow(
                {
                    "label": sc["label"],
                    "start_city": start,
                    "end_city": end,
                    "days": days,
                    "season": season,
                    "mtu": mtu,
                    "nature": prefs.get("nature", 0.0),
                    "culture": prefs.get("culture", 0.0),
                    "food": prefs.get("food", 0.0),
                    "sport": prefs.get("sport", 0.0),
                    "total_score": round(score.total, 7),
                    "interest_matching": round(comps.get("interest_matching", 0.0), 7),
                    "tu_utilization": round(comps.get("tu_utilization", 0.0), 7),
                    "city_visit_efficiency": round(comps.get("city_visit_efficiency", 0.0), 7),
                    "geographic_coverage": round(comps.get("geographic_coverage", 0.0), 7),
                    "long_travel_penalty": round(comps.get("long_travel_penalty", 0.0), 7),
                    "travel_streak_smoothness": round(comps.get("travel_streak_smoothness", 0.0), 7),
                    "stay_streak_smoothness": round(comps.get("stay_streak_smoothness", 0.0), 7),
                    "runtime_seconds": round(elapsed, 6),
                    "violations": "; ".join(score.hard_violations) if score.hard_violations else "-",
                }
            )

    print(f"Wrote results to {out_path}")


if __name__ == "__main__":
    main()

