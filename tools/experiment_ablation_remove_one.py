"""
Remove-one ablation: for each transition, disable it and keep the other three.

Runs the same 24-scenario grid as the single-operator experiment and records
base (best greedy before local search), final (after LS), and gain.

Usage:
  PYTHONPATH=src python tools/experiment_ablation_remove_one.py --output experiments/ablation_remove_one_results.csv --seed 1337
"""

from __future__ import annotations

import argparse
import csv
import time
from pathlib import Path
from typing import Dict, Iterable, List, Mapping

from data_store import TravelDataStore
from evaluator import evaluate_itinerary
from route_planner_ablation import RoutePlanner, TRANSITION_LABELS


PREF_OPTIONS = {
    "balanced": {"nature": 0.25, "culture": 0.25, "food": 0.25, "sport": 0.25},
    "nature_food": {"nature": 0.4, "culture": 0.2, "food": 0.3, "sport": 0.3},
    "culture_food": {"nature": 0.1, "culture": 0.4, "food": 0.3, "sport": 0.2},
}


def scenario_grid() -> Iterable[Dict[str, object]]:
    days_list = [4, 9, 15, 21]
    seasons = ["summer", "winter"]
    pairs = [
        ("Interlaken, Switzerland", "St. Moritz, Switzerland"),
        ("Zurich, Switzerland", "Zurich, Switzerland"),
        ("Geneva, Switzerland", "Lucerne, Switzerland"),
    ]
    mtus = [6, 10]

    for d in days_list:
        for season in seasons:
            for (start_city, end_city) in pairs:
                for mtu in mtus:
                    for label, prefs in PREF_OPTIONS.items():
                        yield {
                            "days": d,
                            "season": season,
                            "start": start_city,
                            "end": end_city,
                            "mtu": mtu,
                            "pref_label": label,
                            "preferences": prefs,
                        }


def _scenario_key(start: str, end: str, days: int, season: str, mtu: int, pref_label: str) -> str:
    return f"{start}|{end}|{days}|{season}|{mtu}|{pref_label}"


