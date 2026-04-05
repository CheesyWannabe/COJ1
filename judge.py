"""
CSV Judge — Core Comparison Engine
Implements: column alignment, row matching (exact + best-match), cell scoring,
            optional Hungarian algorithm for optimal row assignment.
"""

from __future__ import annotations

import io
import math
import re
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd
from scipy.optimize import linear_sum_assignment  # Hungarian algorithm


# ─────────────────────────────────────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class CompareConfig:
    lowercase: bool = True
    trim: bool = True
    numeric_tolerance: bool = True
    tolerance: float = 0.01          # relative tolerance for floats
    penalize_extra: bool = True
    column_weights: dict[str, float] = field(default_factory=dict)
    use_hungarian: bool = True       # False → greedy row matching (faster)
    partial_string_threshold: float = 0.5  # min Levenshtein sim to count


# ─────────────────────────────────────────────────────────────────────────────
# CSV Loading
# ─────────────────────────────────────────────────────────────────────────────

def _load_csv(content: str) -> pd.DataFrame:
    """Parse CSV robustly, raising ValueError on bad input."""
    try:
        df = pd.read_csv(io.StringIO(content), dtype=str, keep_default_na=False)
    except Exception as exc:
        raise ValueError(f"Could not parse CSV: {exc}") from exc
    if df.empty and df.columns.size == 0:
        raise ValueError("CSV appears to be empty or has no columns.")
    return df


# ─────────────────────────────────────────────────────────────────────────────
# Normalisation
# ─────────────────────────────────────────────────────────────────────────────

def _norm(value: str, cfg: CompareConfig) -> str:
    s = str(value) if value is not None else ""
    if cfg.trim:
        s = s.strip()
    if cfg.lowercase:
        s = s.lower()
    return s


def _is_numeric(s: str) -> tuple[bool, float]:
    try:
        return True, float(s.replace(",", ""))
    except ValueError:
        return False, 0.0


# ─────────────────────────────────────────────────────────────────────────────
# Column Matching
# ─────────────────────────────────────────────────────────────────────────────

def _levenshtein(a: str, b: str) -> int:
    if a == b:
        return 0
    la, lb = len(a), len(b)
    if la == 0:
        return lb
    if lb == 0:
        return la
    prev = list(range(lb + 1))
    for i in range(1, la + 1):
        cur = [i] + [0] * lb
        for j in range(1, lb + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost)
        prev = cur
    return prev[lb]


def _str_sim(a: str, b: str) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    dist = _levenshtein(a.lower(), b.lower())
    return 1.0 - dist / max(len(a), len(b))


def match_columns(ref_cols: list[str], sub_cols: list[str]) -> dict[str, Optional[str]]:
    """
    Map each reference column → best matching submission column.
    Returns {ref_col: sub_col or None}.
    """
    mapping: dict[str, Optional[str]] = {}
    used: set[str] = set()

    for rc in ref_cols:
        best_sc, best_sim = None, -1.0
        for sc in sub_cols:
            if sc in used:
                continue
            sim = _str_sim(rc, sc)
            if sim > best_sim:
                best_sim = sim
                best_sc = sc
        if best_sc is not None and best_sim >= 0.6:
            mapping[rc] = best_sc
            used.add(best_sc)
        else:
            mapping[rc] = None
    return mapping


# ─────────────────────────────────────────────────────────────────────────────
# Cell Scoring
# ─────────────────────────────────────────────────────────────────────────────

def _cell_score(ref_val: str, sub_val: str, cfg: CompareConfig) -> float:
    rn = _norm(ref_val, cfg)
    sn = _norm(sub_val, cfg)

    if rn == sn:
        return 1.0

    if cfg.numeric_tolerance:
        rnum_ok, rnum = _is_numeric(rn)
        snum_ok, snum = _is_numeric(sn)
        if rnum_ok and snum_ok:
            base = abs(rnum) if abs(rnum) > 1e-9 else 1.0
            rel_err = abs(rnum - snum) / base
            if rel_err <= cfg.tolerance:
                return 1.0
            if rel_err <= cfg.tolerance * 10:
                return 0.5
            return max(0.0, 1.0 - rel_err)

    # String similarity
    sim = _str_sim(rn, sn)
    if sim >= cfg.partial_string_threshold:
        return sim
    return 0.0


# ─────────────────────────────────────────────────────────────────────────────
# Row Scoring
# ─────────────────────────────────────────────────────────────────────────────

def _row_score(
    ref_row: dict[str, str],
    sub_row: dict[str, str],
    col_map: dict[str, Optional[str]],
    cfg: CompareConfig,
    weights: dict[str, float],
) -> tuple[float, dict[str, dict]]:
    """Score a ref/sub row pair. Returns (weighted_score, per-cell details)."""
    total_w = sum(weights.get(rc, 1.0) for rc in col_map)
    if total_w == 0:
        return 0.0, {}

    score_sum = 0.0
    cells: dict[str, dict] = {}
    for rc, sc in col_map.items():
        w = weights.get(rc, 1.0)
        rv = ref_row.get(rc, "")
        sv = sub_row.get(sc, "") if sc else ""
        cs = _cell_score(rv, sv, cfg)
        score_sum += cs * w
        cells[rc] = {"ref": rv, "sub": sv, "score": round(cs, 4), "weight": w}

    return score_sum / total_w, cells


# ─────────────────────────────────────────────────────────────────────────────
# Row Matching
# ─────────────────────────────────────────────────────────────────────────────

