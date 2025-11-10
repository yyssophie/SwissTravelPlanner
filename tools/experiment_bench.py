"""
Experiment benchmark runner to compare three planners:
  1) Greedy only                -> src/route_planner_greedy.py:RoutePlanner
  2) Greedy + Local Search      -> src/route_planner_greedy_local.py:RoutePlanner
  3) Bidirectional + Local      -> src/route_planner.py:RoutePlanner

Runs a grid of scenarios and writes a CSV with total and per-component scores
plus runtime. All three planners receive the same RNG seed (for reproducible
random tie-breaks inside POI selection).

Usage:
  PYTHONPATH=src python tools/experiment_bench.py --output experiments/results.csv --seed 1337
"""

from __future__ import annotations

import argparse
import csv
import importlib
import time
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Tuple

from data_store import TravelDataStore
from evaluator import evaluate_itinerary


Algorithm = Tuple[int, str, str]  # (id, module, class)


ALGORITHMS: List[Algorithm] = [
    (1, "route_planner_greedy", "RoutePlanner"),
    (2, "route_planner_greedy_local", "RoutePlanner"),
    (3, "route_planner", "RoutePlanner"),
]


def load_planner(module_name: str, class_name: str):
    module = importlib.import_module(module_name)
    planner_cls = getattr(module, class_name)
    return planner_cls


def scenario_grid() -> Iterable[Dict[str, object]]:
    days_list = [4, 9, 15, 21]
    seasons = ["summer", "winter"]
    pairs = [
        ("Interlaken, Switzerland", "St. Moritz, Switzerland"),
        ("Zurich, Switzerland", "Zurich, Switzerland"),
        ("Geneva, Switzerland", "Lucerne, Switzerland"),
        ("St. Moritz, Switzerland", "St. Moritz, Switzerland"),
    ]
    mtus = [6, 10]
    pref_profiles: List[Tuple[str, Mapping[str, float]]] = [
        ("balanced", {"nature": 0.25, "culture": 0.25, "food": 0.25, "sport": 0.25}),
        ("nature_sport", {"nature": 0.4, "culture": 0.1, "food": 0.2, "sport": 0.3}),
        ("culture_food", {"nature": 0.1, "culture": 0.4, "food": 0.3, "sport": 0.2}),
    ]

    for d in days_list:
        for season in seasons:
            for (start_city, end_city) in pairs:
                for mtu in mtus:
                    for label, prefs in pref_profiles:
                        yield {
                            "days": d,
                            "season": season,
                            "start": start_city,
                            "end": end_city,
                            "mtu": mtu,
                            "pref_label": label,
                            "preferences": prefs,
                        }


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark three planners across a scenario grid and write CSV.")
    parser.add_argument("--output", required=True, help="Path to CSV output file")
    parser.add_argument("--seed", type=int, default=1337, help="RNG seed for all planners (default: 1337)")
    args = parser.parse_args()

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    datastore = TravelDataStore.from_files()

    # Prepare planners
    planners = []
    for alg_id, mod, cls in ALGORITHMS:
        planner_cls = load_planner(mod, cls)
        planners.append((alg_id, mod, cls, planner_cls(datastore)))

    fieldnames = [
        "algorithm_id",
        "algorithm",
        "start_city",
        "end_city",
        "days",
        "season",
        "mtu",
        "pref_label",
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

        for scenario in scenario_grid():
            start_city = scenario["start"]  # type: ignore[assignment]
            end_city = scenario["end"]  # type: ignore[assignment]
            days = int(scenario["days"])  # type: ignore[arg-type]
            season = str(scenario["season"])  # type: ignore[arg-type]
            mtu = int(scenario["mtu"])  # type: ignore[arg-type]
            pref_label = str(scenario["pref_label"])  # type: ignore[arg-type]
            prefs: Mapping[str, float] = scenario["preferences"]  # type: ignore[assignment]

            for alg_id, mod, cls, planner in planners:
                t0 = time.perf_counter()
                try:
                    itinerary = planner.plan_route(
                        start_city=start_city,
                        end_city=end_city,
                        num_days=days,
                        preference_weights=prefs,
                        season=season,
                        mtu_per_day=mtu,
                        seed=args.seed,
                    )
                except Exception as exc:  # pragma: no cover - record failure and continue
                    elapsed = time.perf_counter() - t0
                    writer.writerow(
                        {
                            "algorithm_id": alg_id,
                            "algorithm": f"{mod}:{cls}",
                            "start_city": start_city,
                            "end_city": end_city,
                            "days": days,
                            "season": season,
                            "mtu": mtu,
                            "pref_label": pref_label,
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
                    day_plans=itinerary,
                    start_city=start_city,
                    end_city=end_city,
                    interests=prefs,
                    mtu=mtu,
                    season=season,
                )

                components = score.components
                writer.writerow(
                    {
                        "algorithm_id": alg_id,
                        "algorithm": f"{mod}:{cls}",
                        "start_city": start_city,
                        "end_city": end_city,
                        "days": days,
                        "season": season,
                        "mtu": mtu,
                        "pref_label": pref_label,
                        "nature": prefs.get("nature", 0.0),
                        "culture": prefs.get("culture", 0.0),
                        "food": prefs.get("food", 0.0),
                        "sport": prefs.get("sport", 0.0),
                        "total_score": round(score.total, 7),
                        "interest_matching": round(components.get("interest_matching", 0.0), 7),
                        "tu_utilization": round(components.get("tu_utilization", 0.0), 7),
                        "city_visit_efficiency": round(components.get("city_visit_efficiency", 0.0), 7),
                        "geographic_coverage": round(components.get("geographic_coverage", 0.0), 7),
                        "long_travel_penalty": round(components.get("long_travel_penalty", 0.0), 7),
                        "travel_streak_smoothness": round(components.get("travel_streak_smoothness", 0.0), 7),
                        "stay_streak_smoothness": round(components.get("stay_streak_smoothness", 0.0), 7),
                        "runtime_seconds": round(elapsed, 6),
                        "violations": "; ".join(score.hard_violations) if score.hard_violations else "-",
                    }
                )

    print(f"Wrote CSV to {out_path}")


if __name__ == "__main__":
    main()
