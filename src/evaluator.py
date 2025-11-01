"""
Itinerary evaluator for SwissTravelPlanner.

Implements the latest scoring rules with hard-constraint checks and
component breakdown. Designed to score a complete itinerary at the end
of planning. Can also be used incrementally to compute partial sums for
search heuristics, though search should generally use a lighter, optimistic
upper bound as its heuristic.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

try:
    # Local imports (when running inside the repo)
    from .route_planner import DayPlan  # type: ignore
    from .poi_selection import (
        _primary_label,
        _is_in_season,
        _activity_time_units,
    )  # type: ignore
    from .data_store import CATEGORIES
except Exception:  # pragma: no cover
    # Fallback for direct execution
    from route_planner import DayPlan  # type: ignore
    from poi_selection import (  # type: ignore
        _primary_label,
        _is_in_season,
        _activity_time_units,
    )
    from data_store import CATEGORIES  # type: ignore


DEFAULT_DIST_PATH = Path("data/out/google_city_distances.json")


@dataclass(frozen=True)
class ScoreBreakdown:
    total: float
    components: Mapping[str, float]
    hard_violations: Tuple[str, ...]


def _travel_time_units(minutes: float) -> int:
    if minutes <= 0:
        return 0
    return max(1, math.ceil(minutes / 60.0))


def _load_distance_graph(path: Path) -> Dict[str, Dict[str, float]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    graph: Dict[str, Dict[str, float]] = {}
    for origin, destinations in data.get("distances", {}).items():
        graph[origin] = {}
        for dest, payload in destinations.items():
            val = payload.get("duration_minutes")
            graph[origin][dest] = float(val) if val is not None else math.inf
    return graph


def _dijkstra(origin: str, graph: Mapping[str, Mapping[str, float]]) -> Dict[str, float]:
    # Simple Dijkstra on minutes
    import heapq

    dist: Dict[str, float] = {node: math.inf for node in graph.keys()}
    dist[origin] = 0.0
    heap: List[Tuple[float, str]] = [(0.0, origin)]
    while heap:
        d, u = heapq.heappop(heap)
        if d > dist[u]:
            continue
        for v, w in graph[u].items():
            if math.isinf(w):
                continue
            nd = d + w
            if nd < dist[v]:
                dist[v] = nd
                heapq.heappush(heap, (nd, v))
    return dist


def _normalize_city_name(value: str) -> str:
    # Normalize for user-provided start/end vs. itinerary distance_city strings
    return value.strip().lower().replace(", switzerland", "")


def _check_no_revisit(day_plans: Sequence[DayPlan], start_city: str, end_city: str) -> List[str]:
    # Allow multiple consecutive days in same city (one visit block).
    # Disallow a city appearing in non-consecutive blocks. If start==end,
    # allow exactly two blocks for the start city (at the beginning and end).
    blocks: Dict[str, List[Tuple[int, int]]] = {}
    prev = None
    block_start = 1
    for idx, dp in enumerate(day_plans, start=1):
        cur = dp.distance_city
        if prev is None:
            prev = cur
            continue
        if cur != prev:
            # close previous block
            blocks.setdefault(prev, []).append((block_start, idx - 1))
            block_start = idx
            prev = cur
    if prev is not None:
        blocks.setdefault(prev, []).append((block_start, len(day_plans)))

    violations: List[str] = []
    start_norm = _normalize_city_name(start_city)
    end_norm = _normalize_city_name(end_city)
    loop_trip = start_norm == end_norm

    for city, blist in blocks.items():
        if len(blist) <= 1:
            continue
        city_norm = _normalize_city_name(city)
        if loop_trip and city_norm == start_norm:
            # allow two blocks if first block starts at day 1 and last block ends at last day
            if len(blist) == 2 and blist[0][0] == 1 and blist[-1][1] == len(day_plans):
                continue
        violations.append(city)
    return violations


def evaluate_itinerary(
    day_plans: Sequence[DayPlan],
    start_city: str,
    end_city: str,
    interests: Mapping[str, float],  # percentages summing to 100 or proportions summing to 1
    mtu: int,
    season: str,
    distances_path: Path = DEFAULT_DIST_PATH,
) -> ScoreBreakdown:
    """
    Evaluate a complete itinerary according to the latest rules.

    Returns a ScoreBreakdown with total (0–100), per-component scores (0–1),
    and a list of hard-constraint violations (empty when valid).
    """
    violations: List[str] = []

    if not day_plans:
        return ScoreBreakdown(total=0.0, components={}, hard_violations=("empty itinerary",))

    days = len(day_plans)

    # Hard constraints
    # Day 1 city and last day city
    first_city = day_plans[0].distance_city
    last_city = day_plans[-1].distance_city
    if _normalize_city_name(first_city) != _normalize_city_name(start_city):
        violations.append("day 1 not in start city")
    if _normalize_city_name(last_city) != _normalize_city_name(end_city):
        violations.append("last day not in end city")

    # No revisits (with loop-trip exception for start city)
    revisit_violations = _check_no_revisit(day_plans, start_city, end_city)
    if revisit_violations:
        violations.append("revisited cities: " + ", ".join(sorted(set(revisit_violations))))

    # Per-day TU and season check
    all_pois: List = []
    per_day_tu: List[int] = []
    per_day_minutes: List[float] = []

    for dp in day_plans:
        # Season hard check: all POIs must be in season
        for poi in dp.pois:
            if not _is_in_season(poi, season):
                violations.append(f"POI out of season: {poi.name}")
        travel_tu = _travel_time_units(dp.travel_minutes)
        activity_tu = sum(_activity_time_units(p) for p in dp.pois)
        tu_d = travel_tu + activity_tu
        if tu_d > mtu:
            violations.append(
                f"day TU exceeds MTU: {dp.display_city} TU={tu_d} MTU={mtu}"
            )
        per_day_tu.append(tu_d)
        per_day_minutes.append(float(dp.travel_minutes or 0.0))
        all_pois.extend(dp.pois)

    if violations:
        return ScoreBreakdown(total=0.0, components={}, hard_violations=tuple(violations))

    # Components
    components: Dict[str, float] = {}

    # 1) Interest matching
    N = len(all_pois)
    desired_total = float(sum(interests.get(k, 0.0) for k in CATEGORIES))
    if desired_total <= 0:
        # Fallback to uniform if user provided zeros
        target = {k: 1.0 / len(CATEGORIES) for k in CATEGORIES}
    else:
        target = {k: float(interests.get(k, 0.0)) / desired_total for k in CATEGORIES}

    counts: Dict[str, int] = {k: 0 for k in CATEGORIES}
    for poi in all_pois:
        label = _primary_label(poi)
        if label in counts:
            counts[label] += 1

    if N <= 0:
        s_interest = 0.0
    else:
        per_label_scores = []
        for c in CATEGORIES:
            p_hat = counts[c] / N if N else 0.0
            denom = max(target[c], 1.0 / N)
            s_c = max(0.0, 1.0 - abs(p_hat - target[c]) / denom)
            per_label_scores.append(s_c)
        s_interest = sum(per_label_scores) / len(CATEGORIES)
    components["interest_matching"] = s_interest

    # 2) City visit efficiency (unique cities within trip length)
    unique_cities = []  # preserve order of first appearance
    seen = set()
    for dp in day_plans:
        if dp.distance_city not in seen:
            unique_cities.append(dp.distance_city)
            seen.add(dp.distance_city)
    U = len(unique_cities)
    target_cities = 1 + min(days, 8)
    denom = max(1, target_cities - 1)
    s_city = (max(0, U - 1)) / denom
    s_city = min(1.0, s_city)
    components["city_visit_efficiency"] = s_city

    # 3) Geographic coverage (average sqrt(normalized distance from start))
    graph = _load_distance_graph(distances_path)
    start_key = day_plans[0].distance_city  # use itinerary's canonical city key
    sp = _dijkstra(start_key, graph)
    # Exclude start city from coverage
    other_cities = [c for c in seen if _normalize_city_name(c) != _normalize_city_name(start_city)]
    # Compute M_max over all reachable cities from start in the graph
    finite_dists = [v for v in sp.values() if not math.isinf(v)]
    M_max = max(finite_dists) if finite_dists else 1.0
    cover_vals: List[float] = []
    for c in other_cities:
        minutes = sp.get(c, math.inf)
        if math.isinf(minutes) or M_max <= 0:
            continue
        d_norm = max(0.0, min(1.0, minutes / M_max))
        cover_vals.append(math.sqrt(d_norm))
    s_cover = (sum(cover_vals) / len(cover_vals)) if cover_vals else 0.0
    components["geographic_coverage"] = s_cover

    # 4) TU utilization (closeness to MTU)
    util_scores: List[float] = []
    for tu in per_day_tu:
        util_scores.append(max(0.0, 1.0 - abs(tu - mtu) / float(mtu)))
    s_tu = sum(util_scores) / len(util_scores) if util_scores else 0.0
    components["tu_utilization"] = s_tu

    # 5) Heavy penalty for long travel days (> 120 minutes)
    long_scores: List[float] = []
    for m in per_day_minutes:
        if m <= 120.0:
            long_scores.append(1.0)
        else:
            long_scores.append(math.exp(-((m - 120.0) / 30.0) ** 2))
    s_long = sum(long_scores) / len(long_scores) if long_scores else 0.0
    components["long_travel_penalty"] = s_long

    # Total score (0–100) with weights
    total = 100.0 * (
        0.35 * components["interest_matching"]
        + 0.20 * components["tu_utilization"]
        + 0.15 * components["city_visit_efficiency"]
        + 0.15 * components["geographic_coverage"]
        + 0.15 * components["long_travel_penalty"]
    )

    return ScoreBreakdown(total=total, components=components, hard_violations=tuple(violations))


__all__ = [
    "ScoreBreakdown",
    "evaluate_itinerary",
]

