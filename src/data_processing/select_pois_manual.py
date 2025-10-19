"""
Build a curated POI list for the newly added cities based on manual picks.

The selections below were chosen to balance iconic attractions, variety across
the nature/culture/food/sport themes, and seasonal diversity where possible.
The script pulls the full attraction payloads from ``data/in`` and adds a
``city`` field before writing them to
``data/out/selected_city_pois_2.json``.
"""

from __future__ import annotations

import json
from pathlib import Path
import html
from typing import Dict, Iterable, List, Tuple

CITY_FILES: Dict[str, Path] = {
    "lausanne": Path("data/in/lausanne_attractions.json"),
    "kandersteg": Path("data/in/kandersteg_attractions.json"),
    "sion": Path("data/in/sion_attractions.json"),
    "st_gallen": Path("data/in/st_gallen_attractions.json"),
    "st_moritz": Path("data/in/st_moritz_attractions.json"),
}


def _normalise(value: str) -> str:
    unescaped = html.unescape(value)
    return " ".join(unescaped.split()).casefold()


def _key(city: str, name: str) -> Tuple[str, str]:
    return (city, _normalise(name))


SELECTIONS: Dict[str, List[str]] = {
    "lausanne": [
        "Lausanne à table",
        "Lavaux vineyards",
        "Lake Geneva Cruises",
        "Ouchy and its Lakeside Promenade",
        "Terrace bars with a view of Lake Geneva",
        "The Olympic Museum",
        "Collection de l'Art Brut",
        "Visit to a brewery",
        "Creative chocolate workshop",
        "Sauvabelin Park",
        "Botanical Garden",
        "Esplanade de Montbenon",
        "Palais de Rumine & Musée cantonal des Beaux-Arts",
        "AQUATIS: largest fresh water aquarium and vivarium in Europe",
        "Rolex Learning Center",
        "Shopping: Quartier du Flon",
        "Festival de la Cité",
        "Art in the city",
        "Sightseeing Flight",
        "The nightwatch",
    ],
    "kandersteg": [
        "Kandersteg-Allmenalp via ferrata",
        "Kandersteg: Railway Trail",
        "Through Kandersteg in a stagecoach",
        "Winter hike from Kandersteg-Sunnbüel to the Gemmi Pass",
        "Gondola to Lake Oeschinen",
        "Ice Fishing in Lake Oeschinen",
        "Spa in a forest clearing, Blausee",
        "Gemmipass",
        "Chluse Gorge",
        "Choleren Gorge",
        "Engstligenalp – and the Wildstrubel",
        "Engstligen waterfalls",
        "Hahnenmoos - Geils",
        "Kid’s Paradise Elsigenalp",
        "Adelboden mountain dairy",
        "Ricola Herb Garden",
        "Albert Schweitzer path",
        "Train Buffs' Hike: BLS Trail",
        "BLS Lötschberg mountain line",
        "Valley and high plateau cross-country trails",
    ],
    "sion": [
        "Underground lake of St-Leonard",
        "A great past at the crossroad of the alps",
        "Powerful Rhone",
        "\"Senses Trail\" - Direct contact with Nature",
        "Mauvoisin Dam",
        "Golf in the Valais region",
        "Evolène - A sports via ferrata",
        "Matterhorn Golf Club",
        "Liquid pleasure",
        "Piste Nationale",
        "Belvédère via ferrata",
        "Tourbillon Castle",
        "Valère Basilica",
    ],
    "st_gallen": [
        "Stiftsbibliothek (Abbey Library) St. Gallen",
        "Monastery Square",
        "Guided Tours of the Monatery",
        "Old City",
        "Textile trail St. Gallen",
        "St. Gallen Theatre",
        "St.Gallen Panorama Tour",
        "City Lounge - Red Square",
        "St.Gallen Sausage",
        "Discover the St. Gallen region's culinary side",
        "Chocolaterie am Klosterplatz",
        "House of Wine in the Rhine Valley",
        "Treetop path Neckertal",
        "Drei Weieren",
        "Hoher Kasten – Top of Appenzell",
        "Lake Fälen: Fascinating Alpstein-Fjord",
        "Water sports on Lake Constance",
        "Säntispark Olympics",
        "St.Gallen – city winter sports",
        "Textile Museum St. Gallen",
    ],
    "st_moritz": [
        "Bernina Express",
        "Glacier Express",
        "Olympic bob run in St. Moritz-Celerina",
        "St. Moritz - First ski experience",
        "Engadine St. Moritz – Switzerland’s cross-country paradise",
        "Piz Nair",
        "Diavolezza - Isola Pers – Morteratsch glacier",
        "Julier Pass Route",
        "Muottas Muragl",
        "Mountain dining at Muottas Muragl",
        "Tobogganing on Muottas Muragl",
        "Fatbiking",
        "Yoga Piste",
        "Ovaverva Indoor Pool, Spa & Sports Centre",
        "By foot to Heidi’s mountain hut",
        "Lej Nair and Lej dals Chöds",
        "Devil's Place Whiskey Bar",
        "Dine on the move",
        "Storia & Palazzi.",
        "Graubünden Paragliding",
    ],
}

