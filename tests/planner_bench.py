"""Scenario-based benchmark runner for route planners."""

from __future__ import annotations

import argparse
import importlib
import json
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping

from data_store import TravelDataStore
from evaluator import evaluate_itinerary


@dataclass
class Scenario:
    name: str
    start_city: str
    end_city: str
    num_days: int
    season: str
    mtu_per_day: int
    preferences: Mapping[str, float]


@dataclass
class ScenarioResult:
    name: str
    total_score: float
    components: Mapping[str, float]
    hard_violations: Iterable[str]
    runtime_seconds: float


def load_scenarios(path: Path) -> List[Scenario]:
    data = json.loads(path.read_text(encoding="utf-8"))
    scenarios: List[Scenario] = []
    for entry in data:
        scenarios.append(
            Scenario(
                name=entry["name"],
                start_city=entry["start_city"],
                end_city=entry["end_city"],
                num_days=int(entry["num_days"]),
                season=entry["season"],
                mtu_per_day=int(entry.get("mtu_per_day", 8)),
                preferences=entry["preferences"],
            )
        )
    return scenarios


def load_planner(module_name: str, class_name: str):
    module = importlib.import_module(module_name)
    try:
        planner_cls = getattr(module, class_name)
    except AttributeError as exc:  # pragma: no cover
        raise SystemExit(f"Planner class '{class_name}' not found in module '{module_name}'.") from exc
    return planner_cls


def run_scenario(planner_cls, datastore: TravelDataStore, scenario: Scenario) -> ScenarioResult:
    planner = planner_cls(datastore)
    start = scenario.start_city
    end = scenario.end_city
    t0 = time.perf_counter()
    day_plans = planner.plan_route(
        start_city=start,
        end_city=end,
        num_days=scenario.num_days,
        preference_weights=scenario.preferences,
        season=scenario.season,
        mtu_per_day=scenario.mtu_per_day,
    )
    elapsed = time.perf_counter() - t0

    score = evaluate_itinerary(
        day_plans=day_plans,
        start_city=start,
        end_city=end,
        interests=scenario.preferences,
        mtu=scenario.mtu_per_day,
        season=scenario.season,
    )

    return ScenarioResult(
        name=scenario.name,
        total_score=score.total,
        components=score.components,
        hard_violations=score.hard_violations,
        runtime_seconds=elapsed,
    )


def format_summary(results: List[ScenarioResult]) -> str:
    lines = ["Scenario                | Score (0-100)    | Runtime (s) | Violations"]
    lines.append("-" * len(lines[0]))
    for result in results:
        violations = ", ".join(result.hard_violations) if result.hard_violations else "-"
        lines.append(
            f"{result.name:<22}| {result.total_score:14.7f} | {result.runtime_seconds:11.3f} | {violations}"
        )
    return "\n".join(lines)


def save_results(results: List[ScenarioResult], output_path: Path) -> None:
    payload: List[Dict[str, Any]] = []
    for result in results:
        entry = asdict(result)
        entry["components"] = dict(result.components)
        entry["hard_violations"] = list(result.hard_violations)
        payload.append(entry)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark a route planner across predefined scenarios.")
    parser.add_argument(
        "--planner-module",
        required=True,
        help="Python module that defines the planner class (e.g. src.route_planner)",
    )
    parser.add_argument(
        "--planner-class",
        default="RoutePlanner",
        help="Planner class name inside the module (default: RoutePlanner)",
    )
    parser.add_argument(
        "--scenario-file",
        default="tests/data/planner_scenarios.json",
        help="Path to scenario JSON file",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Optional path to save detailed JSON results",
    )
    args = parser.parse_args()

    scenario_path = Path(args.scenario_file)
    scenarios = load_scenarios(scenario_path)
    planner_cls = load_planner(args.planner_module, args.planner_class)

    datastore = TravelDataStore.from_files()
    results: List[ScenarioResult] = []
    for scenario in scenarios:
        result = run_scenario(planner_cls, datastore, scenario)
        results.append(result)

    print(format_summary(results))

    if args.output:
        save_results(results, Path(args.output))
        print(f"\nDetailed results saved to {args.output}")


if __name__ == "__main__":
    main()
