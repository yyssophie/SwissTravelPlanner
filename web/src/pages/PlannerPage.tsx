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

const PlannerPage = () => {
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [days, setDays] = useState<number>(7);
  const [season, setSeason] = useState("summer");
  const [interests, setInterests] = useState<Interests>({ ...DEFAULT_INTERESTS });

  const totalPct = useMemo(
    () =>
      Object.values(interests).reduce((sum, n) => sum + (isNaN(n) ? 0 : n), 0),
    [interests]
  );

  const remainingPct = 100 - totalPct;
  const overLimit = remainingPct < 0;

  function updateInterest(key: keyof Interests, value: number) {
    setInterests((prev) => ({ ...prev, [key]: Math.max(0, Math.min(100, value)) }));
  }

  function resetAll() {
    setFrom("");
    setTo("");
    setDays(7);
    setSeason("summer");
    setInterests({ ...DEFAULT_INTERESTS });
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
          <input
            className="input-lg"
            placeholder="Starting point (e.g., Zurich)"
            value={from}
            onChange={(e) => setFrom(e.target.value)}
          />
          <label>To</label>
          <input
            className="input-lg"
            placeholder="Destination (e.g., Zermatt)"
            value={to}
            onChange={(e) => setTo(e.target.value)}
          />
        </div>

        <div className="row">
          <label>Total travel days</label>
          <input
            type="number"
            min={1}
            max={21}
            step={1}
            inputMode="numeric"
            pattern="[0-9]*"
            value={days}
            onChange={(e) => {
              const raw = e.target.value;
              const parsed = parseInt(raw, 10);
              if (isNaN(parsed)) { setDays(1); return; }
              const clamped = Math.max(1, Math.min(21, parsed));
              setDays(clamped);
            }}
            onBlur={(e) => {
              const parsed = parseInt(e.target.value, 10);
              if (isNaN(parsed)) { setDays(1); return; }
              const clamped = Math.max(1, Math.min(21, parsed));
              setDays(clamped);
            }}
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
                    type="number"
                    min={0}
                    max={100}
                    value={interests[k]}
                    onChange={(e) => updateInterest(k, parseInt(e.target.value || "0", 10))}
                  />
                  <span className="interest__pct">%</span>
                </div>
              );
            })}
          </div>
          <div className={`remaining ${overLimit ? "over" : "ok"}`}>Remaining: {Math.max(0, remainingPct)}%</div>
        </div>

        <div className="planner__actions">
          <button className="link" onClick={resetAll}>Clear all</button>
          <button
            className="btn btn--primary"
            disabled={overLimit || totalPct !== 100 || !from || !to || days <= 0}
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
