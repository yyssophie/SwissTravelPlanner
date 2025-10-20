"""
Probabilistic POI selection logic driven by user preference weights.
"""

from __future__ import annotations

import random
import re
import sys
import unicodedata
from itertools import combinations
from pathlib import Path
import os
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

if __package__ is None or __package__ == "":
    CURRENT_DIR = Path(__file__).resolve().parent
    sys.path.append(str(CURRENT_DIR.parent))
    from data_store import CATEGORIES, POI, TravelDataStore  # type: ignore
else:
    from .data_store import CATEGORIES, POI, TravelDataStore


def _filter_pois_by_preferences(
    pois: Sequence[POI], preference_weights: Mapping[str, float]
) -> List[POI]:
    positive_categories = {
        category for category, weight in preference_weights.items() if weight > 0.0
    }
    if not positive_categories:
        raise ValueError("Preference weights must contain at least one positive entry.")
    zero_categories = {category for category in CATEGORIES if category not in positive_categories}

    return [
        poi
        for poi in pois
        if any(poi.has_label(category) for category in positive_categories)
        and not any(poi.has_label(category) for category in zero_categories)
    ]


def has_preferred_pois(
    pois: Sequence[POI],
    preference_weights: Mapping[str, float],
    season: Optional[str] = None,
) -> bool:
    filtered = _filter_pois_by_preferences(pois, preference_weights)
    if not season:
        return bool(filtered)
    return any(_is_in_season(poi, season) for poi in filtered)


def select_pois_for_day(
    pois: Sequence[POI],
    preference_weights: Mapping[str, float],
    travel_tu: int,
    rng: random.Random | None = None,
    season: Optional[str] = None,
) -> List[POI]:
    """Pick up to two POIs that fit within the TU limits while respecting preferences.

    Selection aims to maximise total daily TUs in the 6–8 range (including travel),
    without exceeding 8. Higher totals are preferred, then higher preference score,
    then better season alignment.
    """

    rng = rng or random.Random()
    debug = os.environ.get("PLANNER_DEBUG", "").lower() in {"1", "true", "yes", "on"}

    positive_categories = {
        category for category, weight in preference_weights.items() if weight > 0.0
    }
    zero_categories = {category for category in CATEGORIES if category not in positive_categories}

    eligible = list(_filter_pois_by_preferences(pois, preference_weights))
    if not eligible:
        return []

    # Precompute activity TU and primary labels for scoring.
    raw_info = []
    for poi in eligible:
        label = _primary_label(poi)
        if not label:
            continue
        raw_info.append((poi, label, _activity_time_units(poi)))

    if season:
        season_info = [info for info in raw_info if _is_in_season(info[0], season)]
        activity_info = season_info or raw_info
    else:
        activity_info = raw_info

    if not activity_info:
        return []

    max_tu = 8
    if travel_tu > max_tu:
        return []

    remaining_tu = max_tu - travel_tu
    combos: List[Tuple[Tuple[POI, ...], int, float, float]] = []

    # Debug accounting
    overflow_skips = 0
    similarity_skips = 0

    if travel_tu <= max_tu:
        combos.append((tuple(), travel_tu, 0.0, 0.0))

    def dfs(start_idx: int, chosen: List[POI], used_tu: int, pref_sum: float, season_sum: float) -> None:
        nonlocal overflow_skips, similarity_skips
        if chosen:
            combos.append((tuple(chosen), travel_tu + used_tu, pref_sum, season_sum))
        for i in range(start_idx, len(activity_info)):
            poi, label, tu = activity_info[i]
            if tu > remaining_tu - used_tu:
                # would exceed daily TU cap
                overflow_skips += 1
                continue
            if any(_are_similar(poi, existing) for existing in chosen):
                similarity_skips += 1
                continue
            dfs(
                i + 1,
                chosen + [poi],
                used_tu + tu,
                pref_sum + preference_weights.get(label, 0.0),
                season_sum + _season_score(poi, season),
            )

    if remaining_tu > 0 and activity_info:
        dfs(0, [], 0, 0.0, 0.0)

    if not combos:
        return []

    def combo_key(item: Tuple[Tuple[POI, ...], int, float, float]) -> Tuple[int, int, float, float]:
        combo, total, pref_score, season_score = item
        # Prefer totals in [6,8]; never exceed 8 by construction.
        meets_target = 1 if 6 <= total <= 8 else 0
        # Higher total TUs wins, then higher preference score, then better season fit.
        return (meets_target, total, pref_score, -season_score)

    best_key = None
    best_items: List[Tuple[Tuple[POI, ...], int, float, float]] = []

    for entry in combos:
        key = combo_key(entry)
        if best_key is None or key > best_key:
            best_key = key
            best_items = [entry]
        elif key == best_key:
            best_items.append(entry)

    chosen_combo = rng.choice(best_items)[0]

    if debug:
        # Build diagnostics
        def poi_labels(p: POI) -> List[str]:
            return [c for c in CATEGORIES if p.has_label(c)]

        total_pois = len(pois)
        eligible_count = len(eligible)
        in_season_count = len(activity_info)

        # Reasons for preference filtering
        zero_weight_blocked = []
        no_positive = []
        for poi in pois:
            has_positive = any(poi.has_label(c) for c in positive_categories)
            has_zero = any(poi.has_label(c) for c in zero_categories)
            if not has_positive:
                no_positive.append(poi.name)
            elif has_zero and poi not in eligible:
                zero_weight_blocked.append(poi.name)

        # Top candidate combos by key
        show = []
        for combo, total, pref_score, season_score in sorted(combos, key=combo_key, reverse=True)[:5]:
            show.append({
                "total_tu": total,
                "pref": round(pref_score, 3),
                "season": round(season_score, 3),
                "items": [p.name for p in combo],
            })

        print("[POI-SELECT] travelTU=", travel_tu,
              " total=", total_pois,
              " eligible=", eligible_count,
              " inSeasonUsed=", in_season_count,
              " overflowSkips=", overflow_skips,
              " similaritySkips=", similarity_skips,
        )
        if zero_weight_blocked:
            print("[POI-SELECT] blocked by zero-weight:", "; ".join(zero_weight_blocked[:10]))
        if no_positive:
            print("[POI-SELECT] no positive-category:", "; ".join(no_positive[:10]))
        print("[POI-SELECT] top combos:")
        for entry in show:
            print("  -", entry)
        print("[POI-SELECT] chosen:", [p.name for p in chosen_combo])

    return list(chosen_combo)



