"""Greedy route planner tuned for the new itinerary score system."""

from __future__ import annotations

import json
import math
import unicodedata
from dataclasses import dataclass
from heapq import heappop, heappush
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

if __package__ is None or __package__ == "":  # pragma: no cover
    import sys

    CURRENT_DIR = Path(__file__).resolve().parent
    sys.path.append(str(CURRENT_DIR.parent))
    from data_store import CATEGORIES, POI, TravelDataStore  # type: ignore
    from poi_selection import (  # type: ignore
        _activity_time_units,
        _is_in_season,
        _primary_label,
    )
else:  # pragma: no cover
    from .data_store import CATEGORIES, POI, TravelDataStore
    from .poi_selection import _activity_time_units, _is_in_season, _primary_label


LONG_TRAVEL_COMFORT_MINUTES = 120.0

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
    """Greedy planner aligned with the new evaluation metrics."""

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
        self._shortest_minutes = self._compute_shortest_paths()

    # ------------------------------------------------------------------ public API

    def plan_route(
        self,
        start_city: str,
        end_city: str,
        num_days: int,
        preference_weights: Mapping[str, float],
        season: Optional[str],
        mtu_per_day: int = 8,
    ) -> List[DayPlan]:
        if num_days < 3:
            raise ValueError("Number of travel days must be at least three.")
        if mtu_per_day < 4 or mtu_per_day > 10:
            raise ValueError("Maximum hours per day must be between 4 and 10.")

        start_distance, start_poi_city, start_display = self._resolve_city(start_city)
        end_distance, end_poi_city, end_display = self._resolve_city(end_city)

        if math.isinf(self._shortest_minutes[start_distance].get(end_distance, math.inf)):
            raise ValueError(f"No travel path between {start_display} and {end_display}.")

        target_distribution = self._normalise_preferences(preference_weights)

        if num_days <= 7:
            arrival_buffer = 1
        elif num_days <= 15:
            arrival_buffer = 2
        else:
            arrival_buffer = 3
        earliest_arrival_day = max(1, num_days - arrival_buffer)

        available_pois: Dict[str, List[POI]] = {}
        for poi_city in self._distance_to_poi.values():
            all_pois = list(self._datastore.pois_for_city(poi_city, season))
            filtered = [poi for poi in all_pois if season is None or _is_in_season(poi, season)]
            available_pois[poi_city] = filtered

        label_counts = {category: 0 for category in CATEGORIES}
        total_pois = 0
        interest_score = self._interest_score(label_counts, total_pois, target_distribution)

        visited_set = {start_distance}
        unique_city_count = 1
        city_score = self._city_efficiency(unique_city_count, num_days)

        coverage_sum = 0.0
        coverage_count = 0
        coverage_score = 0.0

        start_distances = self._shortest_minutes[start_distance]
        max_distance = max(
            (value for value in start_distances.values() if not math.isinf(value)),
            default=1.0,
        )

        day_plans: List[DayPlan] = []
        current_city = start_distance

        travel_streak = 0
        stay_streak = 0
        end_city_reached = False

        for day_index in range(1, num_days + 1):
            remaining_days = num_days - day_index

            candidates = self._enumerate_candidates(
                current_city=current_city,
                end_city=end_distance,
                day_index=day_index,
                num_days=num_days,
                visited_set=visited_set,
                earliest_arrival_day=earliest_arrival_day,
                end_city_reached=end_city_reached,
            )

            best_choice = None
            best_score_gain = -math.inf

            for action in candidates:
                simulation = self._simulate_day(
                    action=action,
                    day_index=day_index,
                    mtu_per_day=mtu_per_day,
                    target_distribution=target_distribution,
                    label_counts=label_counts,
                    total_pois=total_pois,
                    interest_score=interest_score,
                    city_score=city_score,
                    coverage_sum=coverage_sum,
                    coverage_count=coverage_count,
                    coverage_score=coverage_score,
                    unique_city_count=unique_city_count,
                    available_pois=available_pois,
                    start_distances=start_distances,
                    max_distance=max_distance,
                    num_days=num_days,
                    start_city_key=start_distance,
                    end_city=end_distance,
                    remaining_days=remaining_days,
                    travel_streak=travel_streak,
                    stay_streak=stay_streak,
                )

                if simulation is None:
                    continue

                if simulation.total_gain > best_score_gain:
                    best_score_gain = simulation.total_gain
                    best_choice = simulation

            if best_choice is None:
                raise ValueError("Unable to find a feasible next step that respects all constraints.")

            # Commit chosen day
            day_plans.append(best_choice.day_plan)
            current_city = best_choice.next_city

            label_counts = best_choice.label_counts
            total_pois = best_choice.total_pois
            interest_score = best_choice.interest_score
            unique_city_count = best_choice.unique_cities
            city_score = best_choice.city_score
            coverage_sum = best_choice.coverage_sum
            coverage_count = best_choice.coverage_count
            coverage_score = best_choice.coverage_score
            travel_streak = best_choice.travel_streak
            stay_streak = best_choice.stay_streak
            if not end_city_reached and best_choice.next_city == end_distance and best_choice.day_plan.travel_minutes > 0:
                end_city_reached = True

            if best_choice.added_new_city:
                visited_set.add(best_choice.next_city)

            # Remove consumed POIs from availability
            if best_choice.selected_ids:
                poi_city_key = self._distance_to_poi[best_choice.next_city]
                available_pois[poi_city_key] = [
                    poi for poi in available_pois[poi_city_key] if poi.identifier not in best_choice.selected_ids
                ]

            # Enforce final-day arrival
            if day_index == num_days and current_city != end_distance:
                raise ValueError("Planner did not reach the destination on the final day.")

        return day_plans

    def available_cities(self) -> List[str]:
        return sorted({self._display_name(distance_name) for distance_name in self._distance_to_poi.keys()})

    def is_known_city(self, name: str) -> bool:
        try:
            self._resolve_city(name)
        except ValueError:
            return False
        return True

    def display_for(self, name: str) -> str:
        _, _, display = self._resolve_city(name)
        return display

    # ------------------------------------------------------------------ core helpers

    def _enumerate_candidates(
        self,
        current_city: str,
        end_city: str,
        day_index: int,
        num_days: int,
        visited_set: Iterable[str],
        earliest_arrival_day: int,
        end_city_reached: bool,
    ) -> List["CandidateAction"]:
        visited = set(visited_set)
        candidates: List[CandidateAction] = []

        # Option 1: stay in the current city
        candidates.append(
            CandidateAction(
                destination=current_city,
                travel_minutes=0.0,
                travel_from=None,
                added_new_city=False,
            )
        )

        # Day 1 must be spent in the start city
        if day_index == 1:
            return candidates

        # If we have reached the end city before the final day, remain there
        if end_city_reached and current_city == end_city and day_index < num_days:
            return candidates

        # Option 2: move to a neighboring city (respecting unique-visit constraint)
        for dest, payload in self._graph[current_city].items():
            if dest == current_city:
                continue
            duration = payload.get("duration_minutes")
            if duration is None or math.isinf(duration):
                continue

            if dest == end_city and day_index < earliest_arrival_day:
                continue

            already_visited = dest in visited
            allowed_revisit = False
            if dest == end_city and day_index == num_days:
                allowed_revisit = True
            if already_visited and not allowed_revisit:
                continue

            candidates.append(
                CandidateAction(
                    destination=dest,
                    travel_minutes=float(duration),
                    travel_from=current_city,
                    added_new_city=not already_visited,
                )
            )

        return candidates

    def _simulate_day(
        self,
        action: "CandidateAction",
        day_index: int,
        mtu_per_day: int,
        target_distribution: Mapping[str, float],
        label_counts: Mapping[str, int],
        total_pois: int,
        interest_score: float,
        city_score: float,
        coverage_sum: float,
        coverage_count: int,
        coverage_score: float,
        unique_city_count: int,
        available_pois: Mapping[str, Sequence[POI]],
        start_distances: Mapping[str, float],
        max_distance: float,
        num_days: int,
        start_city_key: str,
        end_city: str,
        remaining_days: int,
        travel_streak: int,
        stay_streak: int,
    ) -> Optional["SimulationResult"]:
        travel_tu = self._travel_time_units(action.travel_minutes)
        if travel_tu > mtu_per_day:
            return None

        # Ensure there is enough time after today to reach the destination
        if remaining_days < 0:
            return None
        min_days_needed = self._min_days_to_reach(action.destination, end_city, mtu_per_day)
        if min_days_needed > remaining_days:
            return None

        poi_city = self._distance_to_poi[action.destination]
        city_pois = available_pois.get(poi_city, ())

        selection = self._select_daily_pois(
            candidate_pois=city_pois,
            travel_tu=travel_tu,
            mtu_per_day=mtu_per_day,
            initial_counts=label_counts,
            initial_total=total_pois,
            target_distribution=target_distribution,
        )

        if selection is None:
            return None

        day_activity_tu = selection.activity_tu
        day_total_tu = travel_tu + day_activity_tu
        if day_total_tu > mtu_per_day:
            return None

        tu_score = self._tu_score(day_total_tu, mtu_per_day)
        travel_score = self._long_travel_score(action.travel_minutes)

        new_interest_score = self._interest_score(selection.counts, selection.total_pois, target_distribution)
        interest_gain = new_interest_score - interest_score

        added_new_city = action.added_new_city
        new_unique_count = unique_city_count + (1 if added_new_city else 0)
        new_city_score = self._city_efficiency(new_unique_count, num_days)
        city_gain = new_city_score - city_score

        new_coverage_sum = coverage_sum
        new_coverage_count = coverage_count
        if added_new_city and action.destination != start_city_key:
            distance = start_distances.get(action.destination, math.inf)
            if not math.isinf(distance) and max_distance > 0:
                normalized = max(0.0, min(1.0, distance / max_distance))
                cover_component = math.sqrt(normalized)
                new_coverage_sum += cover_component
                new_coverage_count += 1

        new_coverage_score = self._coverage_score(new_coverage_sum, new_coverage_count)
        coverage_gain = new_coverage_score - coverage_score

        if action.travel_minutes > 0:
            new_travel_streak = travel_streak + 1
            travel_penalty = -0.05 * (new_travel_streak**2)
            new_stay_streak = 0
            stay_penalty = 0.0
        else:
            new_travel_streak = 0
            travel_penalty = 0.0
            new_stay_streak = stay_streak + 1
            stay_penalty = -0.04 * max(0, new_stay_streak - 1) ** 2

        total_gain = (
            0.35 * interest_gain
            + 0.20 * tu_score
            + 0.15 * city_gain
            + 0.15 * coverage_gain
            + 0.15 * travel_score
            + travel_penalty
            + stay_penalty
        )

        day_plan = DayPlan(
            day=day_index,
            distance_city=action.destination,
            poi_city=self._distance_to_poi[action.destination],
            display_city=self._display_name(action.destination),
            travel_from=self._display_name(action.travel_from) if action.travel_from else None,
            travel_minutes=action.travel_minutes,
            pois=selection.selected,
            note=None,
        )

        return SimulationResult(
            total_gain=total_gain,
            day_plan=day_plan,
            next_city=action.destination,
            label_counts=selection.counts,
            total_pois=selection.total_pois,
            interest_score=new_interest_score,
            added_new_city=added_new_city,
            unique_cities=new_unique_count,
            city_score=new_city_score,
            coverage_sum=new_coverage_sum,
            coverage_count=new_coverage_count,
            coverage_score=new_coverage_score,
            selected_ids=[poi.identifier for poi in selection.selected],
            travel_streak=new_travel_streak,
            stay_streak=new_stay_streak,
        )

    # ------------------------------------------------------------------ scoring helpers

    @staticmethod
    def _normalise_preferences(preference_weights: Mapping[str, float]) -> Dict[str, float]:
        total = sum(preference_weights.get(category, 0.0) for category in CATEGORIES)
        if total <= 0:
            return {category: 1.0 / len(CATEGORIES) for category in CATEGORIES}
        return {category: float(preference_weights.get(category, 0.0)) / total for category in CATEGORIES}

    @staticmethod
    def _interest_score(
        counts: Mapping[str, int],
        total_pois: int,
        target_distribution: Mapping[str, float],
    ) -> float:
        if total_pois <= 0:
            return 0.0
        per_label_scores: List[float] = []
        for category in CATEGORIES:
            desired = target_distribution.get(category, 0.0)
            observed = counts.get(category, 0) / total_pois
            denom = max(desired, 1.0 / total_pois)
            per_label_scores.append(max(0.0, 1.0 - abs(observed - desired) / denom))
        return sum(per_label_scores) / len(CATEGORIES)

    @staticmethod
    def _tu_score(day_tu: int, mtu_per_day: int) -> float:
        if mtu_per_day <= 0:
            return 0.0
        value = 1.0 - abs(day_tu - mtu_per_day) / float(mtu_per_day)
        return max(0.0, min(1.0, value))

    @staticmethod
    def _long_travel_score(minutes: float) -> float:
        if minutes <= 0:
            return 1.0
        if minutes <= LONG_TRAVEL_COMFORT_MINUTES:
            return 1.0
        excess = (minutes - LONG_TRAVEL_COMFORT_MINUTES) / 30.0
        return math.exp(-(excess**2))

    @staticmethod
    def _coverage_score(coverage_sum: float, coverage_count: int) -> float:
        if coverage_count <= 0:
            return 0.0
        return coverage_sum / coverage_count

    @staticmethod
    def _city_efficiency(unique_city_count: int, num_days: int) -> float:
        target = 1 + min(num_days, 8)
        denom = max(1, target - 1)
        score = max(0.0, unique_city_count - 1) / denom
        return min(1.0, score)

    @staticmethod
    def _travel_time_units(minutes: float) -> int:
        if minutes <= 0:
            return 0
        return max(1, math.ceil(minutes / 60.0))

    def _min_days_to_reach(self, origin: str, destination: str, mtu_per_day: int) -> int:
        if origin == destination:
            return 0
        minutes = self._shortest_minutes.get(origin, {}).get(destination, math.inf)
        if math.isinf(minutes):
            return math.inf
        mtu_minutes = max(1, mtu_per_day * 60)
        return math.ceil(minutes / mtu_minutes)

    # ------------------------------------------------------------------ selection logic

    def _select_daily_pois(
        self,
        candidate_pois: Sequence[POI],
        travel_tu: int,
        mtu_per_day: int,
        initial_counts: Mapping[str, int],
        initial_total: int,
        target_distribution: Mapping[str, float],
    ) -> Optional["SelectionResult"]:
        remaining_tu = mtu_per_day - travel_tu
        if remaining_tu < 0:
            return None

        counts = {category: int(initial_counts.get(category, 0)) for category in CATEGORIES}
        total_pois = int(initial_total)
        selected: List[POI] = []
        used_indices: set[int] = set()

        current_interest = self._interest_score(counts, total_pois, target_distribution)
        current_activity_tu = 0

        while remaining_tu > 0:
            best_index = None
            best_gain = 0.0
            best_interest = current_interest
            best_activity_tu = current_activity_tu

            for index, poi in enumerate(candidate_pois):
                if index in used_indices:
                    continue
                activity_tu = _activity_time_units(poi)
                if activity_tu <= 0 or activity_tu > remaining_tu:
                    continue

                label = _primary_label(poi)
                new_counts = counts.copy()
                if label in new_counts:
                    new_counts[label] += 1
                new_total = total_pois + 1
                new_interest = self._interest_score(new_counts, new_total, target_distribution)
                interest_gain = new_interest - current_interest

                new_activity_tu = current_activity_tu + activity_tu
                tu_gain = self._tu_score(travel_tu + new_activity_tu, mtu_per_day) - self._tu_score(
                    travel_tu + current_activity_tu, mtu_per_day
                )

                incremental = 0.35 * interest_gain + 0.20 * max(tu_gain, 0.0)
                if incremental > best_gain:
                    best_gain = incremental
                    best_index = index
                    best_interest = new_interest
                    best_activity_tu = new_activity_tu

            if best_index is None or best_gain <= 0.0:
                break

            chosen = candidate_pois[best_index]
            selected.append(chosen)
            used_indices.add(best_index)

            label = _primary_label(chosen)
            if label in counts:
                counts[label] += 1
            total_pois += 1
            current_interest = best_interest
            current_activity_tu = best_activity_tu
            remaining_tu = mtu_per_day - travel_tu - current_activity_tu

        return SelectionResult(
            selected=selected,
            counts=counts,
            total_pois=total_pois,
            activity_tu=current_activity_tu,
        )

    # ------------------------------------------------------------------ distance helpers

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

    def _compute_shortest_paths(self) -> Dict[str, Dict[str, float]]:
        result: Dict[str, Dict[str, float]] = {}
        for origin in self._distance_to_poi.keys():
            result[origin] = self._dijkstra(origin)
        return result

    def _dijkstra(self, origin: str) -> Dict[str, float]:
        distances = {city: math.inf for city in self._graph.keys()}
        distances[origin] = 0.0
        heap: List[Tuple[float, str]] = [(0.0, origin)]
        while heap:
            current_dist, city = heappop(heap)
            if current_dist > distances[city]:
                continue
            for neighbour, payload in self._graph[city].items():
                weight = payload.get("duration_minutes")
                if weight is None or math.isinf(weight):
                    continue
                new_dist = current_dist + weight
                if new_dist < distances[neighbour]:
                    distances[neighbour] = new_dist
                    heappush(heap, (new_dist, neighbour))
        return distances

    # ------------------------------------------------------------------ city helpers

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
        for distance_name in self._distance_to_poi.keys():
            for variant in (
                distance_name,
                distance_name.replace(", Switzerland", ""),
                self._distance_to_poi[distance_name],
            ):
                aliases[self._normalise_name(variant)] = distance_name
        for variant, distance_name in EXTRA_CITY_ALIASES.items():
            aliases[self._normalise_name(variant)] = distance_name
        return aliases

    @staticmethod
    def _normalise_name(value: str) -> str:
        normalised = unicodedata.normalize("NFKD", value or "")
        ascii_value = normalised.encode("ascii", "ignore").decode("ascii")
        return ascii_value.strip().lower()


# ---------------------------------------------------------------------- dataclasses for simulation


@dataclass
class CandidateAction:
    destination: str
    travel_minutes: float
    travel_from: Optional[str]
    added_new_city: bool


@dataclass
class SelectionResult:
    selected: List[POI]
    counts: Dict[str, int]
    total_pois: int
    activity_tu: int


@dataclass
class SimulationResult:
    total_gain: float
    day_plan: DayPlan
    next_city: str
    label_counts: Dict[str, int]
    total_pois: int
    interest_score: float
    added_new_city: bool
    unique_cities: int
    city_score: float
    coverage_sum: float
    coverage_count: int
    coverage_score: float
    selected_ids: List[str]
    travel_streak: int
    stay_streak: int
