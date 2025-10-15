import { useEffect, useMemo, useState } from "react";

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

type Attraction = {
  slug: string;
  name: string;
  city: string;
  image: string;
};

const MUST_VISIT: Attraction[] = [
  { slug: "faelensee", name: "Fälensee", city: "Appenzell", image: "/attractions/faelensee.jpg" },
  { slug: "old-city-of-bern", name: "Old City of Bern", city: "Bern", image: "/attractions/old-city-of-bern.jpg" },
  { slug: "stoos", name: "Stoos", city: "Schwyz", image: "/attractions/stoos.jpg" },
  { slug: "muerrenbahn", name: "Mürrenbahn", city: "Interlaken", image: "/attractions/muerrenbahn.jpg" },
  { slug: "gornergrat", name: "Gornergrat", city: "Zermatt", image: "/attractions/gornergrat.jpg" },
];

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

  // Must‑visit flow state
  const [mvIndex, setMvIndex] = useState<number>(0);
  const [mvSelected, setMvSelected] = useState<string[]>([]);
  const [mvConfirming, setMvConfirming] = useState<boolean>(false);
  const [mvMessage, setMvMessage] = useState<string | null>(null);
  const [mvDone, setMvDone] = useState<boolean>(false);

  const totalPct = useMemo(
    () =>
      Object.values(interests).reduce((sum, n) => sum + (isNaN(n) ? 0 : n), 0),
    [interests]
  );

  const remainingPct = 100 - totalPct;
  const overLimit = remainingPct < 0;
  const maxMust = Math.max(0, days - 2);
  const canAddMore = mvSelected.length < maxMust;

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

  function updateInterest(
    key: keyof Interests,
    value: string,
    allowEmpty = true,
    capToRemaining = true
  ) {
    const text = sanitizePercentText(value, allowEmpty);
    let numeric = sanitizePercent(text);
    if (capToRemaining) {
      const cap = Math.max(0, remainingPct);
      if (numeric > cap) numeric = cap;
    }
    setInterestText((prev) => ({ ...prev, [key]: String(numeric) }));
    setInterests((prev) => ({ ...prev, [key]: numeric }));
  }

  // Must‑visit controls
  function nextAttraction() {
    if (mvIndex < MUST_VISIT.length - 1) {
      setMvIndex((i) => i + 1);
    }
  }

  function addCurrentAttraction() {
    const current = MUST_VISIT[mvIndex];
    if (!current) return;
    if (mvSelected.length >= maxMust) {
      setMvMessage(
        `Limit reached: you can add up to ${maxMust} Must‑Visits for a ${days}-day trip. Increase total days to add more.`
      );
      return;
    }
    if (!mvSelected.includes(current.slug)) {
      setMvSelected((prev) => [...prev, current.slug]);
    }
    setMvConfirming(true);
    setTimeout(() => {
      setMvConfirming(false);
      // Move to next unselected item if available
      const nextIdx = MUST_VISIT.findIndex((item, idx) =>
        idx > mvIndex && !mvSelected.includes(item.slug) && item.slug !== current.slug
      );
      if (nextIdx !== -1) {
        setMvIndex(nextIdx);
      } else {
        // Otherwise try earlier items
        const prevIdx = [...MUST_VISIT.keys()].reverse().find((idx) =>
          idx < mvIndex && !mvSelected.includes(MUST_VISIT[idx].slug)
        );
        if (prevIdx !== undefined && prevIdx >= 0) {
          setMvIndex(prevIdx);
        }
      }
      if (mvSelected.length + 1 >= maxMust || mvSelected.length + 1 === MUST_VISIT.length) {
        setMvMessage(
          "Must‑Visits saved. You can finish now or keep adjusting other inputs."
        );
      }
    }, 1200);
  }

  function skipCurrentAttraction() {
    setMvMessage(null);
    nextAttraction();
  }

  function prevAttraction() {
    setMvMessage(null);
    setMvIndex((i) => Math.max(0, i - 1));
  }

  function removeSelected(slug: string) {
    setMvSelected((prev) => prev.filter((s) => s !== slug));
  }

  function reopenMustVisits() {
    setMvDone(false);
    setMvMessage(null);
    setMvConfirming(false);
    const nextIdx = MUST_VISIT.findIndex((a) => !mvSelected.includes(a.slug));
    setMvIndex(nextIdx === -1 ? 0 : nextIdx);
  }

  // Keyboard navigation for desktop
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (mvDone || mvConfirming) return;
      if (e.key === "ArrowLeft") prevAttraction();
      if (e.key === "ArrowRight") nextAttraction();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [mvDone, mvConfirming, mvIndex]);

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
    setMvIndex(0);
    setMvSelected([]);
    setMvConfirming(false);
    setMvMessage(null);
    setMvDone(false);
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
                    onChange={(e) => updateInterest(k, e.target.value, true, true)}
                    onBlur={(e) => updateInterest(k, e.target.value, false, true)}
                  />
                  <span className="interest__pct">%</span>
                </div>
              );
            })}
          </div>
          <div className={`remaining ${overLimit ? "over" : "ok"}`}>Remaining: {Math.max(0, remainingPct)}%</div>
        </div>

        {/* Must‑Visit Recommendations Section */}
        <div className="mv">
          <div className="mv__header">
            <h3>Must‑Visit Recommendations</h3>
            <div className="mv__meta">
              <span>Limit: {maxMust}</span>
              <span>Selected: {mvSelected.length}</span>
            </div>
          </div>

          {!mvDone ? (
            <>
              <div
                className={`mv-card ${mvConfirming ? "mv-added" : ""}`}
                style={{ backgroundImage: `url(${MUST_VISIT[mvIndex].image})` }}
              >
                <div className="mv-card__top">
                  <span className="mv-pill">View details</span>
                  <span className="mv-count">{mvIndex + 1}/{MUST_VISIT.length}</span>
                </div>
                <div className="mv-card__overlay"></div>
                <div className="mv-card__bottom">
                  <div className="mv-text">
                    <div className="mv-city">{MUST_VISIT[mvIndex].city}</div>
                    <div className="mv-title">{MUST_VISIT[mvIndex].name}</div>
                  </div>
                </div>
                <button
                  type="button"
                  className="mv-arrow mv-arrow--left"
                  onClick={prevAttraction}
                  disabled={mvIndex === 0}
                  aria-label="Previous"
                >
                  ‹
                </button>
                <button
                  type="button"
                  className="mv-arrow mv-arrow--right"
                  onClick={nextAttraction}
                  disabled={mvIndex === MUST_VISIT.length - 1}
                  aria-label="Next"
                >
                  ›
                </button>
                {mvConfirming && (
                  <div className="mv-confirm">
                    <div className="mv-tick">✓</div>
                    <div className="mv-msg">Added to your trip</div>
                  </div>
                )}
              </div>

              <div className="mv-actions">
                <button
                  type="button"
                  className="btn btn--primary"
                  onClick={addCurrentAttraction}
                  disabled={!canAddMore}
                >
                  Add to Must‑Visits
                </button>
                <button
                  type="button"
                  className="btn btn--ghost"
                  onClick={() => setMvDone(true)}
                >
                  Finish selecting
                </button>
              </div>
              {mvSelected.length > 0 && (
                <div className="mv-selected mv-selected--inline">
                  <div className="mv-selected__label">Added so far:</div>
                  <ul className="mv-selected__list">
                    {mvSelected.map((slug) => {
                      const a = MUST_VISIT.find((x) => x.slug === slug);
                      if (!a) return null;
                      return (
                        <li key={slug} className="mv-chip">
                          <span className="mv-chip__text">{a.name} – {a.city}</span>
                          <button
                            className="mv-chip__del"
                            onClick={() => removeSelected(slug)}
                            aria-label={`Remove ${a.name}`}
                          >
                            -
                          </button>
                        </li>
                      );
                    })}
                  </ul>
                </div>
              )}
            </>
          ) : (
            <>
              <div className="mv-done">Great picks — your Must‑Visits are set!</div>
              <div className="mv-selected">
                {mvSelected.length === 0 ? (
                  <div className="mv-selected__empty">No Must‑Visits selected.</div>
                ) : (
                  <ul className="mv-selected__list">
                    {mvSelected.map((slug) => {
                      const a = MUST_VISIT.find((x) => x.slug === slug);
                      if (!a) return null;
                      return (
                        <li key={slug} className="mv-chip">
                          <span className="mv-chip__text">{a.name} – {a.city}</span>
                          <button
                            className="mv-chip__del"
                            onClick={() => removeSelected(slug)}
                            aria-label={`Remove ${a.name}`}
                          >
                            -
                          </button>
                        </li>
                      );
                    })}
                  </ul>
                )}
              </div>
              <div className="mv-finish-actions">
                <button type="button" className="btn btn--ghost" onClick={reopenMustVisits}>
                  Review attractions again
                </button>
              </div>
            </>
          )}

          {mvMessage && <div className="mv-message">{mvMessage}</div>}
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