def _match_rows(
    ref_rows: list[dict],
    sub_rows: list[dict],
    col_map: dict[str, Optional[str]],
    cfg: CompareConfig,
    weights: dict[str, float],
) -> list[tuple[int, Optional[int], float, dict]]:
    """
    Match ref rows to sub rows optimally (Hungarian) or greedily.
    Returns list of (ref_idx, sub_idx or None, row_score, cell_details).
    """
    n_ref, n_sub = len(ref_rows), len(sub_rows)
    if n_ref == 0:
        return []

    # Build cost matrix (we maximise score, so use negative for minimisation)
    cost = np.zeros((n_ref, n_sub), dtype=float)
    cell_cache: dict[tuple[int, int], tuple[float, dict]] = {}

    for ri, rr in enumerate(ref_rows):
        for si, sr in enumerate(sub_rows):
            sc, cells = _row_score(rr, sr, col_map, cfg, weights)
            cost[ri, si] = sc
            cell_cache[(ri, si)] = (sc, cells)

    if cfg.use_hungarian and n_ref <= 500 and n_sub <= 500:
        # Pad to square if needed
        size = max(n_ref, n_sub)
        padded = np.zeros((size, size), dtype=float)
        padded[:n_ref, :n_sub] = cost
        row_ind, col_ind = linear_sum_assignment(-padded)
        assignment = list(zip(row_ind.tolist(), col_ind.tolist()))
    else:
        # Greedy: sort by score descending, assign greedily
        pairs = sorted(
            ((ri, si) for ri in range(n_ref) for si in range(n_sub)),
            key=lambda p: -cost[p],
        )
        used_r, used_s = set(), set()
        assignment = []
        for ri, si in pairs:
            if ri not in used_r and si not in used_s:
                assignment.append((ri, si))
                used_r.add(ri)
                used_s.add(si)
        for ri in range(n_ref):
            if ri not in used_r:
                assignment.append((ri, -1))

    results = []
    matched_sub = set()
    for ri, si in assignment:
        if ri >= n_ref:
            continue
        if si >= n_sub or si < 0:
            results.append((ri, None, 0.0, {}))
            continue
        sc, cells = cell_cache.get((ri, si), (0.0, {}))
        results.append((ri, si, sc, cells))
        matched_sub.add(si)

    return results, matched_sub


# ─────────────────────────────────────────────────────────────────────────────
# Main Comparison Function
# ─────────────────────────────────────────────────────────────────────────────

def compare_csvs(ref_content: str, sub_content: str, cfg: CompareConfig) -> dict:
    """
    Compare submission CSV against reference CSV.
    Returns a dict with score, statistics, and per-column breakdown.
    """
    ref_df = _load_csv(ref_content)
    sub_df = _load_csv(sub_content)

    ref_cols = list(ref_df.columns)
    sub_cols = list(sub_df.columns)

    col_map = match_columns(ref_cols, sub_cols)
    weights = cfg.column_weights or {}

    ref_rows = ref_df.to_dict(orient="records")
    sub_rows = sub_df.to_dict(orient="records")

    n_ref = len(ref_rows)
    n_sub = len(sub_rows)

    matched_results, matched_sub_indices = _match_rows(ref_rows, sub_rows, col_map, cfg, weights)

    # Aggregate
    total_w = sum(weights.get(rc, 1.0) for rc in col_map)
    matched_count = sum(1 for _, si, sc, _ in matched_results if si is not None and sc >= 0.99)
    partial_count = sum(1 for _, si, sc, _ in matched_results if si is not None and 0.01 <= sc < 0.99)
    missing_count = sum(1 for _, si, sc, _ in matched_results if si is None)
    extra_rows = n_sub - len(matched_sub_indices)

    raw_score_sum = sum(sc for _, si, sc, _ in matched_results)
    denominator = n_ref + (extra_rows if cfg.penalize_extra else 0)
    final_score = (raw_score_sum / denominator * 100) if denominator > 0 else 0.0
    final_score = round(max(0.0, min(100.0, final_score)), 2)

    # Per-column scores
    col_scores: dict[str, float] = {}
    for rc in ref_cols:
        col_cells = [cells[rc]["score"] for _, si, _, cells in matched_results if si is not None and rc in cells]
        col_scores[rc] = round(sum(col_cells) / len(col_cells), 4) if col_cells else 0.0

    # Column mapping info for the response
    col_map_info = {rc: {"mapped_to": sc, "found": sc is not None} for rc, sc in col_map.items()}

    # Diff details (trimmed for payload size)
    MAX_DIFF = 100
    diff_rows = []
    for ri, si, row_score, cells in matched_results[:MAX_DIFF]:
        status = "match" if row_score >= 0.99 else ("partial" if si is not None else "missing")
        diff_rows.append({
            "ref_row": ri,
            "sub_row": si,
            "status": status,
            "row_score": round(row_score, 4),
            "cells": {
                rc: {"ref": c["ref"], "sub": c["sub"], "score": c["score"]}
                for rc, c in cells.items()
            } if cells else {},
        })

    grade = _grade(final_score)

    return {
        "score": final_score,
        "grade": grade,
        "matched_rows": matched_count,
        "partial_rows": partial_count,
        "missing_rows": missing_count,
        "extra_rows": extra_rows,
        "total_ref_rows": n_ref,
        "total_sub_rows": n_sub,
        "column_scores": col_scores,
        "column_mapping": col_map_info,
        "ref_columns": ref_cols,
        "sub_columns": sub_cols,
        "diff": diff_rows,
    }


def _grade(score: float) -> str:
    if score >= 95:
        return "S"
    if score >= 85:
        return "A"
    if score >= 70:
        return "B"
    if score >= 55:
        return "C"
    if score >= 35:
        return "D"
    return "F"
