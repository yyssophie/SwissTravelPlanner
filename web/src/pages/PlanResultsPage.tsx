import { useEffect, useMemo, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import type { PlanResponse, PlanDay, PlanPOI } from "../types/plan";

const STORAGE_KEY = "alpScheduler:lastPlan";

const normaliseSeason = (season: string) =>
  season.slice(0, 1).toUpperCase() + season.slice(1).toLowerCase();

const PlanResultsPage = () => {
  const location = useLocation();
  const navigate = useNavigate();
  const initialPlan = (location.state as PlanResponse | undefined) ?? loadFromStorage();
  const [plan, setPlan] = useState<PlanResponse | null>(initialPlan);
  const [expandedDay, setExpandedDay] = useState<number | null>(null);
  const cardRefs = useRef<Record<number, HTMLDivElement | null>>({});

  useEffect(() => {
    const statePlan = location.state as PlanResponse | undefined;
    if (statePlan) {
      setPlan(statePlan);
      sessionStorage.setItem(STORAGE_KEY, JSON.stringify(statePlan));
    }
  }, [location.state]);

  // Jump to top on initial load
  useEffect(() => {
    window.scrollTo({ top: 0, behavior: "smooth" });
  }, []);

  const headline = useMemo(() => {
    if (!plan) return "";
    return `${plan.num_days}-day route from ${plan.from_city} to ${plan.to_city}`;
  }, [plan]);

  if (!plan) {
    return (
      <div className="plan-results plan-results--empty">
        <div className="plan-results__card">
          <h1>No itinerary yet</h1>
          <p>Please build a plan first so we can show day-by-day details.</p>
          <button className="btn btn--dark" onClick={() => navigate("/planner")}>
            Back to planner
          </button>
        </div>
      </div>
    );
  }

  const toggleDay = (dayNumber: number) => {
    setExpandedDay((prev) => (prev === dayNumber ? null : dayNumber));
  };

  // Scroll the expanded card to the top (below the fixed navbar) for better focus
  useEffect(() => {
    if (expandedDay == null) return;
    const el = cardRefs.current[expandedDay];
    if (!el) return;
    const offset = 80; // approximate fixed header height
    const y = el.getBoundingClientRect().top + window.scrollY - offset;
    window.scrollTo({ top: y, behavior: "smooth" });
  }, [expandedDay]);

  return (
    <div className="plan-results">
      <div className="plan-results__intro">
        <button className="plan-results__back" onClick={() => navigate("/planner")}>
          ← Adjust preferences
        </button>
        <div>
          <p className="plan-results__label">Suggested Itinerary</p>
          <h1 className="plan-results__headline">{headline}</h1>
          <p className="plan-results__meta">
            Season focus: {normaliseSeason(plan.season)}
          </p>
        </div>
      </div>

      <section className="plan-results__days">
        {plan.days.map((day) => (
          <DayCard
            key={day.day}
            day={day}
            expanded={expandedDay === day.day}
            onToggle={() => toggleDay(day.day)}
            getRef={(el) => (cardRefs.current[day.day] = el)}
          />
        ))}
      </section>
    </div>
  );
};

const DayCard = ({
  day,
  expanded,
  onToggle,
  getRef,
}: {
  day: PlanDay;
  expanded: boolean;
  onToggle: () => void;
  getRef: (el: HTMLDivElement | null) => void;
}) => (
  <article ref={getRef} className={`plan-day ${expanded ? "plan-day--expanded" : ""}`}>
    <button className="plan-day__summary" onClick={onToggle}>
      <div className="plan-day__col plan-day__col--badge">
        <span className="plan-day__badge">Day {day.day}</span>
      </div>
      <div className="plan-day__col plan-day__col--info">
        <p className="plan-day__route">{formatRoute(day)}</p>
        <p className="plan-day__activities">{day.summary.join(" · ")}</p>
      </div>
      {day.from_city && day.from_city !== day.to_city && (
        (() => {
          const t = formatTravelMinutes(day.travel_minutes);
          return t ? <span className="plan-day__travel">{t}</span> : null;
        })()
      )}
      <span className="plan-day__toggle" aria-hidden>{expanded ? "−" : "+"}</span>
    </button>
    {expanded && (
      <div className="plan-day__details">
        {day.pois.map((poi) => (
          <POICard key={poi.identifier} poi={poi} />
        ))}
      </div>
    )}
  </article>
);

const POICard = ({ poi }: { poi: PlanPOI }) => (
  <div className="plan-poi">
    <div className="plan-poi__header">
      <h3>
        {poi.name}
        <span className="plan-poi__city"> · {formatCity(poi.city)}</span>
      </h3>
      <div className="plan-poi__labels">
        {poi.labels.map((label) => (
          <span className="plan-poi__chip" key={label}>
            {label}
          </span>
        ))}
      </div>
    </div>
    {poi.needed_time && (
      <div className="plan-poi__time">{formatNeededTime(poi.needed_time)}</div>
    )}
    {poi.description ? (
      <p>{poi.description}</p>
    ) : poi.abstract ? (
      <p>{poi.abstract}</p>
    ) : (
      <p>No description available yet.</p>
    )}
    {poi.photo && (
      <img
        className="plan-poi__image"
        src={poi.photo}
        alt={poi.name}
        loading="lazy"
      />
    )}
  </div>
);

function formatCity(slug: string): string {
  if (!slug) return slug;
  const lower = slug.toLowerCase();
  if (lower === "luzerne" || lower === "lucerne") return "Lucerne";
  return lower.charAt(0).toUpperCase() + lower.slice(1);
}

function formatNeededTime(raw: string): string {
  const normalised = raw?.toLowerCase() || "";
  if (normalised.includes("less") || normalised.includes("< 1") || normalised.includes("<1")) {
    return "< 1 hour";
  }
  if (normalised.includes("1") && normalised.includes("2")) {
    return "1 – 2 hours";
  }
  if (normalised.includes("2") && normalised.includes("4")) {
    return "2 – 4 hours";
  }
  if (normalised.includes("4") && normalised.includes("8")) {
    return "4 – 8 hours";
  }
  return raw;
}

function formatRoute(day: PlanDay): string {
  const from = day.from_city ? day.from_city : null;
  const to = day.to_city;
  const same = from && from === to;
  if (!from || same) {
    return to; // just destination city (no "Start ->" or same-city arrows)
  }
  return `${from} → ${to}`;
}

function formatTravelMinutes(minutes: number): string | null {
  if (!minutes || minutes <= 0) return null;
  const rounded = Math.max(15, Math.round(minutes / 15) * 15);
  const hours = Math.floor(rounded / 60);
  const mins = rounded % 60;
  if (hours === 0) return `${mins} minutes`;
  if (mins === 0) return `${hours} ${hours === 1 ? "hour" : "hours"}`;
  return `${hours} ${hours === 1 ? "hour" : "hours"} ${mins} minutes`;
}


function loadFromStorage(): PlanResponse | null {
  const stored = sessionStorage.getItem(STORAGE_KEY);
  if (!stored) return null;
  try {
    return JSON.parse(stored) as PlanResponse;
  } catch {
    sessionStorage.removeItem(STORAGE_KEY);
    return null;
  }
}

export default PlanResultsPage;
