"""
Route planning logic for multi-day travel itineraries.
"""

from __future__ import annotations

import json
import os
import math
import random
import unicodedata
from dataclasses import dataclass
from heapq import heappop, heappush
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

if __package__ is None or __package__ == "":
    import sys

    CURRENT_DIR = Path(__file__).resolve().parent
    sys.path.append(str(CURRENT_DIR.parent))
    from data_store import CATEGORIES, POI, TravelDataStore  # type: ignore
    from poi_selection import has_preferred_pois, select_pois_for_day  # type: ignore
else:  # pragma: no cover
    from .data_store import CATEGORIES, POI, TravelDataStore
    from .poi_selection import has_preferred_pois, select_pois_for_day

DAILY_TRAVEL_LIMIT_MINUTES = 240.0
LONG_TRAVEL_THRESHOLD_MINUTES = 180.0

CITY_DISTANCE_TO_POI = {
    "Appenzell, Switzerland": "appenzell",
    "Bern, Switzerland": "bern",
    "Geneva, Switzerland": "geneva",
    "Interlaken, Switzerland": "interlaken",
    "Kandersteg, Switzerland": "kandersteg",
    "Lausanne, Switzerland": "lausanne",
    "Lucerne, Switzerland": "luzern",
    "Lugano, Switzerland": "lugano",
    "Montreux, Switzerland": "montreux",
    "Schwyz, Switzerland": "schwyz",
    "Sion, Switzerland": "sion",
    "St. Gallen, Switzerland": "st_gallen",
    "St. Moritz, Switzerland": "st_moritz",
    "Zermatt, Switzerland": "zermatt",
    "Zurich, Switzerland": "zurich",
}

EXTRA_CITY_ALIASES = {
    "lucerne": "Lucerne, Switzerland",
    "luzern": "Lucerne, Switzerland",
    "lausanne": "Lausanne, Switzerland",
    "kandersteg": "Kandersteg, Switzerland",
    "sion": "Sion, Switzerland",
    "st gallen": "St. Gallen, Switzerland",
    "st-gallen": "St. Gallen, Switzerland",
    "st. gallen": "St. Gallen, Switzerland",
    "st_gallen": "St. Gallen, Switzerland",
    "st gallen, switzerland": "St. Gallen, Switzerland",
    "st moritz": "St. Moritz, Switzerland",
    "st-moritz": "St. Moritz, Switzerland",
    "st. moritz": "St. Moritz, Switzerland",
    "st_moritz": "St. Moritz, Switzerland",
    "st moritz, switzerland": "St. Moritz, Switzerland",
    "zurich": "Zurich, Switzerland",
    "zuerich": "Zurich, Switzerland",
    "zürich": "Zurich, Switzerland",
}


@dataclass
class DayPlan:
    day: int
    distance_city: str
    poi_city: str
    display_city: str
    travel_from: Optional[str]
    travel_minutes: float
    pois: List[POI]
    note: Optional[str] = None


