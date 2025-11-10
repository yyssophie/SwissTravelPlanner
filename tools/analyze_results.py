"""
Analyze experiment results CSV and produce summary CSVs.

Outputs:
  - summary_algorithms.csv: mean/median/CI per algorithm
  - summary_by_field.csv: mean/median per algorithm broken down by inputs
  - paired_tests.csv: paired comparisons of total_score between algorithms

Usage:
  PYTHONPATH=src python tools/analyze_results.py --input experiments/results.csv --outdir experiments [--seed 1337]
"""

from __future__ import annotations

import argparse
import csv
import math
import random
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any, DefaultDict, Dict, Iterable, List, Mapping, Tuple


# Metrics to summarize from the CSV
KEY_COMPONENTS: List[str] = [
    "total_score",
    "interest_matching",
    "tu_utilization",
    "city_visit_efficiency",
    "geographic_coverage",
    "long_travel_penalty",
    "travel_streak_smoothness",
    "stay_streak_smoothness",
]


def read_rows(path: Path) -> List[Dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8") as f:
        rdr = csv.DictReader(f)
        return [dict(row) for row in rdr]


def write_csv(path: Path, header: List[str], rows: Iterable[Iterable[Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        for r in rows:
            writer.writerow(list(r))


def group_by(rows: Iterable[Mapping[str, Any]], keys: List[str]) -> Dict[Tuple[Any, ...], List[Mapping[str, Any]]]:
    groups: DefaultDict[Tuple[Any, ...], List[Mapping[str, Any]]] = defaultdict(list)
    for r in rows:
        k = tuple(r.get(k) for k in keys)
        groups[k].append(r)
    return dict(groups)


def percentile(values: List[float], q: float) -> float:
    if not values:
        return math.nan
    s = sorted(values)
    idx = (len(s) - 1) * q
    lo = int(math.floor(idx))
    hi = int(math.ceil(idx))
    if lo == hi:
        return s[lo]
    w = idx - lo
    return s[lo] * (1 - w) + s[hi] * w


def bootstrap_ci(values: List[float], n_resamples: int = 2000, seed: int | None = None) -> Tuple[float, float]:
    if len(values) <= 1:
        v = values[0] if values else math.nan
        return (v, v)
    rng = random.Random(seed)
    n = len(values)
    meds: List[float] = []
    for _ in range(n_resamples):
        sample = [values[rng.randrange(n)] for _ in range(n)]
        meds.append(statistics.median(sample))
    return (percentile(meds, 0.025), percentile(meds, 0.975))


def summarize(values: List[float], seed: int | None = None) -> Dict[str, float]:
    if not values:
        return {"mean": math.nan, "median": math.nan, "ci95_low": math.nan, "ci95_high": math.nan}
    mean_v = statistics.fmean(values)
    median_v = statistics.median(values)
    lo, hi = bootstrap_ci(values, seed=seed)
    return {"mean": mean_v, "median": median_v, "ci95_low": lo, "ci95_high": hi}


def build_scenario_key(r: Mapping[str, Any]) -> Tuple[Any, ...]:
    return (
        r.get("start_city"),
        r.get("end_city"),
        r.get("days"),
        r.get("season"),
        r.get("mtu"),
        r.get("pref_label"),
    )


def paired_tests(pairs: List[Tuple[float, float]]) -> Dict[str, float]:
    diffs = [b - a for (a, b) in pairs]
    diffs = [d for d in diffs if d != 0]
    n = len(diffs)
    if n == 0:
        return {"n": 0.0, "median_diff": 0.0, "p_wilcoxon": -1.0}
    median_diff = statistics.median(diffs)

    # Approximate Wilcoxon signed-rank p-value (normal approximation with tie correction)
    # 1) ranks of |diffs| with average for ties
    abs_diffs = [abs(d) for d in diffs]
    # sort indices by abs value
    sorted_idx = sorted(range(n), key=lambda i: abs_diffs[i])
    ranks = [0.0] * n
    i = 0
    while i < n:
        j = i
        while j + 1 < n and abs_diffs[sorted_idx[j + 1]] == abs_diffs[sorted_idx[i]]:
            j += 1
        # average rank for ties in [i, j]
        avg_rank = (i + 1 + j + 1) / 2.0
        for k in range(i, j + 1):
            ranks[sorted_idx[k]] = avg_rank
        i = j + 1

    # W+ is sum of ranks for positive diffs
    Wpos = sum(r for r, d in zip(ranks, diffs) if d > 0)
    # moments under H0
    mean_W = n * (n + 1) / 4.0
    # tie correction: subtract sum(t*(t+1)*(2t+1)) from numerator
    # build tie groups by abs value counts
    tie_counts: Dict[float, int] = {}
    for v in abs_diffs:
        tie_counts[v] = tie_counts.get(v, 0) + 1
    tie_term = sum(t * (t + 1) * (2 * t + 1) for t in tie_counts.values())
    var_W = (n * (n + 1) * (2 * n + 1) - tie_term) / 24.0
    if var_W <= 0:
        p = -1.0
    else:
        # continuity correction
        z = (Wpos - mean_W - 0.5 * (1 if Wpos > mean_W else -1)) / math.sqrt(var_W)
        # two-sided p using normal CDF via erfc
        p = float(2.0 * 0.5 * math.erfc(abs(z) / math.sqrt(2.0)))

    return {"n": float(n), "median_diff": float(median_diff), "p_wilcoxon": p}


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze experiment results and produce summaries.")
    parser.add_argument("--input", required=True, help="Path to input CSV (from experiment_bench)")
    parser.add_argument("--outdir", required=True, help="Directory to write summary CSVs")
    parser.add_argument("--seed", type=int, default=None, help="Seed for bootstrap CI (optional)")
    args = parser.parse_args()

    inp = Path(args.input)
    outdir = Path(args.outdir)

    rows = read_rows(inp)

    # Filter out planner errors for summaries; keep them in a separate count
    error_rows = [r for r in rows if r.get("violations", "") and "planner_error" in (r.get("violations") or "")]
    error_count = len(error_rows)
    ok_rows = [r for r in rows if not ("planner_error" in (r.get("violations") or ""))]

    # Per-algorithm summary
    alg_groups = group_by(ok_rows, ["algorithm_id", "algorithm"])
    alg_header = [
        "algorithm_id",
        "algorithm",
        "n",
    ] + [f"{c}_mean" for c in KEY_COMPONENTS] + [f"{c}_median" for c in KEY_COMPONENTS] + [f"{c}_ci95_low" for c in KEY_COMPONENTS] + [
        f"{c}_ci95_high" for c in KEY_COMPONENTS
    ]
    alg_data: List[List[Any]] = []
    for key, rs in sorted(alg_groups.items()):
        stats_map: Dict[str, Dict[str, float]] = {c: summarize([float(r[c]) for r in rs], seed=args.seed) for c in KEY_COMPONENTS}
        row: List[Any] = [key[0], key[1], len(rs)]
        row += [stats_map[c]["mean"] for c in KEY_COMPONENTS]
        row += [stats_map[c]["median"] for c in KEY_COMPONENTS]
        row += [stats_map[c]["ci95_low"] for c in KEY_COMPONENTS]
        row += [stats_map[c]["ci95_high"] for c in KEY_COMPONENTS]
        alg_data.append(row)
    write_csv(outdir / "summary_algorithms.csv", alg_header, alg_data)

    # Per-algorithm-by-input summaries (one field at a time)
    by_field_rows: List[List[Any]] = []
    by_field_header = [
        "algorithm_id",
        "algorithm",
        "field",
        "value",
        "n",
    ] + [f"{c}_mean" for c in KEY_COMPONENTS] + [f"{c}_median" for c in KEY_COMPONENTS]
    for field in ["days", "season", "mtu", "pref_label", "start_city", "end_city"]:
        field_groups = group_by(ok_rows, ["algorithm_id", "algorithm", field])
        for (alg_id, alg_name, fval), rs in sorted(field_groups.items()):
            stats_map = {c: summarize([float(r[c]) for r in rs], seed=args.seed) for c in KEY_COMPONENTS}
            row = [alg_id, alg_name, field, fval, len(rs)]
            row += [stats_map[c]["mean"] for c in KEY_COMPONENTS]
            row += [stats_map[c]["median"] for c in KEY_COMPONENTS]
            by_field_rows.append(row)
    write_csv(outdir / "summary_by_field.csv", by_field_header, by_field_rows)

    # Paired significance tests (total_score) comparing algorithms across identical scenarios
    # pair on exact scenario key (inputs only); ignore runs with planner_error
    scen_map: Dict[Tuple[Any, ...], Dict[str, float]] = defaultdict(dict)  # key -> {algorithm_id: total_score}
    for r in ok_rows:
        scen_key = build_scenario_key(r)
        alg_id = str(r["algorithm_id"]) if "algorithm_id" in r else str(r.get("algorithm_id"))
        scen_map[scen_key][alg_id] = float(r["total_score"])  # type: ignore[arg-type]
    # Build pair lists
    pairs_21: List[Tuple[float, float]] = []
    pairs_31: List[Tuple[float, float]] = []
    pairs_32: List[Tuple[float, float]] = []
    for _, alg_scores in scen_map.items():
        a1 = alg_scores.get("1"); a2 = alg_scores.get("2"); a3 = alg_scores.get("3")
        if a1 is not None and a2 is not None:
            pairs_21.append((a1, a2))
        if a1 is not None and a3 is not None:
            pairs_31.append((a1, a3))
        if a2 is not None and a3 is not None:
            pairs_32.append((a2, a3))

    comp_header = ["comparison", "n", "median_diff", "p_wilcoxon"]
    comp_rows: List[List[Any]] = []
    for name, pairs in [("2_vs_1", pairs_21), ("3_vs_1", pairs_31), ("3_vs_2", pairs_32)]:
        res = paired_tests(pairs)
        comp_rows.append([
            name,
            int(res["n"]),
            f"{res['median_diff']:.7f}",
            f"{res['p_wilcoxon']:.6g}" if res["p_wilcoxon"] >= 0 else "NA",
        ])

    write_csv(outdir / "paired_tests.csv", comp_header, comp_rows)

    print(
        "Written:\n- {}\n- {}\n- {}\nPlanner errors encountered: {}".format(
            outdir / "summary_algorithms.csv",
            outdir / "summary_by_field.csv",
            outdir / "paired_tests.csv",
            error_count,
        )
    )


if __name__ == "__main__":
    main()
