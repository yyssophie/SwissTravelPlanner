from __future__ import annotations

from typing import Dict, List

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, validator

from .data_store import CATEGORIES, TravelDataStore
from .route_planner import DayPlan, RoutePlanner


class PreferenceWeights(BaseModel):
    lake: float = Field(..., ge=0.0)
    mountain: float = Field(..., ge=0.0)
    sport: float = Field(..., ge=0.0)
    culture: float = Field(..., ge=0.0)
    food: float = Field(..., ge=0.0)

    def normalised(self) -> Dict[str, float]:
        values = [self.lake, self.mountain, self.sport, self.culture, self.food]
        total = sum(values)
        if total <= 0:
            return {category: 1.0 / len(CATEGORIES) for category in CATEGORIES}
        normalised_values = [value / total for value in values]
        return dict(zip(CATEGORIES, normalised_values))


class PlanRequest(BaseModel):
    from_city: str = Field(..., alias="fromCity")
    to_city: str = Field(..., alias="toCity")
    days: int = Field(..., ge=1)
    season: str
    preferences: PreferenceWeights

    @validator("from_city", "to_city", "season")
    def _strip(cls, value: str) -> str:
        return value.strip()


class PlanPOI(BaseModel):
    identifier: str
    name: str
    city: str
    labels: List[str]
    description: str | None
    abstract: str | None


class PlanDay(BaseModel):
    day: int
    title: str
    from_city: str | None
    to_city: str
    travel_minutes: float
    summary: List[str]
    note: str | None
    pois: List[PlanPOI]


class PlanResponse(BaseModel):
    from_city: str
    to_city: str
    num_days: int
    season: str
    days: List[PlanDay]


def _format_day(day: DayPlan) -> PlanDay:
    from_city = day.travel_from
    to_city = day.display_city
    summary = [poi.name for poi in day.pois]
    pois = [
        PlanPOI(
            identifier=poi.identifier,
            name=poi.name,
            city=poi.city,
            labels=[category for category in CATEGORIES if poi.has_label(category)],
            description=poi.description or None,
            abstract=poi.abstract or None,
        )
        for poi in day.pois
    ]
    title = f"{from_city or 'Start'} → {to_city}"
    return PlanDay(
        day=day.day,
        title=title,
        from_city=from_city,
        to_city=to_city,
        travel_minutes=day.travel_minutes,
        summary=summary,
        note=day.note,
        pois=pois,
    )


app = FastAPI(title="AlpScheduler Planner API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DATASTORE = TravelDataStore.from_files()
PLANNER = RoutePlanner(DATASTORE)


@app.post("/api/plan", response_model=PlanResponse)
def plan_trip(request: PlanRequest) -> PlanResponse:
    try:
        start_display = PLANNER.display_for(request.from_city)
        end_display = PLANNER.display_for(request.to_city)
    except ValueError as exc:  # pragma: no cover - simple validation
        raise HTTPException(status_code=400, detail=str(exc))

    try:
        season = DATASTORE.normalize_season(request.season)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    try:
        itinerary = PLANNER.plan_route(
            start_city=start_display,
            end_city=end_display,
            num_days=request.days,
            preference_weights=request.preferences.normalised(),
            season=season,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    days = [_format_day(day) for day in itinerary]

    return PlanResponse(
        from_city=start_display,
        to_city=end_display,
        num_days=request.days,
        season=season,
        days=days,
    )
