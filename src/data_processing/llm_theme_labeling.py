"""
Reclassify POIs into nature, culture, food, and sport themes via OpenAI.

Reads `data/out/selected_city_pois_llm_season_labeled.json`, removes the legacy
lake/mountain/culture/food/sport flags and season labels, and writes a new file
with refreshed theme tags and concise rationales for each category.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Dict, Iterable

from openai import OpenAI

INPUT_PATH = Path("data/out/selected_city_pois_llm_season_labeled.json")
OUTPUT_PATH = Path("data/out/selected_city_pois_llm_theme_labeled.json")

THEME_PROMPT = """You are labelling Swiss travel attractions for four themes.

Use the POI's name, abstract, description, and classification tags to decide if
each theme applies. Interpret the themes as follows:
- nature: scenic viewpoints, natural trails, hikes, waterfalls, lake cruises,
          and mountain or cable-car experiences focused on landscape.
- culture: museums, castles, churches, historic architecture, guided city
           tours, cultural performances, or government buildings such as
           parliaments, spa
- food: vineyards, wine tastings, chocolate or cheese experiences, fondue,
        culinary workshops, markets, or dining specifically highlighted.
- sport: explicit athletic or adventure activities (skiing, snowboarding,
         paragliding, canyoning, climbing, biking, water sports, etc.).
         Hiking alone stays under nature; label sport only when an activity is
         clearly athletic or adrenaline-focused.

Treat any spa or wellness-focused experiences as culture. Exactly one theme
must be marked true—the single best fit for the experience. Set the other three
themes to false and provide a concise reason for each decision. 
If an attraction does not perfectly match any theme, choose the
closest fit rather than leaving multiple true values or all false.

Return compact JSON with keys:
  nature, nature_reason,
  culture, culture_reason,
  food, food_reason,
  sport, sport_reason.
"""

THEME_ORDER = ["culture", "nature", "food", "sport"]

THEME_KEYWORDS = {
    "nature": [
        "lake",
        "lakeshore",
        "mountain",
        "alps",
        "trail",
        "hike",
        "hiking",
        "panorama",
        "viewpoint",
        "scenic",
        "cable car",
        "funicular",
        "waterfall",
        "glacier",
        "valley",
        "forest",
        "park",
        "nature",
        "outdoor",
        "oeschinen",
    ],
    "culture": [
        "museum",
        "castle",
        "church",
        "cathedral",
        "monastery",
        "abbey",
        "heritage",
        "historic",
        "architecture",
        "art",
        "gallery",
        "palace",
        "parliament",
        "government",
        "old town",
        "tour",
        "guided tour",
        "monument",
        "opera",
        "library",
        "spa",
        "wellness",
        "thermal",
        "culture",
    ],
    "food": [
        "chocolate",
        "cheese",
        "fondue",
        "wine",
        "vineyard",
        "tasting",
        "culinary",
        "restaurant",
        "dining",
        "gastronomy",
        "brewery",
        "market",
        "coffee",
        "café",
        "distillery",
        "food",
    ],
    "sport": [
        "ski",
        "snowboard",
        "sledge",
        "sled",
        "paraglid",
        "paragliding",
        "canyon",
        "canyoning",
        "climb",
        "climbing",
        "bike",
        "biking",
        "cycling",
        "mountain bike",
        "golf",
        "kayak",
        "canoe",
        "rafting",
        "zipline",
        "via ferrata",
        "adventure",
        "adrenaline",
        "sport",
    ],
}

THEME_REASON_TEMPLATES = {
    "nature": "The attraction centres on natural scenery or outdoor landscapes.",
    "culture": "The experience highlights cultural, architectural, or heritage elements.",
    "food": "The highlight is a culinary experience focused on local flavours or tastings.",
    "sport": "The main appeal is an active or adventure-driven sporting activity.",
}


def load_client() -> OpenAI:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("Please set the OPENAI_API_KEY environment variable.")
    return OpenAI(api_key=api_key)


def read_pois(path: Path) -> Iterable[Dict]:
    return json.loads(path.read_text(encoding="utf-8"))


def drop_legacy_labels(poi: Dict) -> Dict:
    cleaned = dict(poi)
    for key in (
        "lake",
        "lake_reason",
        "mountain",
        "mountain_reason",
        "culture",
        "culture_reason",
        "food",
        "food_reason",
        "sport",
        "sport_reason",
        "season",
        "season_reason",
    ):
        cleaned.pop(key, None)
    return cleaned


def classify_theme(client: OpenAI, poi: Dict) -> Dict:
    context = json.dumps(
        {
            "name": poi.get("name"),
            "city": poi.get("city"),
            "abstract": poi.get("abstract"),
            "description": poi.get("description"),
            "classification": poi.get("classification"),
        },
        ensure_ascii=False,
        indent=2,
    )
    reminder = ""
    payload: Dict | None = None

    for attempt in range(3):
        prompt = f"""{THEME_PROMPT}{reminder}

