"""Bidirectional Greedy route planner tuned for the new itinerary score system + local search."""

from __future__ import annotations

import json
import math
import unicodedata
from copy import deepcopy
from dataclasses import dataclass
from heapq import heappop, heappush
from pathlib import Path
import random
import logging
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
        select_pois_for_day,
    )
else:  # pragma: no cover
    from .data_store import CATEGORIES, POI, TravelDataStore
    from .poi_selection import _activity_time_units, _is_in_season, _primary_label, select_pois_for_day



LONG_TRAVEL_COMFORT_MINUTES = 120.0

# Use the project logger name so messages appear alongside existing backend logs
LOGGER = logging.getLogger("alp_scheduler")

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


@dataclass
class _ScenarioContext:
    start_city: str
    end_city: str
    start_distance: str
    end_distance: str
    num_days: int
    season: Optional[str]
    mtu_per_day: int
    preferences: Mapping[str, float]
    earliest_arrival_day: int
    rng: random.Random


# Transition labels for ablation (swap removed; add targeted rebalance)
TRANSITION_LABELS = {
    1: "substitute_pois",
    2: "insert_new_city",
    3: "convert_travel_day_to_stay",
    4: "rebalance_label_gap",
}


class RoutePlanner:
    """Greedy planner aligned with the new evaluation metrics."""

    def __init__(
        self,
        datastore: TravelDataStore,
        distance_path: Path = Path("data/out/google_city_distances.json"),
        allowed_transitions: Optional[Sequence[int]] = None,
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
        # Ablation configuration
        self._allowed_transitions = set(allowed_transitions) if allowed_transitions else set(TRANSITION_LABELS.keys())
        # Last-run metrics for experiments
        self.last_base_score: Optional[float] = None
        self.last_final_score: Optional[float] = None
        self.last_gain: Optional[float] = None
        self.last_base_components: Dict[str, float] = {}

    # ------------------------------------------------------------------ public API

    def plan_route(
        self,
        start_city: str,
        end_city: str,
        num_days: int,
        preference_weights: Mapping[str, float],
        season: Optional[str],
        mtu_per_day: int = 8,
        seed: Optional[int] = 1337,
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

        tu_totals = {category: 0.0 for category in CATEGORIES}
        total_tu = 0.0
        interest_score = self._interest_score_tu(tu_totals, total_tu, target_distribution)

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

        # Forward greedy construction
        rng = random.Random(seed) if seed is not None else random.Random(1337)

        scenario = _ScenarioContext(
            start_city=start_city,
            end_city=end_city,
            start_distance=start_distance,
            end_distance=end_distance,
            num_days=num_days,
            season=season,
            mtu_per_day=mtu_per_day,
            preferences=target_distribution,
            earliest_arrival_day=earliest_arrival_day,
            rng=rng,
        )

        forward_plan = self._greedy_construct(scenario)

        # Build backward-based variant (day 1 fixed), then run local search on both and pick best
        backward_variant = self._build_backward_variant(scenario, forward_plan)

        # Evaluate greedy seeds (base, before local search)
        try:
            from .evaluator import evaluate_itinerary  # type: ignore
        except ImportError:  # pragma: no cover
            from evaluator import evaluate_itinerary  # type: ignore

        f_base_eval = evaluate_itinerary(
            forward_plan,
            start_city=scenario.start_city,
            end_city=scenario.end_city,
            interests=scenario.preferences,
            mtu=scenario.mtu_per_day,
            season=scenario.season,
        )
        b_base_total = -math.inf
        if backward_variant is not None:
            b_base_eval = evaluate_itinerary(
                backward_variant,
                start_city=scenario.start_city,
                end_city=scenario.end_city,
                interests=scenario.preferences,
                mtu=scenario.mtu_per_day,
                season=scenario.season,
            )
            b_base_total = b_base_eval.total if not b_base_eval.hard_violations else -math.inf
        f_base_total = f_base_eval.total if not f_base_eval.hard_violations else -math.inf
        base_best_score = max(f_base_total, b_base_total)
        base_components: Dict[str, float] = {}
        if base_best_score == f_base_total and not f_base_eval.hard_violations:
            base_components = dict(f_base_eval.components)
        elif base_best_score == b_base_total and backward_variant is not None and not b_base_eval.hard_violations:
            base_components = dict(b_base_eval.components)

        if base_best_score == -math.inf:
            base_best_score = 0.0
            base_components = {}

        self.last_base_score = base_best_score
        self.last_base_components = base_components
        
        # Run local search on both seeds (forward and backward if available) and keep the better by evaluator score

        LOGGER.info("RoutePlanner: refining forward greedy with local search")
        forward_ls = self._run_local_search(forward_plan, scenario)
        f_eval = evaluate_itinerary(
            forward_ls,
            start_city=scenario.start_city,
            end_city=scenario.end_city,
            interests=scenario.preferences,
            mtu=scenario.mtu_per_day,
            season=scenario.season,
        )

        best_plan = forward_ls
        best_score = f_eval.total if not f_eval.hard_violations else -math.inf

        if backward_variant is not None:
            LOGGER.info("RoutePlanner: refining backward variant with local search")
            backward_ls = self._run_local_search(backward_variant, scenario)
            b_eval = evaluate_itinerary(
                backward_ls,
                start_city=scenario.start_city,
                end_city=scenario.end_city,
                interests=scenario.preferences,
                mtu=scenario.mtu_per_day,
                season=scenario.season,
            )
            b_score = b_eval.total if not b_eval.hard_violations else -math.inf
            if b_score > best_score:
                best_plan = backward_ls
                best_score = b_score
                LOGGER.info("RoutePlanner: selected backward-based result (score=%.5f)", best_score)
            else:
                LOGGER.info("RoutePlanner: kept forward-based result (score=%.5f vs backward %.5f)", best_score, b_score)
        else:
            LOGGER.info("RoutePlanner: backward variant unavailable; kept forward-based result (score=%.5f)", best_score)

        self._renumber_days(best_plan)
        # Record last-final and gain vs base-best
        self.last_final_score = best_score if math.isfinite(best_score) else 0.0
        self.last_gain = self.last_final_score - (self.last_base_score or 0.0)
        return best_plan

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

    def _greedy_construct(self, scenario: _ScenarioContext) -> List[DayPlan]:
        """Construct an itinerary greedily under the current heuristic."""
        start_distance = scenario.start_distance
        end_distance = scenario.end_distance
        num_days = scenario.num_days
        season = scenario.season
        mtu_per_day = scenario.mtu_per_day
        target_distribution = scenario.preferences
        earliest_arrival_day = scenario.earliest_arrival_day

        available_pois: Dict[str, List[POI]] = {}
        for poi_city in self._distance_to_poi.values():
            all_pois = list(self._datastore.pois_for_city(poi_city, season))
            filtered = [poi for poi in all_pois if season is None or _is_in_season(poi, season)]
            available_pois[poi_city] = filtered

        tu_totals = {category: 0.0 for category in CATEGORIES}
        total_tu = 0.0
        interest_score = self._interest_score_tu(tu_totals, total_tu, target_distribution)

        visited_set = {start_distance}
        unique_city_count = 1
        city_score = self._city_efficiency(unique_city_count, num_days)

        coverage_sum = 0.0
        coverage_count = 0
        coverage_score = 0.0

        start_distances = self._shortest_minutes[start_distance]
        max_distance = max((v for v in start_distances.values() if not math.isinf(v)), default=1.0)

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
                    tu_by_label=tu_totals,
                    total_tu=total_tu,
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
                    rng=scenario.rng,
                )
                if simulation is None:
                    continue
                if simulation.total_gain > best_score_gain:
                    best_score_gain = simulation.total_gain
                    best_choice = simulation

            if best_choice is None:
                raise ValueError("Unable to find a feasible next step that respects all constraints.")

            day_plans.append(best_choice.day_plan)
            current_city = best_choice.next_city
            # Update TU totals with selected POIs for the committed day
            day_tu_inc = 0.0
            for p in best_choice.day_plan.pois:
                tu = float(_activity_time_units(p))
                lab = _primary_label(p)
                if lab in tu_totals:
                    tu_totals[lab] += tu
                day_tu_inc += tu
            total_tu += day_tu_inc
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
            if best_choice.selected_ids:
                poi_city_key = self._distance_to_poi[best_choice.next_city]
                available_pois[poi_city_key] = [
                    poi for poi in available_pois[poi_city_key] if poi.identifier not in best_choice.selected_ids
                ]

        if current_city != end_distance:
            raise ValueError("Planner did not reach the destination on the final day.")
        return day_plans

    def _build_backward_variant(
        self, scenario: _ScenarioContext, forward_plan: List[DayPlan]
    ) -> Optional[List[DayPlan]]:
        """Construct an alternate plan from a backward greedy and reverse it into days 2..N."""
        LOGGER.info(
            "RoutePlanner: attempting backward variant | start=%s end=%s days=%d",
            scenario.start_city,
            scenario.end_city,
            scenario.num_days,
        )
        m = scenario.num_days - 1
        if m <= 0:
            LOGGER.info("RoutePlanner: backward variant aborted (m <= 0)")
            return None
        # Compute earliest arrival for the backward window
        if m <= 7:
            buffer = 1
        elif m <= 15:
            buffer = 2
        else:
            buffer = 3
        earliest_back = max(1, m - buffer)
        LOGGER.info(
            "RoutePlanner: backward window m=%d earliest_back=%d (buffer=%d)",
            m,
            earliest_back,
            buffer,
        )
        back_scenario = _ScenarioContext(
            start_city=scenario.end_city,
            end_city=scenario.start_city,
            start_distance=scenario.end_distance,
            end_distance=scenario.start_distance,
            num_days=m,
            season=scenario.season,
            mtu_per_day=scenario.mtu_per_day,
            preferences=scenario.preferences,
            earliest_arrival_day=earliest_back,
            rng=scenario.rng,
        )
        try:
            back_plan = self._greedy_construct(back_scenario)
        except Exception:
            LOGGER.info("RoutePlanner: backward greedy failed to construct a plan")
            return None
        seq = [dp.distance_city for dp in back_plan]
        if not seq or seq[-1] != scenario.start_distance:
            LOGGER.info(
                "RoutePlanner: backward plan invalid (seq empty or does not end at original start). seq_end=%s expected=%s",
                (seq[-1] if seq else None),
                scenario.start_distance,
            )
            return None
        seq_rev = list(reversed(seq))  # length m, starts at start_distance, ends at end_distance
        LOGGER.info("RoutePlanner: reversed city sequence for days 2..N: %s", [self._display_name(c) for c in seq_rev])

        # Build full plan: keep forward day 1, then follow seq_rev[1..]
        new_plan: List[DayPlan] = [self._clone_day(forward_plan[0])] if forward_plan else []
        used_ids = {poi.identifier for dp in new_plan for poi in dp.pois}
        prev = new_plan[0].distance_city if new_plan else seq_rev[0]
        # Append exactly m days (days 2..N). Start from idx=0 to include a possible stay on day 2.
        for idx in range(0, len(seq_rev)):
            dest = seq_rev[idx]
            # Allow stay days (prev == dest) with 0 travel minutes; otherwise require a finite edge
            if dest == prev:
                minutes = 0.0
            else:
                payload = self._graph.get(prev, {}).get(dest)
                if not payload:
                    LOGGER.info(
                        "RoutePlanner: backward rebuild failed (no edge) %s -> %s",
                        self._display_name(prev),
                        self._display_name(dest),
                    )
                    return None
                minutes = float(payload.get("duration_minutes") or math.inf)
                if math.isinf(minutes):
                    LOGGER.info(
                        "RoutePlanner: backward rebuild failed (infinite minutes) %s -> %s",
                        self._display_name(prev),
                        self._display_name(dest),
                    )
                    return None
            day = self._build_day(dest, prev, minutes, scenario, used_ids)
            if day is None:
                LOGGER.info(
                    "RoutePlanner: backward rebuild failed (no in-season POIs or MTU violation) at %s",
                    self._display_name(dest),
                )
                return None
            new_plan.append(day)
            used_ids.update(poi.identifier for poi in day.pois)
            prev = dest

        # Final sanity: recompute travel, validate sequence
        self._recompute_travel(new_plan)
        if not self._is_valid_sequence(new_plan, scenario):
            LOGGER.info("RoutePlanner: backward variant failed validation")
            return None
        self._renumber_days(new_plan)
        LOGGER.info("RoutePlanner: backward variant built successfully")
        return new_plan

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
        tu_by_label: Mapping[str, float],
        total_tu: float,
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
        rng: Optional[random.Random] = None,
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
        # Hard rule: do not visit/stay in cities without in-season POIs.
        if not city_pois:
            return None

        # Use shared POI selector for alignment
        selected_list = select_pois_for_day(
            city_pois,
            target_distribution,
            travel_tu=travel_tu,
            season=None,
            mtu_per_day=mtu_per_day,
            rng=rng,
        )

        day_activity_tu = sum(_activity_time_units(p) for p in selected_list)
        day_total_tu = travel_tu + day_activity_tu
        if day_total_tu > mtu_per_day:
            return None

        tu_score = self._tu_score(day_total_tu, mtu_per_day)
        travel_score = self._long_travel_score(action.travel_minutes)

        # TU-based interest: compute day TU by label and update totals
        day_tu_by_label: Dict[str, float] = {c: 0.0 for c in CATEGORIES}
        day_total_tu_activities = 0.0
        for p in selected_list:
            tu = float(_activity_time_units(p))
            lab = _primary_label(p)
            if lab in day_tu_by_label:
                day_tu_by_label[lab] += tu
            day_total_tu_activities += tu
        new_totals: Dict[str, float] = {k: float(tu_by_label.get(k, 0.0)) + day_tu_by_label.get(k, 0.0) for k in CATEGORIES}
        new_total_tu = float(total_tu) + day_total_tu_activities
        new_interest_score = self._interest_score_tu(new_totals, new_total_tu, target_distribution)
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
            + 0.20 * travel_score
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
            pois=selected_list,
            note=None,
        )

        return SimulationResult(
            total_gain=total_gain,
            day_plan=day_plan,
            next_city=action.destination,
            label_counts={},
            total_pois=0,
            interest_score=new_interest_score,
            added_new_city=added_new_city,
            unique_cities=new_unique_count,
            city_score=new_city_score,
            coverage_sum=new_coverage_sum,
            coverage_count=new_coverage_count,
            coverage_score=new_coverage_score,
            selected_ids=[poi.identifier for poi in selected_list],
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
    def _interest_score_tu(
        tu_by_label: Mapping[str, float],
        total_tu: float,
        target_distribution: Mapping[str, float],
    ) -> float:
        if total_tu <= 0:
            return 0.0
        per_label_scores: List[float] = []
        for category in CATEGORIES:
            desired = float(target_distribution.get(category, 0.0))
            observed = float(tu_by_label.get(category, 0.0)) / total_tu if total_tu > 0 else 0.0
            denom = max(desired, 1.0 / max(total_tu, 1.0))
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
        # Align with evaluator: target unique cities = 1 + ceil(0.6 * num_days)
        target = 1 + math.ceil(0.6 * num_days)
        denom = max(1, target - 1)
        score = max(0.0, unique_city_count - 1) / denom
        return min(1.0, score)

    @staticmethod
    def _travel_time_units(minutes: float) -> int:
        if minutes <= 0:
            return 0
        return max(1, math.ceil(minutes / 60.0))

    # ------------------------------------------------------------------ local search helpers

    def _run_local_search(self, initial_plan: List[DayPlan], scenario: _ScenarioContext) -> List[DayPlan]:
        try:  # pragma: no cover - support both package and script imports
            from .evaluator import evaluate_itinerary  # type: ignore
        except ImportError:  # pragma: no cover
            from evaluator import evaluate_itinerary  # type: ignore

        max_iterations = 10
        improvement_threshold = 1e-7
        config = {
            "gap_swaps": 20,
            "gap_per_day_cap": 5,
            "poi_candidates": 4,
            "insert_limit": 12,
        }

        best_plan = [self._clone_day(day) for day in initial_plan]
        best_eval = evaluate_itinerary(
            best_plan,
            start_city=scenario.start_city,
            end_city=scenario.end_city,
            interests=scenario.preferences,
            mtu=scenario.mtu_per_day,
            season=scenario.season,
        )
        if best_eval.hard_violations:
            return best_plan

        iterations = 0
        while iterations < max_iterations:
            iterations += 1
            improved = False
            best_neighbor_plan: Optional[List[DayPlan]] = None
            best_neighbor_score = best_eval.total

            for candidate in self._generate_neighbors(best_plan, scenario, config):
                self._renumber_days(candidate)
                evaluation = evaluate_itinerary(
                    candidate,
                    start_city=scenario.start_city,
                    end_city=scenario.end_city,
                    interests=scenario.preferences,
                    mtu=scenario.mtu_per_day,
                    season=scenario.season,
                )
                if evaluation.hard_violations:
                    continue
                if evaluation.total > best_neighbor_score + improvement_threshold:
                    best_neighbor_score = evaluation.total
                    best_neighbor_plan = candidate
                    best_eval = evaluation
                    improved = True

            if not improved or best_neighbor_plan is None:
                break

            best_plan = best_neighbor_plan

        return best_plan

    def _generate_neighbors(
        self,
        plan: List[DayPlan],
        scenario: _ScenarioContext,
        config: Mapping[str, int],
    ) -> Iterable[List[DayPlan]]:
        # City-block swap removed from ablation transitions
        if 4 in self._allowed_transitions:
            yield from self._rebalance_label_gap(
                plan,
                scenario,
                gap_swaps=int(config.get("gap_swaps", 0)),
                per_day_cap=int(config.get("gap_per_day_cap", 0)),
            )
        if 1 in self._allowed_transitions:
            yield from self._substitute_pois(plan, scenario, config.get("poi_candidates", 0))
        if 2 in self._allowed_transitions:
            yield from self._insert_new_city(plan, scenario, config.get("insert_limit", 0))
        if 3 in self._allowed_transitions:
            yield from self._convert_travel_day_to_stay(plan, scenario)

    def _rebalance_label_gap(
        self,
        plan: List[DayPlan],
        scenario: _ScenarioContext,
        gap_swaps: int,
        per_day_cap: int,
    ) -> Iterable[List[DayPlan]]:
        if gap_swaps <= 0 or per_day_cap <= 0:
            return

        tu_by_label: Dict[str, float] = {k: 0.0 for k in CATEGORIES}
        total_tu = 0.0
        for day in plan:
            for poi in day.pois:
                tu = float(_activity_time_units(poi))
                total_tu += tu
                lab = _primary_label(poi)
                if lab in tu_by_label:
                    tu_by_label[lab] += tu

        target_sum = sum(float(scenario.preferences.get(k, 0.0)) for k in CATEGORIES)
        target = {k: (float(scenario.preferences.get(k, 0.0)) / target_sum) if target_sum > 0 else (1.0 / len(CATEGORIES)) for k in CATEGORIES}

        if total_tu <= 0:
            return

        gaps: Dict[str, float] = {}
        for k in CATEGORIES:
            actual = tu_by_label[k] / total_tu if total_tu > 0 else 0.0
            gaps[k] = target.get(k, 0.0) - actual

        deficit_label = max(CATEGORIES, key=lambda k: gaps.get(k, 0.0))
        if gaps.get(deficit_label, 0.0) <= 1e-9:
            return
        source_label = min(CATEGORIES, key=lambda k: gaps.get(k, 0.0))
        if source_label == deficit_label:
            return

        generated = 0
        all_ids = [{poi.identifier for poi in day.pois} for day in plan]

        for idx, day in enumerate(plan):
            if generated >= gap_swaps:
                break

            removable = [p for p in day.pois if _primary_label(p) == source_label]
            if not removable:
                continue
            removable.sort(key=lambda p: _activity_time_units(p), reverse=True)

            poi_city = day.poi_city
            city_pois = list(self._datastore.pois_for_city(poi_city, season=scenario.season))
            if not city_pois:
                continue
            used_elsewhere = set().union(*(all_ids[j] for j in range(len(plan)) if j != idx))
            add_candidates = [p for p in city_pois if _primary_label(p) == deficit_label and p.identifier not in used_elsewhere]
            if not add_candidates:
                continue
            add_candidates.sort(key=lambda p: _activity_time_units(p), reverse=True)

            built_for_day = 0
            for rem in removable:
                if built_for_day >= per_day_cap or generated >= gap_swaps:
                    break
                for add in add_candidates:
                    if built_for_day >= per_day_cap or generated >= gap_swaps:
                        break
                    new_plan = [self._clone_day(d) for d in plan]
                    new_day = new_plan[idx]
                    new_pois = [p for p in new_day.pois if p.identifier != rem.identifier]
                    if any(p.identifier == add.identifier for p in new_pois):
                        continue
                    new_pois.append(add)
                    new_day.pois = new_pois
                    if not self._is_valid_day(new_day, scenario.mtu_per_day):
                        continue
                    if not self._is_valid_sequence(new_plan, scenario):
                        continue
                    yield new_plan
                    built_for_day += 1
                    generated += 1

    def _swap_city_blocks(
        self,
        plan: List[DayPlan],
        scenario: _ScenarioContext,
        swap_limit: int,
    ) -> Iterable[List[DayPlan]]:
        if swap_limit <= 0:
            return
        blocks = self._city_blocks(plan)
        interior_blocks = [block for block in blocks if block[0] != 0 and block[2] != len(plan) - 1]
        if len(interior_blocks) < 2:
            return

        proposals: List[Tuple[int, int]] = []
        for i in range(len(interior_blocks)):
            for j in range(i + 1, len(interior_blocks)):
                proposals.append((interior_blocks[i][0], interior_blocks[j][0]))
                if len(proposals) >= swap_limit:
                    break
            if len(proposals) >= swap_limit:
                break

        for start_i, start_j in proposals:
            block_i = next(block for block in blocks if block[0] == start_i)
            block_j = next(block for block in blocks if block[0] == start_j)
            new_plan = [self._clone_day(day) for day in plan]
            new_plan[block_i[0] : block_i[2] + 1], new_plan[block_j[0] : block_j[2] + 1] = (
                new_plan[block_j[0] : block_j[2] + 1],
                new_plan[block_i[0] : block_i[2] + 1],
            )
            self._recompute_travel(new_plan)
            if not self._is_valid_sequence(new_plan, scenario):
                continue
            yield new_plan

    def _substitute_pois(
        self,
        plan: List[DayPlan],
        scenario: _ScenarioContext,
        poi_candidates: int,
    ) -> Iterable[List[DayPlan]]:
        if poi_candidates <= 0:
            return

        all_pois_map = {
            city: list(self._datastore.pois_for_city(city, season=scenario.season))
            for city in self._datastore.cities()
        }

        counts = self._label_counts(plan)
        total_pois = sum(counts.values())
        targets = scenario.preferences

        excess_labels = {
            label
            for label, observed in counts.items()
            if total_pois > 0 and observed / total_pois > targets.get(label, 0.0)
        }
        deficit_labels = {
            label
            for label, observed in counts.items()
            if total_pois == 0 or observed / total_pois < targets.get(label, 0.0)
        }

        attempts = 0
        used_ids = {poi.identifier for day in plan for poi in day.pois}

        for idx, day in enumerate(plan):
            if attempts >= poi_candidates:
                break
            candidates = [
                poi
                for poi in all_pois_map.get(day.poi_city, [])
                if poi.identifier not in used_ids and _primary_label(poi) in deficit_labels
            ]
            if not candidates:
                continue

            removable = None
            for poi in day.pois:
                if _primary_label(poi) in excess_labels:
                    removable = poi
                    break
            if removable is None and day.pois:
                removable = day.pois[-1]
            if removable is None:
                continue

            removable_tu = _activity_time_units(removable)
            remaining_tu = scenario.mtu_per_day - self._travel_time_units(day.travel_minutes) + removable_tu

            for candidate in candidates:
                candidate_tu = _activity_time_units(candidate)
                if candidate_tu > remaining_tu:
                    continue
                new_plan = [self._clone_day(d) for d in plan]
                new_pois = [p for p in new_plan[idx].pois if p.identifier != removable.identifier]
                new_pois.append(candidate)
                new_plan[idx].pois = new_pois
                if not self._is_valid_day(new_plan[idx], scenario.mtu_per_day):
                    continue
                if not self._is_valid_sequence(new_plan, scenario):
                    continue
                attempts += 1
                yield new_plan
                break

    def _insert_new_city(
        self,
        plan: List[DayPlan],
        scenario: _ScenarioContext,
        insert_limit: int,
    ) -> Iterable[List[DayPlan]]:
        if insert_limit <= 0:
            return

        existing_cities = {day.distance_city for day in plan}
        candidate_cities = [
            city for city in self._graph.keys() if city not in existing_cities and city != scenario.end_distance
        ]
        if not candidate_cities:
            return

        generated = 0
        max_minutes = scenario.mtu_per_day * 60

        for idx in range(1, len(plan) - 1):
            if generated >= insert_limit:
                break
            current_city = plan[idx].distance_city
            if current_city in {scenario.start_distance, scenario.end_distance}:
                continue
            prev_city = plan[idx - 1].distance_city
            next_city = plan[idx + 1].distance_city

            original_ids = {poi.identifier for poi in plan[idx].pois}
            used_ids = {poi.identifier for day in plan for poi in day.pois if day.distance_city != current_city}

            for candidate_city in candidate_cities:
                if generated >= insert_limit:
                    break
                if candidate_city == scenario.end_distance and (idx + 1) < scenario.earliest_arrival_day - 1:
                    continue

                payload_prev = self._graph.get(prev_city, {}).get(candidate_city)
                payload_next = self._graph.get(candidate_city, {}).get(next_city)
                if not payload_prev or not payload_next:
                    continue
                travel_prev = float(payload_prev.get("duration_minutes", math.inf))
                travel_next = float(payload_next.get("duration_minutes", math.inf))
                if any(math.isinf(t) or t > max_minutes for t in (travel_prev, travel_next)):
                    continue

                new_day = self._build_day(candidate_city, prev_city, travel_prev, scenario, used_ids)
                if new_day is None:
                    continue

                new_plan = [self._clone_day(day) for day in plan]
                new_plan[idx] = new_day
                self._recompute_travel(new_plan)
                if not self._is_valid_sequence(new_plan, scenario):
                    continue
                generated += 1
                yield new_plan

    def _build_day(
        self,
        distance_city: str,
        prev_distance_city: str,
        travel_minutes: float,
        scenario: _ScenarioContext,
        used_ids: set[str],
    ) -> Optional[DayPlan]:
        poi_city = self._distance_to_poi.get(distance_city)
        if not poi_city:
            return None

        candidates = [
            poi
            for poi in self._datastore.pois_for_city(poi_city, season=scenario.season)
            if poi.identifier not in used_ids
        ]
        # If a city has no in-season POIs, do not create a day for it.
        if not candidates:
            return None

        travel_tu = self._travel_time_units(travel_minutes)
        if travel_tu > scenario.mtu_per_day:
            return None

        selected: List[POI] = []
        if candidates:
            selected = select_pois_for_day(
                candidates,
                scenario.preferences,
                travel_tu=travel_tu,
                season=scenario.season,
                mtu_per_day=scenario.mtu_per_day,
                rng=scenario.rng,
            )
            total_tu = travel_tu + sum(_activity_time_units(p) for p in selected)
            while selected and total_tu > scenario.mtu_per_day:
                selected.pop()
                total_tu = travel_tu + sum(_activity_time_units(p) for p in selected)
            if total_tu > scenario.mtu_per_day:
                return None

        return DayPlan(
            day=0,
            distance_city=distance_city,
            poi_city=poi_city,
            display_city=self._display_name(distance_city),
            travel_from=self._display_name(prev_distance_city),
            travel_minutes=travel_minutes,
            pois=selected,
            note=None,
        )

    def _recompute_travel(self, plan: List[DayPlan]) -> None:
        for idx, day in enumerate(plan):
            if idx == 0:
                day.travel_from = None
                day.travel_minutes = 0.0
                continue
            prev_city = plan[idx - 1].distance_city
            current_city = day.distance_city
            day.travel_from = self._display_name(prev_city)
            if prev_city == current_city:
                day.travel_minutes = 0.0
            else:
                payload = self._graph.get(prev_city, {}).get(current_city)
                day.travel_minutes = float(payload.get("duration_minutes", math.inf)) if payload else math.inf

    @staticmethod
    def _city_blocks(plan: Sequence[DayPlan]) -> List[Tuple[int, str, int]]:
        blocks: List[Tuple[int, str, int]] = []
        start = 0
        current_city = plan[0].distance_city
        for idx in range(1, len(plan)):
            if plan[idx].distance_city != current_city:
                blocks.append((start, current_city, idx - 1))
                start = idx
                current_city = plan[idx].distance_city
        blocks.append((start, current_city, len(plan) - 1))
        return blocks

    @staticmethod
    def _label_counts(plan: Sequence[DayPlan]) -> Dict[str, int]:
        counts = {label: 0 for label in CATEGORIES}
        for day in plan:
            for poi in day.pois:
                label = _primary_label(poi)
                if label in counts:
                    counts[label] += 1
        return counts

    @staticmethod
    def _is_valid_sequence(plan: List[DayPlan], scenario: _ScenarioContext) -> bool:
        if len(plan) != scenario.num_days:
            return False
        if plan[0].distance_city != scenario.start_distance:
            return False
        if plan[-1].distance_city != scenario.end_distance:
            return False
        earliest = scenario.earliest_arrival_day
        first_end = next((idx for idx, day in enumerate(plan) if day.distance_city == scenario.end_distance), len(plan) - 1)
        if first_end + 1 < earliest:
            return False
        max_minutes = scenario.mtu_per_day * 60
        prev_city = plan[0].distance_city
        seen: Dict[str, bool] = {prev_city: True}
        for idx in range(1, len(plan)):
            city = plan[idx].distance_city
            if city != prev_city and city in seen and city != scenario.end_distance:
                return False
            seen[city] = True
            prev_city = city
            minutes = plan[idx].travel_minutes
            if not math.isfinite(minutes) or minutes > max_minutes:
                return False
        return True

    def _is_valid_day(self, day: DayPlan, mtu: int) -> bool:
        travel_tu = self._travel_time_units(day.travel_minutes)
        activity_tu = sum(_activity_time_units(p) for p in day.pois)
        return travel_tu + activity_tu <= mtu

    @staticmethod
    def _renumber_days(plan: List[DayPlan]) -> None:
        for idx, day in enumerate(plan, start=1):
            day.day = idx

    @staticmethod
    def _clone_day(day: DayPlan) -> DayPlan:
        return deepcopy(day)

    def _convert_travel_day_to_stay(self, plan: List[DayPlan], scenario: _ScenarioContext) -> Iterable[List[DayPlan]]:
        for idx in range(1, len(plan)):
            day = plan[idx]
            if day.travel_minutes <= 0.0:
                continue

            prev_city = plan[idx - 1].distance_city
            poi_city = self._distance_to_poi.get(prev_city)
            if not poi_city:
                continue

            all_pois = self._datastore.pois_for_city(poi_city, season=scenario.season)
            if not all_pois:
                continue

            used_ids = {
                poi.identifier
                for j, other_day in enumerate(plan)
                if j != idx
                for poi in other_day.pois
            }

            available = [poi for poi in all_pois if poi.identifier not in used_ids]
            # allow empty selection; stay-day with no POIs is still valid

            new_plan = [self._clone_day(d) for d in plan]
            replacement = new_plan[idx]
            replacement.distance_city = prev_city
            replacement.poi_city = poi_city
            replacement.display_city = self._display_name(prev_city)
            replacement.travel_from = self._display_name(prev_city)
            replacement.travel_minutes = 0.0

            if available:
                replacement.pois = select_pois_for_day(
                    available,
                    scenario.preferences,
                    travel_tu=0,
                    season=scenario.season,
                    mtu_per_day=scenario.mtu_per_day,
                    rng=scenario.rng,
                )
            else:
                # Do not propose staying where there are no in-season POIs
                continue

            self._recompute_travel(new_plan)
            if not math.isfinite(new_plan[idx].travel_minutes):
                continue
            if not self._is_valid_day(new_plan[idx], scenario.mtu_per_day):
                continue
            if not self._is_valid_sequence(new_plan, scenario):
                continue
            yield new_plan

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
