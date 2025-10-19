import json
from pathlib import Path
from openai import OpenAI  # pip install openai>=1.0.0

# Use an environment variable or other secure method for your API key.
OpenAI(api_key=os.environ["OPENAI_API_KEY"])

INPUT = Path("data/out/selected_city_pois_simplify.json")
OUTPUT = Path("data/out/selected_city_pois_llm_labeled.json")

BASE_PROMPT = """
You are labeling Swiss points of interest for a travel planner. For each POI:
1. Use the “name”, “abstract”, “description”, and “classification” fields.
2. Decide the Boolean value of these categories and explain your decision:
   - lake: true only if the experience is on or directly uses a lake (boat trips, lakeside activities).
   - mountain: true only if the experience centres on alpine terrain, mountain transport or peaks.
   - culture: museums, churches, castles, guided city tours, architecture or other heritage/art content.
   - food: true only for explicit culinary experiences (fondue, chocolate tastings, vineyards, restaurants, etc.).
   - sport: true only for actual physical/adventure activities (hiking, skiing, via ferrata, rafting, paragliding, golf, etc.).
3. If a category is false, explain briefly why it does not apply.
Respond strictly in JSON with keys:
  lake, lake_reason, mountain, mountain_reason, culture, culture_reason,
  food, food_reason, sport, sport_reason.
"""

def classify_poi(poi):
    context = json.dumps(
        {
            "name": poi.get("name"),
            "abstract": poi.get("abstract"),
            "description": poi.get("description"),
            "classification": poi.get("classification"),
        },
        ensure_ascii=False,
        indent=2,
    )

    user_message = f"""{BASE_PROMPT.strip()}

POI DATA:
{context}
"""

    response = client.chat.completions.create(
        model="gpt-4o",
        temperature=0,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": "Return compact JSON only—no extra text."},
            {"role": "user", "content": user_message},
        ],
    )
    return json.loads(response.choices[0].message.content)

def main():
    pois = json.loads(INPUT.read_text(encoding="utf-8"))
    labeled = []

    for idx, poi in enumerate(pois, 1):
        labels = classify_poi(poi)
        labeled_record = {**poi, **labels}
        labeled.append(labeled_record)
        print(f"[{idx}/{len(pois)}] {poi.get('name', 'Unknown')} -> {json.dumps(labels, ensure_ascii=False)}")

    OUTPUT.write_text(json.dumps(labeled, ensure_ascii=False, indent=2), encoding="utf-8")

if __name__ == "__main__":
    main()
