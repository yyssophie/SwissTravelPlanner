"""
Estimate road travel distances between Swiss cities using the OpenAI API.

This script prompts an LLM to return driving-distance estimates (in kilometres)
for each pair of the ten cities defined in ``CITIES``. Results are collected in
an in-memory dictionary so they can be serialised or integrated elsewhere in
the project.

IMPORTANT: LLM answers are heuristic and should be validated against a routing
API (e.g., Google Maps, Mapbox, OpenRouteService) before relying on them in a
production workflow.
"""

from __future__ import annotations

import itertools
import json
import os
import time
from typing import Dict, Tuple

from openai import OpenAI  # pip install openai>=1.0.0

# Cities of interest. The human-readable label is used both for prompting and as
# the key in the resulting distance dictionary.
CITIES = [
    "Appenzell, Switzerland",
    "Bern, Switzerland",
    "Geneva, Switzerland",
    "Interlaken, Switzerland",
    "Lucerne, Switzerland",
    "Lugano, Switzerland",
    "Montreux, Switzerland",
    "Schwyz, Switzerland",
    "Zermatt, Switzerland",
    "Zurich, Switzerland",
]

# Construct the API client. Fails fast if the key is not available.
try:
    _api_key = ""
except KeyError as exc:  # pragma: no cover - explicit failure path
    raise RuntimeError(
        "Set the OPENAI_API_KEY environment variable before running this script."
    ) from exc

client = OpenAI(api_key=_api_key)

# Prompt template that forces a JSON-only response containing the distance
# (kilometres), a qualitative confidence score, and a short reasoning string.
PROMPT_TEMPLATE = """You are a Swiss travel routing specialist.

- Estimate the real-world driving distance by car between the two cities.
- Use current Swiss road knowledge (motorways, tunnels, passes).
- When unsure, make your best professional estimate rather than leaving blanks.

Respond with **only** valid JSON on one line, no prose.
Schema:
{{
  "distance_km": <number>,        # Driving distance rounded to one decimal place
  "confidence": "<low|medium|high>",
  "rationale": "<one concise sentence referencing key roads or geography>"
}}

City A: {origin}
City B: {destination}
"""


def fetch_distance(origin: str, destination: str) -> Tuple[float, Dict[str, str]]:
    """Query the LLM for the driving distance between two cities."""
    prompt = PROMPT_TEMPLATE.format(origin=origin, destination=destination)

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        temperature=0,
        messages=[
            {"role": "system", "content": "Return JSON that matches the requested schema."},
            {"role": "user", "content": prompt},
        ],
    )

    raw_content = response.choices[0].message.content.strip()
    payload = json.loads(raw_content)
    distance_km = float(payload["distance_km"])
    return distance_km, payload


def build_distance_matrix(pause_seconds: float = 0.5) -> Dict[str, Dict[str, float]]:
    """
    Request driving distances for each unordered city pair.

    The returned structure is a nested dictionary {origin: {destination: distance_km}}.
    Both directions are populated to make lookups straightforward.
    """
    matrix: Dict[str, Dict[str, float]] = {city: {} for city in CITIES}

    for origin, destination in itertools.combinations(CITIES, 2):
        distance_km, extra = fetch_distance(origin, destination)
        matrix[origin][destination] = distance_km
        matrix[destination][origin] = distance_km

        # Optionally log the reasoning for manual review.
        rationale = extra.get("rationale", "")
        confidence = extra.get("confidence", "unknown")
        print(
            f"{origin} → {destination}: {distance_km:.1f} km "
            f"(confidence: {confidence}; rationale: {rationale})"
        )

        # Gentle pacing to avoid rate limits.
        if pause_seconds:
            time.sleep(pause_seconds)

    return matrix


def main() -> None:
    distances = build_distance_matrix()
    # Example of how to persist the result.
    print(json.dumps(distances, indent=2))


if __name__ == "__main__":
    main()
