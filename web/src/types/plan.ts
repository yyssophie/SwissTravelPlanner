export interface PlanPOI {
  identifier: string;
  name: string;
  city: string;
  labels: string[];
  description?: string | null;
  abstract?: string | null;
  photo?: string | null;
  needed_time?: string | null;
}

export interface PlanDay {
  day: number;
  title: string;
  from_city: string | null;
  to_city: string;
  travel_minutes: number;
  summary: string[];
  note?: string | null;
  pois: PlanPOI[];
}

export interface PlanResponse {
  from_city: string;
  to_city: string;
  num_days: number;
  season: string;
  days: PlanDay[];
}
