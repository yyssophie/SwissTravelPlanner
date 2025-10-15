import { useMemo, useState } from "react";

type Interests = {
  lake: number;
  mountain: number;
  culture: number;
  food: number;
  sport: number;
};

const DEFAULT_INTERESTS: Interests = {
  lake: 0,
  mountain: 0,
  culture: 0,
  food: 0,
  sport: 0,
};

const CITY_OPTIONS = [
  "appenzell",
  "bern",
  "geneva",
  "interlaken",
  "lucerne",
  "lugano",
  "montreux",
  "schwyz",
  "zermatt",
  "zurich",
] as const;

function labelForCity(slug: (typeof CITY_OPTIONS)[number] | ""): string {
  switch (slug) {
    case "lucerne":
      return "Lucerne";
    case "zurich":
      return "Zurich";
    default:
      return slug ? slug.charAt(0).toUpperCase() + slug.slice(1) : "";
  }
}

const PlannerPage = () => {
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [days, setDays] = useState<number>(7);
  const [daysText, setDaysText] = useState<string>("7");
  const [season, setSeason] = useState("summer");
  const [interests, setInterests] = useState<Interests>({ ...DEFAULT_INTERESTS });
  const [interestText, setInterestText] = useState<Record<keyof Interests, string>>({
    lake: "0",
    mountain: "0",
    culture: "0",
    food: "0",
    sport: "0",
  });

  const totalPct = useMemo(
    () =>
      Object.values(interests).reduce((sum, n) => sum + (isNaN(n) ? 0 : n), 0),
    [interests]
  );

  const remainingPct = 100 - totalPct;
  const overLimit = remainingPct < 0;

  function sanitizePercent(raw: string): number {
    // Keep digits only
    const digits = (raw || "").replace(/\D+/g, "");
    // Remove leading zeros but keep a single zero
    const noLead = digits.replace(/^0+(?=\d)/, "");
    const parsed = parseInt(noLead || "0", 10);
    if (isNaN(parsed)) return 0;
    return Math.max(0, Math.min(100, parsed));
  }

  function sanitizePercentText(raw: string, allowEmpty: boolean): string {
    const digits = (raw || "").replace(/\D+/g, "");
    if (digits === "") return allowEmpty ? "" : "0";
    const noLead = digits.replace(/^0+(?=\d)/, "");
    const n = Math.max(0, Math.min(100, parseInt(noLead, 10)));
    return String(n);
  }

  function updateInterest(key: keyof Interests, value: string, allowEmpty = true) {
    const text = sanitizePercentText(value, allowEmpty);
    setInterestText((prev) => ({ ...prev, [key]: text }));
    const numeric = sanitizePercent(text);
    setInterests((prev) => ({ ...prev, [key]: numeric }));
  }

  function sanitizeDaysText(raw: string, allowEmpty: boolean): string {
    const digits = (raw || "").replace(/\D+/g, "");
    if (digits === "") return allowEmpty ? "" : "1";
    const noLead = digits.replace(/^0+(?=\d)/, "");
    const n = Math.max(1, Math.min(21, parseInt(noLead || "1", 10)));
    return String(n);
  }

  function updateDays(value: string, allowEmpty = true) {
    const text = sanitizeDaysText(value, allowEmpty);
    setDaysText(text);
    const n = parseInt(text || "0", 10);
    setDays(isNaN(n) ? 1 : Math.max(1, Math.min(21, n)));
  }

  function resetAll() {
    setFrom("");
    setTo("");
    setDays(7);
    setDaysText("7");
    setSeason("summer");
    setInterests({ ...DEFAULT_INTERESTS });
    setInterestText({ lake: "0", mountain: "0", culture: "0", food: "0", sport: "0" });
  }

  function startPlanning() {
    const payload = { from, to, days, season, interests };
    // Placeholder: integrate AI planner call here.
    console.log("Planning payload", payload);
    alert("Planner input captured. Check console for payload.");
  }

  return (
    <section className="planner" id="planner">
      <div className="planner__card">
        <div className="planner__header">
          <h2>Plan your route</h2>
          <div className="planner__tabs">
            <button className="active">Routes</button>
            <button disabled>Places</button>
          </div>
        </div>

        <div className="row fromto">
          <label>From</label>
          <select
            className="input-lg"
            value={from}
            onChange={(e) => setFrom(e.target.value)}
          >
            <option value="">Select city</option>
            {CITY_OPTIONS.map((c) => (
              <option key={c} value={c}>
                {labelForCity(c)}
              </option>
            ))}
          </select>
          <label>To</label>
          <select
            className="input-lg"
            value={to}
            onChange={(e) => setTo(e.target.value)}
          >
            <option value="">Select city</option>
            {CITY_OPTIONS.map((c) => (
              <option key={c} value={c}>
                {labelForCity(c)}
              </option>
            ))}
          </select>
        </div>

        <div className="row">
          <label>Total travel days</label>
          <input
            type="text"
            inputMode="numeric"
            pattern="[0-9]*"
            value={daysText}
            onChange={(e) => updateDays(e.target.value, true)}
            onBlur={(e) => updateDays(e.target.value, false)}
          />
        </div>

        <div className="row">
          <label>Season</label>
          <select value={season} onChange={(e) => setSeason(e.target.value)}>
            <option value="spring">Spring</option>
            <option value="summer">Summer</option>
            <option value="autumn">Autumn</option>
            <option value="winter">Winter</option>
          </select>
        </div>

        <div className="row">
          <label>Interests (total must be 100%)</label>
          <div className="grid-2">
            {Object.keys(interests).map((key) => {
              const k = key as keyof Interests;
              return (
                <div className="interest" key={key}>
                  <span className="interest__label">{k}</span>
                  <input
                    type="text"
                    inputMode="numeric"
                    pattern="[0-9]*"
                    value={interestText[k]}
                    onChange={(e) => updateInterest(k, e.target.value, true)}
                    onBlur={(e) => updateInterest(k, e.target.value, false)}
                  />
                  <span className="interest__pct">%</span>
                </div>
              );
            })}
          </div>
          <div className={`remaining ${overLimit ? "over" : "ok"}`}>Remaining: {Math.max(0, remainingPct)}%</div>
        </div>

        <div className="planner__actions">
          <button type="button" className="link" onClick={resetAll}>Clear all</button>
          <button
            className="btn btn--primary"
            disabled={overLimit || totalPct !== 100 || !from || !to || days < 1 || days > 21}
            onClick={startPlanning}
          >
            Start planning
          </button>
        </div>
      </div>
    </section>
  );
};

export default PlannerPage;