POI DATA:
{context}
"""
        response = client.chat.completions.create(
            model="gpt-4o",
            temperature=0,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": "Return valid JSON matching the requested keys."},
                {"role": "user", "content": prompt},
            ],
        )
        payload = json.loads(response.choices[0].message.content)

        bool_keys = ("nature", "culture", "food", "sport")
        true_count = sum(bool(payload.get(key)) for key in bool_keys)
        if true_count == 1:
            break

        reminder = "\n\n⚠️ Exactly ONE theme may be true. Re-evaluate and answer again."

    return enforce_single_theme(poi, payload or {})


def enforce_single_theme(poi: Dict, payload: Dict) -> Dict:
    bool_keys = ("nature", "culture", "food", "sport")
    true_keys = [key for key in bool_keys if bool(payload.get(key))]

    chosen = select_theme(poi, true_keys)

    for key in bool_keys:
        payload[key] = key == chosen
        reason_key = f"{key}_reason"
        existing_reason = str(payload.get(reason_key, "") or "").strip()
        if key == chosen:
            if not existing_reason or "not" in existing_reason.lower():
                payload[reason_key] = THEME_REASON_TEMPLATES[key]
        else:
            if not existing_reason:
                payload[reason_key] = f"The experience is primarily {chosen}, so it is not categorised as {key}."
            elif key in true_keys and key != chosen:
                payload[reason_key] = f"The experience aligns more with {chosen} than {key}."

    return payload


def select_theme(poi: Dict, candidates: list[str]) -> str:
    text = extract_text(poi)
    if "spa" in text or "wellness" in text or "thermal" in text:
        return "culture"

    return heuristic_theme_selection(text, candidates)


def heuristic_theme_selection(text: str, candidates: list[str]) -> str:
    ordered_candidates: list[str] = []
    for theme in candidates:
        if theme in THEME_ORDER and theme not in ordered_candidates:
            ordered_candidates.append(theme)

    if not ordered_candidates:
        ordered_candidates = THEME_ORDER.copy()

    scores: Dict[str, int] = {}
    for theme in ordered_candidates:
        keywords = THEME_KEYWORDS.get(theme, [])
        scores[theme] = sum(1 for keyword in keywords if keyword in text)

    best_theme = max(
        ordered_candidates,
        key=lambda theme: (scores.get(theme, 0), -THEME_ORDER.index(theme)),
    )

    if scores.get(best_theme, 0) == 0:
        return ordered_candidates[0]

    return best_theme


def extract_text(poi: Dict) -> str:
    parts: list[str] = []
    for key in ("name", "city", "abstract", "description"):
        value = poi.get(key)
        if isinstance(value, str):
            parts.append(value.lower())

    classification = poi.get("classification")
    if isinstance(classification, list):
        for entry in classification:
            if not isinstance(entry, dict):
                continue
            title = entry.get("title")
            name = entry.get("name")
            if isinstance(title, str):
                parts.append(title.lower())
            if isinstance(name, str):
                parts.append(name.lower())
            values = entry.get("values")
            if isinstance(values, list):
                for item in values:
                    if isinstance(item, dict):
                        for sub_key in ("title", "name"):
                            sub_val = item.get(sub_key)
                            if isinstance(sub_val, str):
                                parts.append(sub_val.lower())
                    elif isinstance(item, str):
                        parts.append(item.lower())

    return " ".join(parts)


def main() -> None:
    client = load_client()
    pois = list(read_pois(INPUT_PATH))
    relabeled = []

    for index, poi in enumerate(pois, start=1):
        labels = classify_theme(client, poi)
        updated = {**drop_legacy_labels(poi), **labels}
        relabeled.append(updated)
        print(f"[{index}/{len(pois)}] {poi.get('name', 'Unknown')} -> {labels}")

    OUTPUT_PATH.write_text(json.dumps(relabeled, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {OUTPUT_PATH} with {len(relabeled)} records.")


if __name__ == "__main__":
    main()