SYNTHETIC_ENTRIES: Dict[Tuple[str, str], Dict] = {
    _key("lausanne", "The Olympic Museum"): {
        "@context": "https://schema.org/",
        "@type": "TouristAttraction",
        "identifier": "synthetic-olympic-museum",
        "name": "The Olympic Museum",
        "abstract": "Lausanne’s flagship museum celebrates the Olympic movement with immersive exhibits, athlete memorabilia, and interactive displays overlooking Lake Geneva.",
        "description": "Located in the Olympic Capital, The Olympic Museum guides visitors through the history and values of the Games. Multimedia galleries, temporary exhibitions and landscaped terraces bring athletes’ achievements to life while highlighting Lausanne’s global sporting role.",
        "url": "https://olympics.com/museum",
        "top": True,
        "classification": [
            {
                "@context": "https://myswitzerland.io/",
                "@type": "Classification",
                "name": "seasons",
                "values": [
                    {"name": "winter", "title": "Winter"},
                    {"name": "spring", "title": "Spring"},
                    {"name": "summer", "title": "Summer"},
                    {"name": "autumn", "title": "Autumn"},
                ],
            },
            {
                "@context": "https://myswitzerland.io/",
                "@type": "Classification",
                "name": "museumtype",
                "title": "Museum",
                "values": [
                    {"name": "history", "title": "History"},
                    {"name": "sport", "title": "Sport"},
                ],
            },
        ],
    },
    _key("lausanne", "Collection de l'Art Brut"): {
        "@context": "https://schema.org/",
        "@type": "TouristAttraction",
        "identifier": "synthetic-collection-art-brut",
        "name": "Collection de l'Art Brut",
        "abstract": "Jean Dubuffet’s renowned museum presents raw, self-taught artistry that challenges conventional notions of culture.",
        "description": "Lausanne’s Collection de l'Art Brut houses thousands of works by visionary outsiders—self-taught artists, psychiatric patients, and folk creators. Intimate galleries, rotating exhibitions and audio guides reveal the personal stories behind these powerful sculptures, drawings and assemblages.",
        "url": "https://www.artbrut.ch/",
        "classification": [
            {
                "@context": "https://myswitzerland.io/",
                "@type": "Classification",
                "name": "seasons",
                "values": [
                    {"name": "winter", "title": "Winter"},
                    {"name": "spring", "title": "Spring"},
                    {"name": "summer", "title": "Summer"},
                    {"name": "autumn", "title": "Autumn"},
                ],
            },
            {
                "@context": "https://myswitzerland.io/",
                "@type": "Classification",
                "name": "museumtype",
                "title": "Museum",
                "values": [
                    {"name": "art", "title": "Art"},
                ],
            },
        ],
    },
    _key("st_gallen", "Textile Museum St. Gallen"): {
        "@context": "https://schema.org/",
        "@type": "TouristAttraction",
        "identifier": "synthetic-textile-museum-st-gallen",
        "name": "Textile Museum St. Gallen",
        "abstract": "A neo-Renaissance palace showcasing eastern Switzerland’s embroidery legacy, couture lace, and contemporary textile design.",
        "description": "The Textile Museum illuminates St. Gallen’s storied fabric industry through shimmering embroidery, fashion archives, and hands-on exhibits. Permanent and temporary shows explore how craftsmanship and innovation shaped the city’s global reputation.",
        "url": "https://www.textilmuseum.ch/",
        "classification": [
            {
                "@context": "https://myswitzerland.io/",
                "@type": "Classification",
                "name": "seasons",
                "values": [
                    {"name": "winter", "title": "Winter"},
                    {"name": "spring", "title": "Spring"},
                    {"name": "summer", "title": "Summer"},
                    {"name": "autumn", "title": "Autumn"},
                ],
            },
            {
                "@context": "https://myswitzerland.io/",
                "@type": "Classification",
                "name": "museumtype",
                "title": "Museum",
                "values": [
                    {"name": "design", "title": "Design"},
                    {"name": "history", "title": "History"},
                ],
            },
        ],
    },
    _key("sion", "Tourbillon Castle"): {
        "@context": "https://schema.org/",
        "@type": "TouristAttraction",
        "identifier": "synthetic-tourbillon-castle",
        "name": "Tourbillon Castle",
        "abstract": "Medieval hilltop ruins overlooking Sion with sweeping views across the Rhône Valley and Valais vineyards.",
        "description": "Built in the 13th century for the Prince-Bishops of Sion, Tourbillon Castle crowns a dramatic rocky spur. Visitors explore chapel remains and defensive walls, pairing history with panoramic vistas opposite the Valère hill.",
        "url": "https://www.valais.ch/en/activities/culture/fortresses-castles/chateau-de-tourbillon",
        "classification": [
            {
                "@context": "https://myswitzerland.io/",
                "@type": "Classification",
                "name": "seasons",
                "values": [
                    {"name": "spring", "title": "Spring"},
                    {"name": "summer", "title": "Summer"},
                    {"name": "autumn", "title": "Autumn"},
                ],
            },
        ],
    },
    _key("sion", "Valère Basilica"): {
        "@context": "https://schema.org/",
        "@type": "TouristAttraction",
        "identifier": "synthetic-valere-basilica",
        "name": "Valère Basilica",
        "abstract": "Fortified hilltop basilica famed for its 15th-century organ and atmospheric Romanesque-Gothic interiors.",
        "description": "The Basilica of Our Lady of Valère crowns Sion’s second iconic hill. Cloisters, medieval murals and regular organ recitals trace eight centuries of ecclesiastical artistry, complementing the neighbouring Tourbillon Castle.",
        "url": "https://www.valais.ch/en/activities/culture/fortresses-castles/basilique-de-valere",
        "classification": [
            {
                "@context": "https://myswitzerland.io/",
                "@type": "Classification",
                "name": "seasons",
                "values": [
                    {"name": "winter", "title": "Winter"},
                    {"name": "spring", "title": "Spring"},
                    {"name": "summer", "title": "Summer"},
                    {"name": "autumn", "title": "Autumn"},
                ],
            },
            {
                "@context": "https://myswitzerland.io/",
                "@type": "Classification",
                "name": "achitekturtyp",
                "title": "Architecture",
                "values": [
                    {"name": "churches", "title": "Churches"},
                ],
            },
        ],
    },
}


