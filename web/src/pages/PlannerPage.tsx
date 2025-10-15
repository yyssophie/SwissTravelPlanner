import { useEffect, useMemo, useState } from "react";
import { getMustVisitDetail } from "../data/mustVisitDetails";

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

const BASE_ATTRACTIONS: Attraction[] = [
  { slug: "faelensee", name: "Fälensee", city: "Appenzell", image: "/attractions/faelensee.jpg" },
  { slug: "old-city-of-bern", name: "Old City of Bern", city: "Bern", image: "/attractions/old-city-of-bern.jpg" },
  { slug: "stoos", name: "Stoos", city: "Schwyz", image: "/attractions/stoos.jpg" },
  { slug: "muerrenbahn", name: "Mürrenbahn", city: "Interlaken", image: "/attractions/muerrenbahn.jpg" },
  { slug: "gornergrat", name: "Gornergrat", city: "Zermatt", image: "/attractions/gornergrat.jpg" },
  { slug: "grosser-mythen", name: "Grosser Mythen", city: "Schwyz", image: "/attractions/grosser-mythen.jpg" },
  { slug: "mount-rigi", name: "Mount Rigi", city: "Lucerne", image: "/attractions/mount-rigi.jpg" },
  { slug: "interlaken-water-sports", name: "Interlaken Water Sports", city: "Interlaken", image: "/attractions/interlaken-water-sports.jpg" },
  { slug: "gurten", name: "Gurten", city: "Bern", image: "/attractions/gurten.jpg" },
];