def select_pois_for_cities(
    datastore: TravelDataStore,
    cities: Iterable[str],
    preference_weights: Mapping[str, float],
    rng: random.Random | None = None,
    season: str | None = None,
) -> Dict[str, List[POI]]:
    """
    Apply the probabilistic selection to each requested city.

    Returns a mapping of city name (as provided) to the chosen POIs.
    """
    rng = rng or random.Random()
    itinerary: Dict[str, List[POI]] = {}

    for city in cities:
        city_pois = datastore.pois_for_city(city, season=season)
        if not city_pois:
            itinerary[city] = []
            continue
        # Use a seeded RNG per city for reproducibility if desired.
        city_rng = random.Random(rng.random())
        itinerary[city] = select_pois_for_day(
            city_pois,
            preference_weights,
            travel_tu=0,
            rng=city_rng,
            season=season,
        )

    return itinerary


_TOKEN_PATTERN = re.compile(r"[a-z0-9]+")
_STOPWORDS = {
    "the",
    "of",
    "and",
    "on",
    "in",
    "at",
    "lake",
    "mountain",
    "mount",
    "top",
    "adventure",
    "tour",
    "experience",
    "view",
    "platform",
    "glacier",
    "swiss",
    "switzerland",
}


def _are_similar(poi_a: POI, poi_b: POI) -> bool:
    tokens_a = _name_tokens(poi_a.name)
    tokens_b = _name_tokens(poi_b.name)
    if not tokens_a or not tokens_b:
        return False
    overlap = tokens_a & tokens_b
    if not overlap:
        return False
    return len(overlap) >= 2 or (len(overlap) == 1 and next(iter(overlap)) in {"jungfraujoch", "lucerne", "geneva", "zermatt"})


def _name_tokens(name: str) -> set[str]:
    normalized = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    tokens = {match.group(0) for match in _TOKEN_PATTERN.finditer(normalized.lower())}
    return {token for token in tokens if token not in _STOPWORDS}


def _primary_label(poi: POI) -> Optional[str]:
    for category in CATEGORIES:
        if poi.has_label(category):
            return category
    return None


def _activity_time_units(poi: POI) -> int:
    needed = (getattr(poi, "needed_time", None) or "").lower()
    if not needed:
        return 2
    if "4" in needed and "8" in needed:
        return 8
    if "2" in needed and "4" in needed:
        return 4
    if "1" in needed and "2" in needed:
        return 2
    if "less" in needed or "<" in needed:
        return 1
    return 2


def _season_score(poi: POI, season: Optional[str]) -> float:
    if season is None:
        return 0.0
    priority = poi.season_priority(season)
    if priority is None:
        return 5.0
    return float(priority)


def _is_in_season(poi: POI, season: Optional[str]) -> bool:
    if season is None:
        return True
    return poi.season_priority(season) is not None
