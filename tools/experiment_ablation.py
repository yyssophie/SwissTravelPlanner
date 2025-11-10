"""
Run ablation experiments for local-search transitions in route_planner_ablation.

For each single enabled transition (labels 1..4), evaluate a 24-scenario grid and
record base (best of forward/backward greedy), final (after LS), and gain.

Usage:
  PYTHONPATH=src python tools/experiment_ablation.py --output experiments/ablation_results.csv --seed 1337
"""

from __future__ import annotations

import argparse
import csv
import time
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Tuple

from data_store import TravelDataStore
from evaluator import evaluate_itinerary
from route_planner_ablation import RoutePlanner, TRANSITION_LABELS


def scenario_grid() -> Iterable[Dict[str, object]]:
    days_list = [4, 9, 15, 21]
    seasons = ["summer", "winter"]
    pairs = [
        ("Interlaken, Switzerland", "St. Moritz, Switzerland"),
        ("Zurich, Switzerland", "Zurich, Switzerland"),
        ("Geneva, Switzerland", "Lucerne, Switzerland"),
    ]
    mtu = 8
    prefs = {"nature": 0.25, "culture": 0.25, "food": 0.25, "sport": 0.25}

    for d in days_list:
        for season in seasons:
            for (start_city, end_city) in pairs:
                yield {
                    "days": d,
                    "season": season,
                    "start": start_city,
                    "end": end_city,
                    "mtu": mtu,
                    "pref_label": "balanced",
                    "preferences": prefs,
                }


def main() -> None:
    parser = argparse.ArgumentParser(description="Ablation experiment for local-search transitions.")
    parser.add_argument("--output", required=True, help="Path to CSV output file")
    parser.add_argument("--seed", type=int, default=1337, help="RNG seed (default: 1337)")
    args = parser.parse_args()

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    datastore = TravelDataStore.from_files()

    fieldnames = [
        "transition_label",
        "transition_name",
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
        "base_score",
        "final_score",
        "gain",
        "runtime_seconds",
        "violations",
    ]

    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for label in sorted(TRANSITION_LABELS.keys()):
            name = TRANSITION_LABELS[label]
            planner = RoutePlanner(datastore, allowed_transitions=[label])

            for scenario in scenario_grid():
                start_city = scenario["start"]  # type: ignore[assignment]
                end_city = scenario["end"]  # type: ignore[assignment]
                days = int(scenario["days"])  # type: ignore[arg-type]
                season = str(scenario["season"])  # type: ignore[arg-type]
                mtu = int(scenario["mtu"])  # type: ignore[arg-type]
                pref_label = str(scenario["pref_label"])  # type: ignore[arg-type]
                prefs: Mapping[str, float] = scenario["preferences"]  # type: ignore[assignment]

                t0 = time.perf_counter()
                try:
                    plan = planner.plan_route(
                        start_city=start_city,
                        end_city=end_city,
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
                            "transition_label": label,
                            "transition_name": name,
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
                            "base_score": 0.0,
                            "final_score": 0.0,
                            "gain": 0.0,
                            "runtime_seconds": round(elapsed, 6),
                            "violations": f"planner_error: {exc}",
                        }
                    )
                    continue

                elapsed = time.perf_counter() - t0
                eval_result = evaluate_itinerary(
                    day_plans=plan,
                    start_city=start_city,
                    end_city=end_city,
                    interests=prefs,
                    mtu=mtu,
                    season=season,
                )

                base_score = planner.last_base_score if planner.last_base_score is not None else 0.0
                final_score = eval_result.total if not eval_result.hard_violations else 0.0
                gain = planner.last_gain if planner.last_gain is not None else (final_score - base_score)

                writer.writerow(
                    {
                        "transition_label": label,
                        "transition_name": name,
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
                        "base_score": round(base_score, 7),
                        "final_score": round(final_score, 7),
                        "gain": round(gain, 7),
                        "runtime_seconds": round(elapsed, 6),
                        "violations": "; ".join(eval_result.hard_violations) if eval_result.hard_violations else "-",
                    }
                )

    print(f"Wrote ablation CSV to {out_path}")


if __name__ == "__main__":
    main()