class RoutePlanner:
    """Plan multi-day routes while respecting travel limits and encouraging exploration."""

    def __init__(
        self,
        datastore: TravelDataStore,
        distance_path: Path = Path("data/out/google_city_distances.json"),
    ) -> None:
        self._datastore = datastore
        self._graph = self._load_distance_graph(distance_path)
        self._distance_cities = list(self._graph.keys())
        self._distance_to_poi = CITY_DISTANCE_TO_POI
        self._poi_to_distance = {
            poi_city: distance_city for distance_city, poi_city in self._distance_to_poi.items()
        }
        self._alias_to_distance = self._build_aliases()
        self._shortest_km = self._compute_shortest_paths(weight_key="distance_km")
        self._shortest_minutes = self._compute_shortest_paths(weight_key="duration_minutes")

    def plan_route(
        self,
        start_city: str,
        end_city: str,
        num_days: int,
        preference_weights: Mapping[str, float],
        season: Optional[str],
        rng: Optional[random.Random] = None,
    ) -> List[DayPlan]:
        if num_days <= 0:
            raise ValueError("Number of travel days must be positive.")

        rng = rng or random.Random()
        start_distance, start_poi_city, start_display = self._resolve_city(start_city)
        end_distance, end_poi_city, end_display = self._resolve_city(end_city)
        same_start_end = start_distance == end_distance

        if math.isinf(self._shortest_km[start_distance].get(end_distance, math.inf)):
            raise ValueError(f"No travel path between {start_display} and {end_display}.")

        if start_distance != end_distance and num_days < 2:
            raise ValueError("At least two days are required to travel between different cities.")

        min_days_to_end = {
            city: (
                math.inf
                if math.isinf(self._shortest_minutes[city].get(end_distance, math.inf))
                else math.ceil(self._shortest_minutes[city][end_distance] / DAILY_TRAVEL_LIMIT_MINUTES)
            )
            for city in self._distance_cities
        }
        # Determine required end-city stay days based on total trip length
        # - 7–14 days: at least 2 days in the end city (arrive by N-1)
        # - 15+ days: at least 3 days in the end city (arrive by N-2)
        # - otherwise: keep prior behavior (at least last day in end city)
        if same_start_end:
            # Loop trips: only require being at the end city on the last day
            required_end_stay_days = 1
        elif num_days >= 15:
            required_end_stay_days = 3
        elif num_days >= 7:
            required_end_stay_days = 2
        else:
            required_end_stay_days = 1

        # Feasibility: must be able to reach the end city with enough days left
        # to satisfy the required stay at the end.
        if min_days_to_end[start_distance] > max(0, num_days - required_end_stay_days):
            raise ValueError("Not enough days to reach the destination under the travel limit.")

        distance_to_end = {
            city: self._shortest_km[city].get(end_distance, math.inf) for city in self._distance_cities
        }

        available_pois = {
            poi_city: list(self._datastore.pois_for_city(poi_city, season))
            for poi_city in self._distance_to_poi.values()
        }

        target_stay_days = 1 if num_days <= 10 else min(2, max(1, math.ceil(num_days / 10)))

        visit_counts: Dict[str, int] = {}
        extra_stay_used = {city: False for city in self._distance_cities}
        visited_cities = set()

        current_distance_city = start_distance
        current_poi_city = start_poi_city
        previous_distance_city: Optional[str] = None
        travel_from_distance: Optional[str] = None
        travel_minutes_prev = 0.0

        day_plans: List[DayPlan] = []

        for day_index in range(1, num_days + 1):
            visit_counts[current_distance_city] = visit_counts.get(current_distance_city, 0) + 1
            visited_cities.add(current_distance_city)
            remaining_days = num_days - day_index

            travel_tu = _travel_time_units(travel_minutes_prev)
            pois = select_pois_for_day(
                available_pois[current_poi_city],
                preference_weights,
                travel_tu=travel_tu,
                rng=rng,
                season=season,
            )
            # Compute total daily TU (travel + activities)
            try:
                from .poi_selection import _activity_time_units as _tu_for
            except Exception:
                # Fallback if relative import path differs when run directly
                from poi_selection import _activity_time_units as _tu_for  # type: ignore
            activity_tu_sum = sum(_tu_for(p) for p in pois)
            total_daily_tu = travel_tu + activity_tu_sum

            debug = os.environ.get("PLANNER_DEBUG", "").lower() in {"1", "true", "yes", "on"}

            selected_ids = {poi.identifier for poi in pois}
            if selected_ids:
                available_pois[current_poi_city] = [
                    poi for poi in available_pois[current_poi_city] if poi.identifier not in selected_ids
                ]
            contains_sport = any(poi.has_label("sport") for poi in pois)

            day_plan = DayPlan(
                day=day_index,
                distance_city=current_distance_city,
                poi_city=current_poi_city,
                display_city=self._display_name(current_distance_city),
                travel_from=self._display_name(travel_from_distance) if travel_from_distance else None,
                travel_minutes=travel_minutes_prev,
                pois=pois,
            )

            note_parts: List[str] = []

            if day_index == num_days:
                if current_distance_city != end_distance:
                    raise ValueError("Itinerary did not reach the destination on the final day.")
                note_parts.append("final day at destination")
                day_plan.note = "; ".join(note_parts)
                day_plans.append(day_plan)
                break

            should_stay = False
            if current_distance_city == end_distance:
                # If start and end are the same, do not force staying at the beginning;
                # only ensure we are at the end city on the last day (handled by move logic).
                # Otherwise, once we reach the end city mid‑trip, stay until required end‑stay is satisfied.
                if same_start_end:
                    should_stay = False
                else:
                    current_visits = visit_counts.get(current_distance_city, 0)
                    should_stay = current_visits < required_end_stay_days
            else:
                stay_reasons: List[str] = []
                if remaining_days > 1:
                    event_reasons: List[str] = []
                    if not extra_stay_used[current_distance_city]:
                        if contains_sport:
                            event_reasons.append("sport-focused day")
                        if travel_from_distance and travel_minutes_prev >= LONG_TRAVEL_THRESHOLD_MINUTES:
                            event_reasons.append("long travel day")

                    target_stay = (
                        num_days > 10
                        and visit_counts[current_distance_city] < target_stay_days
                    )

                    if event_reasons:
                        stay_reasons.extend(event_reasons)
                        should_stay = True
                    elif target_stay:
                        stay_reasons.append(f"target stay {target_stay_days} days")
                        should_stay = True

                    if should_stay:
                        # Ensure staying here still leaves enough time to arrive at
                        # the end city with the required end stay days.
                        if min_days_to_end[current_distance_city] > max(0, (remaining_days - 1) - (required_end_stay_days - 1)):
                            should_stay = False
                            stay_reasons.clear()

                if should_stay and stay_reasons:
                    note_parts.extend(stay_reasons)
                    if "sport-focused day" in stay_reasons or "long travel day" in stay_reasons:
                        extra_stay_used[current_distance_city] = True

            if should_stay and not has_preferred_pois(
                available_pois[current_poi_city], preference_weights, season
            ):
                should_stay = False
                stay_reasons = []

            # New rule: if total TU for the day is strictly less than 6, move rather than stay.
            # Applies also to end city (unless it's the literal final day which is handled earlier).
            low_tu_force_move = total_daily_tu < 6 and remaining_days > 0
            if should_stay and low_tu_force_move:
                should_stay = False
                stay_reasons = []

            if debug:
                print(
                    f"[ROUTE] Day {day_index} city={self._display_name(current_distance_city)} travelTU={travel_tu} activityTU={activity_tu_sum} totalTU={total_daily_tu} stayCandidate={should_stay}"
                )

            if should_stay:
                day_plan.note = "; ".join(note_parts) if note_parts else None
                day_plans.append(day_plan)
                travel_from_distance = current_distance_city
                travel_minutes_prev = 0.0
                continue

            dest_info = self._choose_next_city(
                current_city=current_distance_city,
                previous_city=previous_distance_city,
                day_index=day_index,
                num_days=num_days,
                end_city=end_distance,
                remaining_days=remaining_days,
                visit_counts=visit_counts,
                min_days_to_end=min_days_to_end,
                distance_to_end=distance_to_end,
                visited_cities=visited_cities,
                available_pois=available_pois,
                preference_weights=preference_weights,
                season=season,
                rng=rng,
                required_end_stay_days=required_end_stay_days,
            )
            if dest_info is None:
                raise ValueError("Unable to find a feasible next city under the constraints.")

            next_city, travel_minutes = dest_info

            if low_tu_force_move:
                # Rebuild the current day as a move into the next city, consuming travel TU now
                # and selecting activities at the destination if possible.
                origin_city = current_distance_city
                dest_poi_city = self._distance_to_poi[next_city]

                # adjust visit counts to reflect that we didn't actually spend the day in origin
                visit_counts[origin_city] = max(0, visit_counts.get(origin_city, 1) - 1)
                visit_counts[next_city] = visit_counts.get(next_city, 0) + 1

                travel_tu_now = _travel_time_units(travel_minutes)
                dest_pois = select_pois_for_day(
                    available_pois[dest_poi_city],
                    preference_weights,
                    travel_tu=travel_tu_now,
                    rng=rng,
                    season=season,
                )
                try:
                    from .poi_selection import _activity_time_units as _tu_for
                except Exception:
                    from poi_selection import _activity_time_units as _tu_for  # type: ignore
                selected_ids_now = {poi.identifier for poi in dest_pois}
                if selected_ids_now:
                    available_pois[dest_poi_city] = [
                        poi for poi in available_pois[dest_poi_city] if poi.identifier not in selected_ids_now
                    ]
                note_parts.append("moved due to low TU")

                # Rewrite day_plan to represent the destination day with travel included
                day_plan.distance_city = next_city
                day_plan.poi_city = dest_poi_city
                day_plan.display_city = self._display_name(next_city)
                day_plan.travel_from = self._display_name(origin_city)
                day_plan.travel_minutes = travel_minutes
                day_plan.pois = dest_pois
                day_plan.note = "; ".join(note_parts) if note_parts else None
                day_plans.append(day_plan)

                # Prepare for next iteration: we already travelled today
                previous_distance_city = next_city
                travel_from_distance = next_city
                travel_minutes_prev = 0.0
                current_distance_city = next_city
                current_poi_city = dest_poi_city
            else:
                # Normal case: travel happens after today's activities
                day_plan.note = "; ".join(note_parts) if note_parts else None
                day_plans.append(day_plan)

                previous_distance_city = current_distance_city
                travel_from_distance = current_distance_city
                travel_minutes_prev = travel_minutes
                current_distance_city = next_city
                current_poi_city = self._distance_to_poi[current_distance_city]

        return day_plans

    def available_cities(self) -> List[str]:
        return sorted({self._display_name(city) for city in self._distance_cities})

    def is_known_city(self, name: str) -> bool:
        try:
            self._resolve_city(name)
        except ValueError:
            return False
        return True

    def display_for(self, name: str) -> str:
        _, _, display = self._resolve_city(name)
        return display

    # ------------------------------------------------------------------ helpers

    def _choose_next_city(
        self,
        current_city: str,
        previous_city: Optional[str],
        day_index: int,
        num_days: int,
        end_city: str,
        remaining_days: int,
        visit_counts: Mapping[str, int],
        min_days_to_end: Mapping[str, float],
        distance_to_end: Mapping[str, float],
        visited_cities: Iterable[str],
        available_pois: Mapping[str, List[POI]],
        preference_weights: Mapping[str, float],
        season: Optional[str],
        rng: random.Random,
        required_end_stay_days: int,
    ) -> Optional[Tuple[str, float]]:
        remaining_days_after_move = remaining_days - 1
        thresholds = [60.0, 120.0, 180.0, DAILY_TRAVEL_LIMIT_MINUTES]
        buckets: Dict[float, List[Tuple[Tuple[int, int, float, float], str, float]]] = {
            threshold: [] for threshold in thresholds
        }
        visited_set = set(visited_cities)

        for dest, payload in self._graph[current_city].items():
            if dest == current_city:
                continue
            duration = payload.get("duration_minutes")
            if duration is None or duration > DAILY_TRAVEL_LIMIT_MINUTES:
                continue

            if dest in visited_set and dest != end_city:
                continue

            dest_poi_city = self._distance_to_poi.get(dest)
            if not dest_poi_city or not has_preferred_pois(
                available_pois.get(dest_poi_city, []), preference_weights, season
            ):
                continue

            if dest == end_city:
                # Only move into the end city on the exact day that
                # ensures the required number of end-city stay days.
                end_arrival_move_day = num_days - required_end_stay_days
                if day_index != end_arrival_move_day:
                    continue
                # After moving, there should be (required_end_stay_days - 1) days remaining
                if remaining_days_after_move != max(0, required_end_stay_days - 1):
                    continue
            else:
                # For intermediate cities, ensure we can still reach the end city
                # with enough days left for the required end stay.
                moves_budget = remaining_days_after_move - max(0, required_end_stay_days - 1)
                if moves_budget < min_days_to_end.get(dest, math.inf):
                    continue

            dist_to_end_value = distance_to_end.get(dest, math.inf)
            if dest != end_city and math.isinf(dist_to_end_value):
                continue

            visits = visit_counts.get(dest, 0)
            backtrack_penalty = 1 if previous_city and dest == previous_city else 0
            if remaining_days_after_move > 3:
                dist_component = -dist_to_end_value
            else:
                dist_component = dist_to_end_value
            score = (visits, backtrack_penalty, dist_component, duration)

            for threshold in thresholds:
                if duration <= threshold:
                    buckets[threshold].append((score, dest, duration))
                    break

        for threshold in thresholds:
            bucket = buckets[threshold]
            if not bucket:
                continue
            bucket.sort()
            best_score = bucket[0][0]
            best = [candidate for candidate in bucket if candidate[0] == best_score]
            chosen_score, chosen_dest, chosen_duration = rng.choice(best)
            return chosen_dest, chosen_duration

        return None

    def _load_distance_graph(self, path: Path) -> Dict[str, Dict[str, Dict[str, float]]]:
        data = json.loads(path.read_text(encoding="utf-8"))
        graph: Dict[str, Dict[str, Dict[str, float]]] = {}
        for origin, destinations in data.get("distances", {}).items():
            graph[origin] = {}
            for dest, payload in destinations.items():
                graph[origin][dest] = {
                    "distance_km": float(payload.get("distance_km") or math.inf),
                    "duration_minutes": float(payload.get("duration_minutes") or math.inf),
                }
        return graph

    def _compute_shortest_paths(self, weight_key: str) -> Dict[str, Dict[str, float]]:
        result: Dict[str, Dict[str, float]] = {}
        for origin in self._distance_cities:
            result[origin] = self._dijkstra(origin, weight_key)
        return result

    def _dijkstra(self, origin: str, weight_key: str) -> Dict[str, float]:
        distances = {city: math.inf for city in self._distance_cities}
        distances[origin] = 0.0
        heap: List[Tuple[float, str]] = [(0.0, origin)]

        while heap:
            current_dist, city = heappop(heap)
            if current_dist > distances[city]:
                continue
            for neighbour, payload in self._graph[city].items():
                weight = payload.get(weight_key)
                if weight is None or math.isinf(weight):
                    continue
                new_dist = current_dist + weight
                if new_dist < distances[neighbour]:
                    distances[neighbour] = new_dist
                    heappush(heap, (new_dist, neighbour))
        return distances

    def _resolve_city(self, name: str) -> Tuple[str, str, str]:
        key = self._normalise_name(name)
        if key not in self._alias_to_distance:
            raise ValueError(f"Unknown city '{name}'.")
        distance_name = self._alias_to_distance[key]
        poi_city = self._distance_to_poi[distance_name]
        display_name = self._display_name(distance_name)
        return distance_name, poi_city, display_name

    def _display_name(self, distance_name: Optional[str]) -> str:
        if not distance_name:
            return ""
        return distance_name.split(",")[0]

    def _build_aliases(self) -> Dict[str, str]:
        aliases: Dict[str, str] = {}
        for distance_name, poi_city in self._distance_to_poi.items():
            for variant in (
                poi_city,
                distance_name,
                distance_name.replace(", Switzerland", ""),
            ):
                aliases[self._normalise_name(variant)] = distance_name
        for variant, distance_name in EXTRA_CITY_ALIASES.items():
            aliases[self._normalise_name(variant)] = distance_name
        return aliases

    def _normalise_name(self, value: str) -> str:
        normalised = unicodedata.normalize("NFKD", value or "")
        ascii_value = normalised.encode("ascii", "ignore").decode("ascii")
        return ascii_value.strip().lower()


def _travel_time_units(minutes: float) -> int:
    if minutes <= 0:
        return 0
    return max(1, math.ceil(minutes / 60.0))
