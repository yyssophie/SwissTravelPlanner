"""
Utilities for loading POIs and inter-city distances into structured objects.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Optional, Tuple


# Categories used throughout the planner. Centralising them here keeps ordering
# consistent between data loading and selection logic.
CATEGORIES = ("nature", "culture", "food", "sport")
SEASONS = ("spring", "summer", "autumn", "winter")


@dataclass(frozen=True)
class POI:
    """Represents a single point of interest with LLM-derived labels."""

    identifier: str
    name: str
    city: str
    abstract: Optional[str]
    description: Optional[str]
    photo: Optional[str]
    needed_time: Optional[str]
    seasons: Tuple[str, ...]
    season_reason: Optional[str]
    season_order: Mapping[str, int]
    labels: Mapping[str, bool]
    metadata: Mapping[str, object]

    def has_label(self, category: str) -> bool:
        """Return True if the POI satisfies the requested category."""
        return bool(self.labels.get(category, False))

    def season_priority(self, season: Optional[str]) -> Optional[int]:
        """Return the position (0-indexed) of the requested season, if present."""
        if season is None:
            return 0
        return self.season_order.get(season)


@dataclass(frozen=True)
class DistanceRecord:
    """Driving distance details between two cities."""

    distance_km: Optional[float]
    duration_minutes: Optional[float]
    status: str


class TravelDataStore:
    """
    Aggregates POIs and road distances for the travel planner.

    POIs are organised by lower-cased city names to allow case-insensitive lookups.
    Distances retain the original Google API keys but are searchable in a
    case-insensitive manner.
    """

    def __init__(
        self,
        pois_by_city: Mapping[str, Tuple[POI, ...]],
        distances: Mapping[str, Mapping[str, DistanceRecord]],
    ) -> None:
        self._pois_by_city = {city.lower(): tuple(pois) for city, pois in pois_by_city.items()}
        self._distances = {
            origin.lower(): {dest.lower(): record for dest, record in destinations.items()}
            for origin, destinations in distances.items()
        }

        seasons_present = {
            season
            for pois in self._pois_by_city.values()
            for poi in pois
            for season in poi.seasons
        }
        self._available_seasons = tuple(sorted(seasons_present)) if seasons_present else SEASONS

    @classmethod
    def from_files(
        cls,
        pois_path: Path = Path("data/out/selected_city_pois_llm_theme_labeled.json"),
        distances_path: Path = Path("data/out/google_city_distances.json"),
        season_path: Path = Path("data/out/selected_city_pois_llm_season_labeled.json"),
    ) -> "TravelDataStore":
        pois_data = json.loads(pois_path.read_text(encoding="utf-8"))
        season_lookup = _load_season_lookup(season_path) if season_path.exists() else {}
        city_accumulator: Dict[str, List[POI]] = {}

        reason_keys = {f"{category}_reason" for category in CATEGORIES}

        for entry in pois_data:
            labels = {category: bool(entry.get(category, False)) for category in CATEGORIES}
            needed_time = _extract_needed_time(entry)
            excluded_keys = {
                "identifier",
                "name",
                "city",
                "abstract",
                "description",
                "photo",
                "season",
                "season_reason",
            }
            excluded_keys.update(labels.keys())
            excluded_keys.update(reason_keys)
            metadata = {k: v for k, v in entry.items() if k not in excluded_keys}

            fallback_season, fallback_reason = season_lookup.get(entry["identifier"], (None, None))
            seasons = _parse_seasons(entry, fallback_season)
            season_reason = entry.get("season_reason") or fallback_reason
            season_order = {season: idx for idx, season in enumerate(seasons)}

            poi = POI(
                identifier=entry["identifier"],
                name=entry["name"],
                city=entry["city"],
                abstract=entry.get("abstract"),
                description=entry.get("description"),
                photo=entry.get("photo"),
                needed_time=needed_time,
                seasons=seasons,
                season_reason=season_reason,
                season_order=season_order,
                labels=labels,
                metadata=metadata,
            )

            city_lower = entry["city"].lower()
            city_accumulator.setdefault(city_lower, []).append(poi)

        distances_raw = json.loads(distances_path.read_text(encoding="utf-8"))
        distances_section = distances_raw.get("distances", {})
        distances: Dict[str, Dict[str, DistanceRecord]] = {}
        for origin, destinations in distances_section.items():
            distances[origin] = {}
            for dest, payload in destinations.items():
                distances[origin][dest] = DistanceRecord(
                    distance_km=payload.get("distance_km"),
                    duration_minutes=payload.get("duration_minutes"),
                    status=payload.get("status", "UNKNOWN"),
                )

        pois_by_city = {city: tuple(pois) for city, pois in city_accumulator.items()}

        return cls(pois_by_city=pois_by_city, distances=distances)

    def cities(self) -> Iterable[str]:
        """Return all city names available in the POI dataset."""
        return sorted(self._pois_by_city.keys())

    def seasons(self) -> Iterable[str]:
        """Return the seasons represented in the POI dataset."""
        return list(self._available_seasons)

    def pois_for_city(self, city: str, season: Optional[str] = None) -> List[POI]:
        """
        Return POIs for the provided city name (case-insensitive), optionally
        filtering by season. When a specific season is requested, POIs that
        explicitly list that season are prioritised by their order of suitability.
        """
        city_key = city.lower()
        candidates = list(self._pois_by_city.get(city_key, ()))
        if not candidates or season is None:
            return candidates

        season_key = self.normalize_season(season)
        prioritized: List[Tuple[int, POI]] = []
        others: List[POI] = []

        for poi in candidates:
            priority = poi.season_priority(season_key)
            if priority is not None:
                prioritized.append((priority, poi))
            else:
                others.append(poi)

        prioritized.sort(key=lambda item: item[0])
        ordered = [poi for _, poi in prioritized]
        ordered.extend(others)
        return ordered

    def distance_between(self, origin: str, destination: str) -> Optional[DistanceRecord]:
        """Return distance details between the given cities, if known."""
        return self._distances.get(origin.lower(), {}).get(destination.lower())

    @staticmethod
    def normalize_season(value: str | None) -> str:
        if value is None:
            raise ValueError("Season value cannot be None.")
        candidate = value.strip().lower()
        if candidate not in SEASONS:
            raise ValueError(f"Unsupported season '{value}'.")
        return candidate


def _extract_needed_time(entry: Mapping[str, object]) -> Optional[str]:
    for classification in entry.get("classification", []) or []:
        if not isinstance(classification, dict):
            continue
        if classification.get("name") != "neededtime":
            continue
        values = classification.get("values") or []
        if not values:
            return None
        first = values[0]
        if isinstance(first, dict):
            return first.get("title") or first.get("name")
        return str(first)
    return None


def _parse_seasons(entry: Mapping[str, object], fallback: Optional[object] = None) -> Tuple[str, ...]:
    seasons: List[str] = []
    raw_value = entry.get("season") if entry else None
    if isinstance(raw_value, str):
        seasons.append(raw_value.strip().lower())
    elif isinstance(raw_value, list):
        for item in raw_value:
            if isinstance(item, str):
                seasons.append(item.strip().lower())

    if not seasons:
        for classification in entry.get("classification", []) or []:
            if not isinstance(classification, dict):
                continue
            if classification.get("name") != "seasons":
                continue
            for value in classification.get("values") or []:
                if not isinstance(value, dict):
                    continue
                candidate = value.get("name") or value.get("title")
                if candidate:
                    seasons.append(str(candidate).strip().lower())
            if seasons:
                break

    if not seasons and fallback is not None:
        if isinstance(fallback, str):
            seasons.append(fallback.strip().lower())
        elif isinstance(fallback, list):
            for item in fallback:
                if isinstance(item, str):
                    seasons.append(item.strip().lower())

    normalized: List[str] = []
    for season in seasons:
        lowered = season.lower()
        if lowered in SEASONS and lowered not in normalized:
            normalized.append(lowered)
    return tuple(normalized)


def _load_season_lookup(path: Path) -> Dict[str, Tuple[Optional[object], Optional[str]]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    lookup: Dict[str, Tuple[Optional[object], Optional[str]]] = {}
    for entry in data:
        identifier = entry.get("identifier")
        if not identifier:
            continue
        lookup[identifier] = (entry.get("season"), entry.get("season_reason"))
    return lookup
