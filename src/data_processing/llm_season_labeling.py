"""
Infer seasonal suitability for each POI using the OpenAI API.

Reads POIs from ``data/out/selected_city_pois_llm_labeled.json`` and writes an
enriched list where ``season`` is a list of applicable seasons (spring, summer,
autumn, winter) with an accompanying ``season_reason`` explaining the choice to
``data/out/selected_city_pois_llm_season_labeled.json``.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Dict, Iterable

from openai import OpenAI

INPUT_PATH = Path("data/out/selected_city_pois_llm_labeled.json")
OUTPUT_PATH = Path("data/out/selected_city_pois_llm_season_labeled.json")

SEASON_OPTIONS = ("spring", "summer", "autumn", "winter")

PROMPT_TEMPLATE = """You are a Swiss travel planning expert.

Determine all realistic seasons for the attraction below. Consider climate,
accessibility (mountain passes, lake navigation, etc.), and any clues in the
description. Pay close attention to the classification array—many categories
indicate seasonal availability (e.g., ski areas, Christmas markets, summer-only
lakes). Ignore the existing season field; it is unreliable. Recommend a season
only when the experience is genuinely practical: keep Christmas to winter,
limit high-alpine hikes or exposed routes to the safe months, and highlight true
year-round experiences only when the description supports it (e.g., indoor
museums, some safe photo spot).

Return a JSON object on a single line with this schema:
{{
  "season": ["<season1>", "<season2>", ...],
  "season_reason": "<one concise sentence explaining the choice>"
}}

Rules for the season list:
- Allowed values: spring, summer, autumn, winter.
- Only include seasons that are clearly supported by the text or common sense;
  do not default to all four unless truly justified.
- No duplicates; order by most suitable first.
- Never output an empty list.

Do not include extra keys or narration.

POI DATA:
{context}
"""


def load_client() -> OpenAI:
    return OpenAI(api_key="")


def build_context(poi: Dict) -> str:
    fields = {
        "name": poi.get("name"),
        "city": poi.get("city"),
        "abstract": poi.get("abstract"),
        "description": poi.get("description"),
        "classification": poi.get("classification"),
    }
    return json.dumps(fields, ensure_ascii=False, indent=2)


def normalise_season(value: str) -> str:
    candidate = value.strip().lower()
    if candidate not in SEASON_OPTIONS:
        raise ValueError(f"Invalid season returned by model: {value}")
    return candidate


def normalise_season_list(value) -> list[str]:
    if not isinstance(value, list):
        raise ValueError(f"Expected 'season' to be a list, got {type(value).__name__}")
    seen = set()
    ordered: list[str] = []
    for item in value:
        season = normalise_season(str(item))
        if season not in seen:
            seen.add(season)
            ordered.append(season)
    if not ordered:
        raise ValueError("Season list cannot be empty.")
    return ordered


def label_season(client: OpenAI, poi: Dict) -> Dict[str, str]:
    prompt = PROMPT_TEMPLATE.format(context=build_context(poi))
    response = client.chat.completions.create(
        model="gpt-4o",
        temperature=0,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": "Return compact JSON exactly matching the requested schema."},
            {"role": "user", "content": prompt},
        ],
    )

    payload = json.loads(response.choices[0].message.content)
    seasons = normalise_season_list(payload["season"])
    reason = str(payload.get("season_reason", "")).strip()
    if not reason:
        raise ValueError("season_reason missing from model response.")
    return {"season": seasons, "season_reason": reason}


def main() -> None:
    client = load_client()
    pois: Iterable[Dict] = json.loads(INPUT_PATH.read_text(encoding="utf-8"))
    enriched = []

    for idx, poi in enumerate(pois, start=1):
        labels = label_season(client, poi)
        enriched.append({**poi, **labels})
        seasons_text = ", ".join(labels["season"])
        print(f"[{idx}] {poi.get('name', 'Unknown')} -> {seasons_text} ({labels['season_reason']})")
        time.sleep(0.4)  # light pacing to avoid hitting rate limits

    OUTPUT_PATH.write_text(json.dumps(enriched, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
