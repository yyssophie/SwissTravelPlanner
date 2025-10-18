"""
Estimate visit duration for POIs via LLM and add a needed-time classification.

For every POI in ``data/out/selected_city_pois_llm_season_labeled.json`` that
is missing a ``neededtime`` classification entry, query the OpenAI API to select
one of the canonical duration buckets and append the result to the
``classification`` array.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from openai import OpenAI

POI_PATH = Path("data/out/selected_city_pois_llm_season_labeled.json")


@dataclass(frozen=True)
class NeededTimeOption:
    slug: str
    title: str
    description: str


NEEDED_TIME_OPTIONS: List[NeededTimeOption] = [
    NeededTimeOption("lessthan1hour", "Less than 1 hour", "Brief photo stop or compact indoor site."),
    NeededTimeOption("between1to2hours", "1-2 hours", "Small museum, short walk, or single activity."),
    NeededTimeOption("2to4hourshalfday", "2 to 4 hours (half day)", "Multiple exhibits, longer tours, or activities requiring gear/transport."),
    NeededTimeOption("4to8hoursfullday", "4 to 8 hours (full day)", "Large outdoor excursions, ski days, extensive hikes or multi-stop experiences.")
]


PROMPT_TEMPLATE = """You are a Swiss travel planning expert.

Estimate the realistic amount of time a typical visitor should plan to spend at
the following point of interest. Consider the experience type, what the visitor
is expected to do on-site, accessibility logistics, and any recommendations in
the description. When unsure, default to the conservative amount of time that
lets a traveller enjoy the core highlights without rushing.

Choose exactly one option from the list below and output machine- and
human-readable values plus a short justification:
{options}

Return a compact JSON object on one line with this schema:
{{
  "slug": "<one of the option slugs>",
  "title": "<matching title>",
  "reason": "<succinct explanation referencing key details>"
}}

Only use the provided slugs and titles—do not invent new ones. The reason must
be a single sentence. Do not add extra keys or text.

POI DATA:
{context}
"""


def format_options() -> str:
    lines = []
    for option in NEEDED_TIME_OPTIONS:
        lines.append(f"- {option.slug}: {option.title} — {option.description}")
    return "\n".join(lines)


def build_context(poi: Dict) -> str:
    fields = {
        "identifier": poi.get("identifier"),
        "name": poi.get("name"),
        "city": poi.get("city"),
        "abstract": poi.get("abstract"),
        "description": poi.get("description"),
        "classification": poi.get("classification"),
    }
    return json.dumps(fields, ensure_ascii=False, indent=2)


def load_client() -> OpenAI:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY environment variable is not set.")
    return OpenAI(api_key=api_key)


def load_pois(path: Path) -> List[Dict]:
    return json.loads(path.read_text(encoding="utf-8"))


def has_needed_time(poi: Dict) -> bool:
    classifications = poi.get("classification")
    if not isinstance(classifications, list):
        return False
    return any(cls.get("name") == "neededtime" for cls in classifications if isinstance(cls, dict))


def call_model(client: OpenAI, poi: Dict) -> Dict[str, str]:
    prompt = PROMPT_TEMPLATE.format(options=format_options(), context=build_context(poi))
    response = client.chat.completions.create(
        model="gpt-4o",
        temperature=0,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": "Return valid JSON exactly matching the requested schema."},
            {"role": "user", "content": prompt},
        ],
    )
    payload = json.loads(response.choices[0].message.content)
    return {
        "slug": str(payload["slug"]).strip(),
        "title": str(payload["title"]).strip(),
        "reason": str(payload["reason"]).strip(),
    }


def find_option(slug: str, title: str) -> NeededTimeOption:
    slug_lower = slug.lower()
    title_normalized = title.strip().lower()
    for option in NEEDED_TIME_OPTIONS:
        if option.slug == slug_lower:
            return option
        if option.title.lower() == title_normalized:
            return option
    raise ValueError(f"Model returned unsupported option: slug={slug} title={title}")


def upsert_needed_time(poi: Dict, option: NeededTimeOption) -> None:
    classification = poi.setdefault("classification", [])
    if not isinstance(classification, list):
        raise TypeError("classification field must be a list when present")

    entry: Optional[Dict] = None
    for item in classification:
        if isinstance(item, dict) and item.get("name") == "neededtime":
            entry = item
            break

    values = [{"name": option.slug, "title": option.title}]

    if entry:
        entry["values"] = values
        entry.setdefault("@context", "https://myswitzerland.io/")
        entry.setdefault("@type", "Classification")
        entry.setdefault("title", "Needed time")
    else:
        classification.append(
            {
                "@context": "https://myswitzerland.io/",
                "@type": "Classification",
                "name": "neededtime",
                "title": "Needed time",
                "values": values,
            }
        )


def main() -> None:
    pois = load_pois(POI_PATH)
    client = load_client()

    missing_indices = [idx for idx, poi in enumerate(pois) if not has_needed_time(poi)]

    if not missing_indices:
        print("All POIs already contain neededtime classification. No work required.")
        return

    print(f"Labelling needed time for {len(missing_indices)} POIs...")

    for counter, idx in enumerate(missing_indices, start=1):
        poi = pois[idx]
        result = call_model(client, poi)
        option = find_option(result["slug"], result["title"])
        upsert_needed_time(poi, option)

        print(f"[{counter}/{len(missing_indices)}] {poi.get('name', 'Unknown')} -> {option.title} ({result['reason']})")
        time.sleep(0.5)

    POI_PATH.write_text(json.dumps(pois, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Updated {len(missing_indices)} POIs and wrote {POI_PATH}")


if __name__ == "__main__":
    main()
