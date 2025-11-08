"""Wrapper to expose the legacy greedy planner with the current interface."""

from __future__ import annotations

from pathlib import Path
from typing import Mapping, Optional

from planner_old import RoutePlanner as LegacyRoutePlanner, DayPlan as LegacyDayPlan
from route_planner import DayPlan, RoutePlanner as CurrentRoutePlanner


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
    """Legacy greedy planner wrapped to match the modern interface."""

    def __init__(
        self,
        datastore,
        distance_path: Path = Path("data/out/google_city_distances.json"),
    ) -> None:
        self._legacy = LegacyRoutePlanner(datastore, distance_path=distance_path)
        self._fallback = CurrentRoutePlanner(datastore, distance_path=distance_path)

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
            # Legacy planner could not find a feasible route; fall back to the current planner
            return self._fallback.plan_route(
                start_city=start_city,
                end_city=end_city,
                num_days=num_days,
                preference_weights=preference_weights,
                season=season,
                mtu_per_day=mtu_per_day,
            )
        converted = [_convert(day) for day in legacy_plan]
        CurrentRoutePlanner._renumber_days(converted)  # type: ignore[attr-defined]
        return converted