def load_city_payload(path: Path) -> List[dict]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    data = raw.get("data")
    if not isinstance(data, list):
        raise ValueError(f"Expected attraction list in {path}, found {type(data).__name__}")
    return data


def build_selection() -> List[dict]:
    output: List[dict] = []

    for city, selections in SELECTIONS.items():
        payload_path = CITY_FILES[city]
        attractions = load_city_payload(payload_path)

        index = {_key(city, item.get("name", "")): item for item in attractions}

        for name in selections:
            key = _key(city, name)
            record = index.get(key)
            if record is None:
                synthetic = SYNTHETIC_ENTRIES.get(key)
                if synthetic is None:
                    raise KeyError(f"Could not find '{name}' in {payload_path.name}")
                enriched = dict(synthetic)
            else:
                enriched = dict(record)
            enriched["city"] = city
            output.append(enriched)

    return output


def main() -> None:
    selections = build_selection()
    output_path = Path("data/out/selected_city_pois_2.json")
    output_path.write_text(json.dumps(selections, ensure_ascii=False, indent=2), encoding="utf-8")

    city_counts: Dict[str, int] = {}
    for entry in selections:
        city_counts[entry["city"]] = city_counts.get(entry["city"], 0) + 1

    print(f"Wrote {len(selections)} POIs to {output_path}")
    for city, count in sorted(city_counts.items()):
        print(f"  {city}: {count} entries")


if __name__ == "__main__":
    main()
