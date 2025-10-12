#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import glob
import os
import re
import hashlib
from pathlib import Path

# Resolve paths relative to this script (…/src/data_parser.py -> project root)
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent

INPUT_GLOB = str(PROJECT_ROOT / "data" / "*_attractions.json")
OUTPUT_FILE = PROJECT_ROOT / "data" / "out" / "combined_pois.json"

SEASON_ORDER = ["summer", "winter", "autumn", "spring"]
SEASON_KEYS = set(SEASON_ORDER)

LAKE_HINTS = ["atthelake", "lake", "see", "lac", "lago", "lakeside", "ufer", "strandbad", "beach"]
MOUNTAIN_HINTS = ["inthemountains", "mountain", "peak", "summit", "alp", "alps", "kulm", "gipfel", "berg", "mountainview", "funicular", "cable", "gondola"]
HERITAGE_HINTS = ["unesco", "world heritage", "heritage", "weltkulturerbe", "patrimoine"]

def safe_get(d, *keys, default=None):
    cur = d
    for k in keys:
        if isinstance(cur, dict) and k in cur:
            cur = cur[k]
        else:
            return default
    return cur

def flatten_address(addr_obj):
    if not isinstance(addr_obj, dict):
        return None
    parts = []
    for k in ("name", "streetAddress", "postalCode", "addressLocality", "addressRegion", "addressCountry"):
        v = addr_obj.get(k)
        if v:
            parts.append(str(v))
    return ", ".join(parts) if parts else None

def first_address(address_list):
    if not address_list or not isinstance(address_list, list):
        return None, None
    chosen = None
    for a in address_list:
        if isinstance(a, dict) and (a.get("contactType") or a.get("addressLocality")):
            chosen = a
            break
    if chosen is None:
        chosen = address_list[0] if isinstance(address_list[0], dict) else None
    return flatten_address(chosen), safe_get(chosen, "addressLocality", default=None)

def get_classification_values(item, key_name):
    result = []
    for c in item.get("classification", []) or []:
        if isinstance(c, dict) and c.get("name") == key_name:
            for v in c.get("values") or []:
                if isinstance(v, dict):
                    if v.get("name"):
                        result.append(str(v["name"]).lower())
                    elif v.get("title"):
                        result.append(str(v["title"]).lower())
    return result

def text_blob(item):
    fields = []
    for k in ("name", "abstract", "description"):
        v = item.get(k)
        if v and isinstance(v, str):
            fields.append(v)
    return " ".join(fields).lower()

def filename_city_hint(path):
    base = os.path.basename(path)
    m = re.match(r"(.+?)_attractions\.json$", base, flags=re.IGNORECASE)
    return m.group(1) if m else None

def choose_season(item):
    seasons = [s for s in get_classification_values(item, "seasons") if s in SEASON_KEYS]
    if not seasons:
        blob = text_blob(item)
        if any(w in blob for w in ["ski", "snow", "sledg", "snowshoe", "winter"]):
            return "winter"
        if any(w in blob for w in ["hike", "swim", "lake", "boat", "summer"]):
            return "summer"
        if "autumn" in blob or "fall" in blob:
            return "autumn"
        if "spring" in blob:
            return "spring"
        return "summer"
    for s in SEASON_ORDER:
        if s in seasons:
            return s
    return seasons[0]

def bool_from_hints(item, classification_keys, hint_words):
    for key in classification_keys:
        vals = get_classification_values(item, key)
        for v in vals:
            if any(h in v for h in hint_words):
                return True
    blob = text_blob(item)
    if any(h in blob for h in hint_words):
        return True
    return False

def is_lake(item):
    return bool_from_hints(item, ["geographicallocations", "wellnesstype", "views", "naturetype"], LAKE_HINTS)

def is_mountain(item):
    return bool_from_hints(item, ["geographicallocations", "views", "toursandsightseeingtype", "transporttype"], MOUNTAIN_HINTS)

def is_heritage(item):
    if bool_from_hints(item, ["experiencetype", "museumtype"], HERITAGE_HINTS):
        return True
    return any(h in text_blob(item) for h in HERITAGE_HINTS)

def stable_id(item, city_fallback):
    src_id = item.get("identifier")
    if src_id:
        return src_id
    basis = (item.get("name") or "").strip() + "|" + (city_fallback or "")
    return hashlib.sha1(basis.encode("utf-8")).hexdigest()[:16]

def extract_city(item, file_city_hint=None):
    address = item.get("address") or []
    _, locality = first_address(address)
    city = (locality or file_city_hint or "").strip()
    return city

def extract_address(item):
    address = item.get("address") or []
    line, _ = first_address(address)
    return line or ""

def normalize_poi(item, city_hint=None):
    city = extract_city(item, city_hint)
    return {
        "id": stable_id(item, city),
        "name": item.get("name") or "",
        "city": city,
        "address": extract_address(item),
        "lake": bool(is_lake(item)),
        "mountain": bool(is_mountain(item)),
        "heritage": bool(is_heritage(item)),
        "season": choose_season(item),
    }

def main():
    files = sorted(glob.glob(INPUT_GLOB))
    if not files:
        print(f"No input files matched {INPUT_GLOB}")
        return

    # Ensure output directory exists
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    output = []
    seen = set()

    for path in files:
        try:
            with open(path, "r", encoding="utf-8") as f:
                payload = json.load(f)
        except Exception as e:
            print(f"⚠️ Skipping {path}: {e}")
            continue

        file_city = filename_city_hint(path)
        items = payload.get("data") or []
        for it in items:
            poi = normalize_poi(it, file_city)
            key = (poi["id"], poi["name"].lower(), poi["city"].lower())
            if key in seen:
                continue
            seen.add(key)
            output.append(poi)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"✅ Wrote {len(output)} POIs to {OUTPUT_FILE}")
    cities = sorted({p["city"] for p in output if p["city"]})
    if cities:
        print(f"Cities covered: {', '.join(cities)}")

if __name__ == "__main__":
    main()