const shuffle = <T,>(items: T[]): T[] => {
  const arr = [...items];
  for (let i = arr.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [arr[i], arr[j]] = [arr[j], arr[i]];
  }
  return arr;
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
  const [attractions, setAttractions] = useState<Attraction[]>(() => shuffle(BASE_ATTRACTIONS));

  // Must‑visit flow state
  const [mvIndex, setMvIndex] = useState<number>(0);
  const [mvSelected, setMvSelected] = useState<string[]>([]);
  const [mvConfirming, setMvConfirming] = useState<boolean>(false);
  const [mvMessage, setMvMessage] = useState<string | null>(null);
  const [mvDone, setMvDone] = useState<boolean>(false);
  const [detailSlug, setDetailSlug] = useState<string | null>(null);

  const totalPct = useMemo(
    () =>
      Object.values(interests).reduce((sum, n) => sum + (isNaN(n) ? 0 : n), 0),
    [interests]
  );

  const remainingPct = 100 - totalPct;
  const overLimit = remainingPct < 0;
  const maxMust = Math.max(0, days - 2);
  const canAddMore = mvSelected.length < maxMust;
  const currentAttraction = attractions[mvIndex] ?? attractions[0];

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
    if (attractions.length === 0) return;
    setMvIndex((i) => (i + 1) % attractions.length);
  }

  function addCurrentAttraction() {
    const current = attractions[mvIndex];
    if (!current) return;
    if (maxMust <= 0) {
      setMvMessage("Increase your total travel days to unlock Must‑Visits for this trip.");
      return;
    }

    const alreadySelected = mvSelected.includes(current.slug);
    const tentativeLength = alreadySelected ? mvSelected.length : mvSelected.length + 1;
    if (tentativeLength > maxMust) {
      setMvMessage(
        `Limit reached: you can add up to ${maxMust} Must‑Visits for a ${days}-day trip. Increase total days to add more.`
      );
      return;
    }

    const nextSelected = alreadySelected ? mvSelected : [...mvSelected, current.slug];
    if (!alreadySelected) setMvSelected(nextSelected);

    setMvConfirming(true);
    setTimeout(() => {
      setMvConfirming(false);
      setMvMessage(null);

      const forward = attractions.findIndex(
        (item, idx) => idx > mvIndex && !nextSelected.includes(item.slug)
      );
      if (forward !== -1) {
        setMvIndex(forward);
      } else {
        const backward = Array.from(attractions.keys())
          .reverse()
          .find((idx) => idx !== mvIndex && !nextSelected.includes(attractions[idx].slug));
        if (backward !== undefined && backward >= 0) {
          setMvIndex(backward);
        } else {
          const firstUnselected = attractions.findIndex((item) => !nextSelected.includes(item.slug));
          if (firstUnselected !== -1) setMvIndex(firstUnselected);
        }
      }

      if (nextSelected.length >= maxMust || nextSelected.length === attractions.length) {
        setMvMessage("Must‑Visits saved. You can finish now or keep adjusting other inputs.");
      }
    }, 1200);
  }

  function prevAttraction() {
    setMvMessage(null);
    if (attractions.length === 0) return;
    setMvIndex((i) => (i - 1 + attractions.length) % attractions.length);
  }

  function removeSelected(slug: string) {
    setMvSelected((prev) => prev.filter((s) => s !== slug));
    setMvMessage(null);
  }

  function reopenMustVisits() {
    setMvDone(false);
    setMvMessage(null);
    setMvConfirming(false);
    const nextIdx = attractions.findIndex((a) => !mvSelected.includes(a.slug));
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

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setDetailSlug(null);
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

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
    setAttractions(shuffle(BASE_ATTRACTIONS));
    setMvIndex(0);
    setMvSelected([]);
    setMvConfirming(false);
    setMvMessage(null);
    setMvDone(false);
    setDetailSlug(null);
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
          <div className="planner__mode">Routes</div>
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
              {currentAttraction && (
                <div
                  className={`mv-card ${mvConfirming ? "mv-added" : ""}`}
                  style={{ backgroundImage: `url(${currentAttraction.image})` }}
                >
                  <div className="mv-card__top">
                    <button
                      type="button"
                      className="mv-pill mv-pill--button"
                      onClick={() => setDetailSlug(currentAttraction.slug)}
                    >
                      View details
                    </button>
                    <span className="mv-count">{mvIndex + 1}/{attractions.length}</span>
                  </div>
                  <div className="mv-card__overlay"></div>
                  <div className="mv-card__bottom">
                    <div className="mv-text">
                      <div className="mv-city">{currentAttraction.city}</div>
                      <div className="mv-title">{currentAttraction.name}</div>
                    </div>
                  </div>
                  <button
                    type="button"
                    className="mv-arrow mv-arrow--left"
                    onClick={prevAttraction}
                    disabled={attractions.length <= 1}
                    aria-label="Previous"
                  >
                    ‹
                  </button>
                  <button
                    type="button"
                    className="mv-arrow mv-arrow--right"
                    onClick={nextAttraction}
                    disabled={attractions.length <= 1}
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
              )}

              <div className="mv-actions">
                <button
                  type="button"
                  className="btn btn--must"
                  onClick={addCurrentAttraction}
                  disabled={!canAddMore || mvConfirming}
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
                      const a = attractions.find((x) => x.slug === slug);
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
                      const a = attractions.find((x) => x.slug === slug);
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
          <button
            className="btn btn--primary"
            disabled={overLimit || totalPct !== 100 || !from || !to || days < 1 || days > 21}
            onClick={startPlanning}
          >
            Start planning
          </button>
          <button type="button" className="link" onClick={resetAll}>Clear all</button>
        </div>
      </div>
      {detailSlug && (
        <DetailModal slug={detailSlug} onClose={() => setDetailSlug(null)} />
      )}
    </section>
  );
};

export default PlannerPage;

type DetailModalProps = {
  slug: string;
  onClose: () => void;
};

const DetailModal = ({ slug, onClose }: DetailModalProps) => {
  const detail = getMustVisitDetail(slug);
  if (!detail) return null;
  return (
    <div className="mv-modal" role="dialog" aria-modal="true">
      <div className="mv-modal__backdrop" onClick={onClose} />
      <div className="mv-modal__card">
        <button className="mv-modal__close" onClick={onClose} aria-label="Close details">
          ×
        </button>
        <div className="mv-modal__header">
          <h3>{detail.name}</h3>
          <span className="mv-modal__city">{detail.city}</span>
        </div>
        <p className="mv-modal__intro">{detail.intro}</p>
        <div className="mv-modal__seasons">
          Best seasons: <span>{detail.seasons.join(" · ")}</span>
        </div>
        <div className="mv-modal__body">
          {detail.description.map((paragraph, idx) => (
            <p key={idx}>{paragraph}</p>
          ))}
        </div>
      </div>
    </div>
  );
};
