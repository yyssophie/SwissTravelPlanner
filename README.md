# SwissTravelPlanner – Scoring & Planner Guide

## Current Evaluation Function
The evaluator returns a 0–100 score via:

```
Total = 100 * (
    0.35 * interest_matching
  + 0.15 * tu_utilization
  + 0.15 * city_visit_efficiency
  + 0.15 * geographic_coverage
  + 0.10 * long_travel_penalty
  + 0.05 * travel_streak_smoothness
  + 0.05 * stay_streak_smoothness
)
```

**Components**
- **Interest matching (35%)** – TU-weighted label distribution vs. user preferences.
- **TU utilisation (15%)** – For each day: `1 - |TU_used - MTU|/MTU` clipped to [0,1].
- **City visit efficiency (15%)** – `max(0, unique_cities-1) / max(1, (1 + ceil(0.6*days)) - 1)`.
- **Geographic coverage (15%)** – Average √(normalised shortest-path minutes from the start city).
- **Long travel penalty (10%)** – Per day: 1 when travel ≤120 min, else `exp(-((m-120)/30)^2)`.
- **Travel streak smoothness (5%)** – For consecutive travel days:
  - score = `exp(-0.6*(streak_len-1))` (first day=1, quickly decays).
  - Rest days reset the streak and score 1.
  - Component is the average over all days.
- **Stay streak smoothness (5%)** – For consecutive days in the same city:
  - Days 1–2 → score 1
  - Days ≥3 → score `max(0, 1 - (stay_len-2)/4)`
  - Average over all days.

## Planner Heuristic
`RoutePlanner` builds and refines itineraries with a weighted gain:
```
Gain = 0.35*interest_gain
     + 0.20*tu_score
     + 0.15*city_gain
     + 0.15*coverage_gain
     + 0.20*travel_score
     - 0.05*(travel_streak+1)^2   (travel penalty)
     - 0.04*max(0, stay_streak-1)^2 (stay penalty)
     - 0.25 * ((max(0, travel_minutes-120)/60)**2)
```
The heuristic favours moving when travel streaks grow, discourages long stays, and penalises very long hops.

**Local-search moves**
1. Swap two interior city blocks.
2. Substitute an over-served POI label with an under-served one in the same city.
3. Insert a new connector city between adjacent stops when feasible.
4. Convert a travel day into an extra stay day to break streaks.

## Running the Benchmarks
```
PYTHONPATH=src python -m tests.planner_bench \
  --planner-module src.route_planner \
  --planner-class RoutePlanner \
  --scenario-file tests/data/planner_scenarios.json \
  --output tests/results/route_planner_results.json
```

## Scoring an LLM Itinerary
1. Save the LLM JSON (per the prompt structure) to `plan.json`.
2. Run:
```
PYTHONPATH=src python tools/evaluate_llm_plan.py plan.json \
  --start "Zurich" --end "St. Moritz" --days 15 --season winter --mtu 7 \
  --preferences '{"nature":0.45,"culture":0.3,"food":0.15,"sport":0.1}'
```

## Starting the Web Application
### Backend API
```
PYTHONPATH=src uvicorn src.api_server:app --reload
```
(defaults to `http://127.0.0.1:8000`)

### Frontend (Vite + React)
```
cd web
npm install
npm run dev
```
The frontend typically runs on `http://127.0.0.1:5173` and talks to the FastAPI backend.

