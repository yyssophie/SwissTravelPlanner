"""Run legacy greedy planner followed by the current local search refinement."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Mapping, Optional

from planner_old import RoutePlanner as LegacyRoutePlanner, DayPlan as LegacyDayPlan
from route_planner import (
    RoutePlanner as CurrentRoutePlanner,
    DayPlan,
    _ScenarioContext,
)


def _convert(day: LegacyDayPlan) -> DayPlan:
    return DayPlan(
        day=day.day,
        distance_city=day.distance_city,
        poi_city=day.poi_city,
        display_city=day.display_city,
        travel_from=day.travel_from,
        travel_minutes=day.travel_minutes,
        pois=list(day.pois),
        note=day.note,
    )


class RoutePlanner:
    """Legacy greedy planner followed by the new local search optimiser."""

    def __init__(
        self,
        datastore,
        distance_path: Path = Path("data/out/google_city_distances.json"),
    ) -> None:
        self._legacy = LegacyRoutePlanner(datastore, distance_path=distance_path)
        self._optimiser = CurrentRoutePlanner(datastore, distance_path=distance_path)
        self._fallback = self._optimiser

    def plan_route(
        self,
        start_city: str,
        end_city: str,
        num_days: int,
        preference_weights: Mapping[str, float],
        season: Optional[str],
        mtu_per_day: int = 8,
    ):
        try:
            legacy_plan = self._legacy.plan_route(
                start_city=start_city,
                end_city=end_city,
                num_days=num_days,
                preference_weights=preference_weights,
                season=season,
            )
        except ValueError:
            return self._fallback.plan_route(
                start_city=start_city,
                end_city=end_city,
                num_days=num_days,
                preference_weights=preference_weights,
                season=season,
                mtu_per_day=mtu_per_day,
            )
        current_plan = [_convert(day) for day in legacy_plan]
        CurrentRoutePlanner._renumber_days(current_plan)  # type: ignore[attr-defined]

        target_distribution = self._optimiser._normalise_preferences(preference_weights)  # type: ignore[attr-defined]
        start_distance, _, _ = self._optimiser._resolve_city(start_city)  # type: ignore[attr-defined]
        end_distance, _, _ = self._optimiser._resolve_city(end_city)  # type: ignore[attr-defined]

        if num_days <= 7:
            arrival_buffer = 1
        elif num_days <= 15:
            arrival_buffer = 2
        else:
            arrival_buffer = 3
        earliest_arrival = max(1, num_days - arrival_buffer)

        scenario = _ScenarioContext(
            start_city=start_city,
            end_city=end_city,
            start_distance=start_distance,
            end_distance=end_distance,
            num_days=num_days,
            season=season,
            mtu_per_day=mtu_per_day,
            preferences=target_distribution,
            earliest_arrival_day=earliest_arrival,
        )

        refined = self._optimiser._run_local_search(current_plan, scenario)  # type: ignore[attr-defined]
        CurrentRoutePlanner._renumber_days(refined)  # type: ignore[attr-defined]
        return refined
