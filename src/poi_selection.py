"""
Probabilistic POI selection logic driven by user preference weights.
"""

from __future__ import annotations

import random
import re
import sys
import unicodedata
from pathlib import Path
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
    pois: Sequence[POI], preference_weights: Mapping[str, float]
) -> bool:
    return bool(_filter_pois_by_preferences(pois, preference_weights))


def pick_two_pois_for_city(
    pois: Sequence[POI],
    preference_weights: Mapping[str, float],
    rng: random.Random | None = None,
    season: Optional[str] = None,
) -> List[POI]:
    """Randomly pick up to two POIs that satisfy the user's preferences."""
    rng = rng or random.Random()

    remaining_pois = list(_filter_pois_by_preferences(pois, preference_weights))
    chosen: List[POI] = []

    if not remaining_pois:
        return chosen

    weights = {}
    for cat in CATEGORIES:
        if preference_weights.get(cat, 0.0) <= 0.0:
            continue
        if any(poi.has_label(cat) for poi in remaining_pois):
            weights[cat] = float(preference_weights.get(cat, 0.0))
    total_weight = sum(weights.values())
    if total_weight <= 0.0:
        weights = {cat: 1.0 for cat in CATEGORIES if cat in preference_weights}
        total_weight = sum(weights.values())
        if total_weight <= 0.0:
            raise ValueError("Preference weights must contain at least one positive entry.")
    weights = {cat: w / total_weight for cat, w in weights.items()}

    for _ in range(min(2, len(remaining_pois))):
        available_weights = dict(weights)

        while available_weights and remaining_pois:
            categories, probs = zip(*available_weights.items())
            probs_total = sum(probs)
            probs = [p / probs_total for p in probs]

            label = rng.choices(categories, weights=probs, k=1)[0]
            matches = [poi for poi in remaining_pois if poi.has_label(label)]

            if matches:
                filtered_matches = _prioritise_by_season(matches, season)
                if not filtered_matches:
                    available_weights.pop(label, None)
                    continue

                distinct_matches = _exclude_similar(filtered_matches, chosen)
                if not distinct_matches:
                    available_weights.pop(label, None)
                    continue

                poi = rng.choice(distinct_matches)
                chosen.append(poi)
                remaining_pois.remove(poi)
                break

            available_weights.pop(label, None)
        else:
            fallback = [poi for poi in remaining_pois if not any(_are_similar(poi, other) for other in chosen)]
            pool = fallback or remaining_pois
            poi = rng.choice(pool)
            chosen.append(poi)
            remaining_pois.remove(poi)

    return chosen



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
        itinerary[city] = pick_two_pois_for_city(
            city_pois,
            preference_weights,
            rng=city_rng,
            season=season,
        )

    return itinerary


def _prioritise_by_season(
    candidates: Sequence[POI], season: Optional[str]
) -> List[POI]:
    if season is None:
        return list(candidates)

    ranked: List[Tuple[int, POI]] = []
    for poi in candidates:
        priority = poi.season_priority(season)
        if priority is not None:
            ranked.append((priority, poi))

    if not ranked:
        return []

    best_rank = min(priority for priority, _ in ranked)
    return [poi for priority, poi in ranked if priority == best_rank]


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


def _exclude_similar(candidates: Sequence[POI], chosen: Sequence[POI]) -> List[POI]:
    if not chosen:
        return list(candidates)
    return [poi for poi in candidates if not any(_are_similar(poi, other) for other in chosen)]


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
