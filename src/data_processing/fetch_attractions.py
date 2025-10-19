#!/usr/bin/env python3

"""Download complete attraction datasets for selected Swiss cities."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

import requests

API_KEY = "mxSMOFbLwZ5yvrHrIWp94au6mxgkqZmI9aUiZ6wI"

BASE_URL = "https://opendata.myswitzerland.io/v1/attractions/"

COMMON_PARAMS: Dict[str, str] = {
    "lang": "en",
    "hitsPerPage": "50",
    "facets": "*",
    "facets.translate": "true",
    "expand": "true",
    "striphtml": "true",
    "top": "false",
}

# Mapping of output slug -> API query string.
CITY_QUERIES: Dict[str, str] = {
    # "zurich": "Zurich",
    # "lucerne": "Luzern",  # API results cover Lucerne attractions
    # "geneva": "Geneva",
    # "bern": "Bern",
    # "interlaken": "Interlaken",
    "lausanne": "Lausanne",
    # "montreux": "Montreux",
    # "appenzell": "Appenzell",
    # "lugano": "Lugano",
    "sion": "Sion",
    "st_gallen": "St. Gallen",
    "st_moritz": "St. Moritz",
    "kandersteg": "Kandersteg",
    # "schwyz": "Schwyz",
    # "zermatt": "Zermatt",
}

OUTPUT_DIR = Path("/Users/yuanyusi/Desktop/CS3263/project/SwissTravelPlan/data/in")

# Additional icon-specific queries to ensure signature attractions are captured.
ICON_QUERIES: Dict[str, List[str]] = {
    # "zurich": [
    #     "Kunsthaus Zürich",
    #     "Swiss National Museum",
    #     "Lindenhof",
    #     "Uetliberg",
    # ],
    # "lucerne": [
    #     "Chapel Bridge",
    #     "Kapellbrücke",
    #     "Lion Monument",
    #     "Mount Rigi",
    #     "Lake Lucerne",
    #     "Old Town of Lucerne",
    #     "Swiss Museum of Transport",
    # ],
    # "geneva": [
    #     "Palais des Nations",
    #     "United Nations Office at Geneva",
    # ],
    "lausanne": [
        "Olympic Museum",
        "Lausanne Cathedral",
        "Collection de l'Art Brut",
    ],
    # "montreux": [
    #     "Chillon Castle",
    #     "Château de Chillon",
    # ],
    # "appenzell": [
    #     "Seealpsee",
    #     "Aescher",
    #     "Appenzeller Schaukaserei",
    # ],
    # "lugano": [
    #     "Monte Brè",
    #     "Parco Ciani",
    #     "Gandria",
    #     "LAC Lugano",
    # ],
    "sion": [
        "Valère Basilica",
        "Tourbillon Castle",
    ],
    "st_gallen": [
        "Abbey Library of Saint Gall",
        "Stiftsbibliothek St. Gallen",
        "Textilmuseum St. Gallen",
    ],
    "st_moritz": [
        "Corviglia",
        "Muottas Muragl",
        "Lake St. Moritz",
    ],
    "kandersteg": [
        "Oeschinen Lake",
        "Blausee",
        "Gemmi Pass",
    ],
    "schwyz": [
        "Einsiedeln Monastery",
        "Swiss Knife Valley",
    ],
}


def fetch_all_pages(query: str) -> Tuple[List[dict], dict, dict]:
    """Fetch every page for the given query."""

    collected: List[dict] = []
    last_meta: dict = {}
    last_links: dict = {}

    page = 0
    total_expected: int | None = None
    total_pages: int | None = None

    while True:
        params = {**COMMON_PARAMS, "query": query, "page": str(page)}
        response = requests.get(
            BASE_URL,
            params=params,
            headers={"accept": "application/json", "x-api-key": API_KEY},
            timeout=30,
        )
        response.raise_for_status()

        payload = response.json()
        data = payload.get("data", [])
        meta = payload.get("meta", {})
        links = payload.get("links", {})

        page_info = meta.get("page", {})
        total_expected = total_expected or page_info.get("totalElements")
        total_pages = total_pages or page_info.get("totalPages")

        collected.extend(data)
        last_meta = meta
        last_links = links

        # Exit once we've collected everything the API reports.
        if total_expected is not None and len(collected) >= total_expected:
            break

        if total_pages is not None and page >= total_pages - 1:
            break

        page += 1
        time.sleep(0.25)

    return collected, last_meta, last_links


def fetch_icons_for_city(slug: str) -> List[dict]:
    """Issue additional icon-specific searches and collect unique results."""

    targets = ICON_QUERIES.get(slug, [])
    if not targets:
        return []

    seen_ids = set()
    extra_results: List[dict] = []

    for term in targets:
        items, _, _ = fetch_all_pages(term)
        for item in items:
            identifier = item.get("identifier") or item.get("url")
            if not identifier:
                identifier = term + "|" + item.get("name", "")
            if identifier in seen_ids:
                continue
            seen_ids.add(identifier)
            extra_results.append(item)
    return extra_results


def save_payload(
    slug: str, data: Iterable[dict], meta: dict, links: dict
) -> Path:
    """Write the aggregated payload to disk and return the path."""

    items = list(data)
    total = len(items)

    page_info = meta.setdefault("page", {})
    page_info["size"] = total
    page_info["number"] = 0
    page_info["totalElements"] = total
    page_info["totalPages"] = 1

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT_DIR / f"{slug}_attractions.json"

    payload = {
        "meta": meta,
        "links": links,
        "data": items,
    }

    with out_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)

    return out_path


def main() -> None:
    for slug, query in CITY_QUERIES.items():
        print(f"Fetching attractions for {query}…")
        data, meta, links = fetch_all_pages(query)
        expected = meta.get("page", {}).get("totalElements")
        if expected is not None and len(data) != expected:
            print(
                f"⚠️  Warning: expected {expected} records for {query}, "
                f"collected {len(data)}"
            )

        icons = fetch_icons_for_city(slug)
        if icons:
            print(f"  ↳ Merging {len(icons)} icon-specific items for {slug}")

        # Merge while avoiding duplicates by identifier/name combo.
        seen_keys = set()
        merged: List[dict] = []

        def add_items(items: Iterable[dict]) -> None:
            for item in items:
                identifier = item.get("identifier") or ""
                name = (item.get("name") or "").strip().lower()
                key = (identifier, name)
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                merged.append(item)

        add_items(data)
        add_items(icons)

        out_path = save_payload(slug, merged, meta, links)
        print(f"  → Saved {len(merged)} items to {out_path}")


if __name__ == "__main__":
    main()