def main() -> None:
    parser = argparse.ArgumentParser(description="Remove-one ablation for local-search transitions.")
    parser.add_argument("--output", required=True, help="Path to CSV output file")
    parser.add_argument("--seed", type=int, default=1337, help="RNG seed (default: 1337)")
    args = parser.parse_args()

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    datastore = TravelDataStore.from_files()

    component_cols = [
        "interest_matching",
        "tu_utilization",
        "city_visit_efficiency",
        "geographic_coverage",
        "long_travel_penalty",
        "travel_streak_smoothness",
        "stay_streak_smoothness",
    ]

    fieldnames = [
        "removed_label",
        "removed_name",
        "kept_labels",
        "kept_names",
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
        "baseline_final_score",
        "delta_vs_baseline",
    ]
    for col in component_cols:
        fieldnames.extend(
            [
                f"{col}_base",
                f"{col}_final",
                f"{col}_gain",
                f"{col}_baseline_final",
                f"{col}_delta_vs_baseline",
            ]
        )
    fieldnames.extend(["runtime_seconds", "violations"])

    # Precompute baseline local-search results (all transitions enabled)
    scenarios = list(scenario_grid())

    baseline_planner = RoutePlanner(datastore)
    baseline_metrics: Dict[str, Dict[str, object]] = {}

    for scenario in scenarios:
        start_city = scenario["start"]  # type: ignore[assignment]
        end_city = scenario["end"]  # type: ignore[assignment]
        days = int(scenario["days"])  # type: ignore[arg-type]
        season = str(scenario["season"])  # type: ignore[arg-type]
        mtu = int(scenario["mtu"])  # type: ignore[arg-type]
        pref_label = str(scenario["pref_label"])  # type: ignore[arg-type]
        prefs: Mapping[str, float] = scenario["preferences"]  # type: ignore[assignment]

        key = _scenario_key(start_city, end_city, days, season, mtu, pref_label)
        plan = baseline_planner.plan_route(
            start_city=start_city,
            end_city=end_city,
            num_days=days,
            preference_weights=prefs,
            season=season,
            mtu_per_day=mtu,
            seed=args.seed,
        )
        eval_result = evaluate_itinerary(
            day_plans=plan,
            start_city=start_city,
            end_city=end_city,
            interests=prefs,
            mtu=mtu,
            season=season,
        )
        baseline_metrics[key] = {
            "score": eval_result.total if not eval_result.hard_violations else 0.0,
            "components": dict(eval_result.components) if not eval_result.hard_violations else {},
        }

    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        all_labels = sorted(TRANSITION_LABELS.keys())
        for removed in all_labels:
            kept = [lab for lab in all_labels if lab != removed]
            removed_name = TRANSITION_LABELS[removed]
            kept_names = [TRANSITION_LABELS[k] for k in kept]

            planner = RoutePlanner(datastore, allowed_transitions=kept)

            for scenario in scenarios:
                start_city = scenario["start"]  # type: ignore[assignment]
                end_city = scenario["end"]  # type: ignore[assignment]
                days = int(scenario["days"])  # type: ignore[arg-type]
                season = str(scenario["season"])  # type: ignore[arg-type]
                mtu = int(scenario["mtu"])  # type: ignore[arg-type]
                pref_label = str(scenario["pref_label"])  # type: ignore[arg-type]
                prefs: Mapping[str, float] = scenario["preferences"]  # type: ignore[assignment]
                key = _scenario_key(start_city, end_city, days, season, mtu, pref_label)
                baseline_info = baseline_metrics.get(key, {"score": 0.0, "components": {}})
                baseline_final = float(baseline_info.get("score", 0.0))
                baseline_comp = baseline_info.get("components", {})

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
                    empty_components = {}
                    for col in component_cols:
                        empty_components[f"{col}_base"] = 0.0
                        empty_components[f"{col}_final"] = 0.0
                        empty_components[f"{col}_gain"] = 0.0
                        empty_components[f"{col}_baseline_final"] = float(
                            baseline_comp.get(col, 0.0)
                        )
                        empty_components[f"{col}_delta_vs_baseline"] = -float(
                            baseline_comp.get(col, 0.0)
                        )

                    writer.writerow(
                        {
                            "removed_label": removed,
                            "removed_name": removed_name,
                            "kept_labels": "|".join(map(str, kept)),
                            "kept_names": ",".join(kept_names),
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
                            "baseline_final_score": round(baseline_final, 7),
                            "delta_vs_baseline": round(-baseline_final, 7),
                            **empty_components,
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
                delta = final_score - baseline_final

                base_components = getattr(planner, "last_base_components", {}) or {}
                final_components = eval_result.components if not eval_result.hard_violations else {}
                component_data = {}
                for col in component_cols:
                    base_val = float(base_components.get(col, 0.0))
                    final_val = float(final_components.get(col, 0.0))
                    baseline_val = float(baseline_comp.get(col, 0.0))
                    component_data[f"{col}_base"] = round(base_val, 7)
                    component_data[f"{col}_final"] = round(final_val, 7)
                    component_data[f"{col}_gain"] = round(final_val - base_val, 7)
                    component_data[f"{col}_baseline_final"] = round(baseline_val, 7)
                    component_data[f"{col}_delta_vs_baseline"] = round(final_val - baseline_val, 7)

                writer.writerow(
                    {
                        "removed_label": removed,
                        "removed_name": removed_name,
                        "kept_labels": "|".join(map(str, kept)),
                        "kept_names": ",".join(kept_names),
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
                        "baseline_final_score": round(baseline_final, 7),
                        "delta_vs_baseline": round(delta, 7),
                        **component_data,
                        "runtime_seconds": round(elapsed, 6),
                        "violations": "; ".join(eval_result.hard_violations) if eval_result.hard_violations else "-",
                    }
                )

    print(f"Wrote remove-one ablation CSV to {out_path}")


if __name__ == "__main__":
    main()
