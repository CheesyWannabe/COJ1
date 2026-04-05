"""
Tests for the CSV Judge comparison engine.
Run: pytest tests/test_judge.py -v
"""

import pytest
from backend.judge import compare_csvs, CompareConfig


def cfg(**kwargs) -> CompareConfig:
    return CompareConfig(**kwargs)


# ─── helpers ──────────────────────────────────────────────────────────────────

def csv(*rows: str) -> str:
    return "\n".join(rows)


# ─── 1. Perfect match ─────────────────────────────────────────────────────────

def test_perfect_match():
    ref = csv("name,score", "Alice,90", "Bob,80", "Carol,70")
    sub = csv("name,score", "Alice,90", "Bob,80", "Carol,70")
    r = compare_csvs(ref, sub, cfg())
    assert r["score"] == 100.0
    assert r["matched_rows"] == 3
    assert r["missing_rows"] == 0


# ─── 2. Completely different ─────────────────────────────────────────────────

def test_completely_different():
    ref = csv("name,score", "Alice,90", "Bob,80")
    sub = csv("name,score", "Zzz,1", "Yyy,2")
    r = compare_csvs(ref, sub, cfg())
    assert r["score"] < 20.0


# ─── 3. Partial match ─────────────────────────────────────────────────────────

def test_partial_match():
    ref = csv("name,score", "Alice,90", "Bob,80", "Carol,70", "Dave,60")
    sub = csv("name,score", "Alice,90", "Bob,80", "Carol,71", "Dave,99")
    r = compare_csvs(ref, sub, cfg())
    assert 50.0 < r["score"] < 100.0


# ─── 4. Column order shuffled ────────────────────────────────────────────────

def test_column_order_shuffled():
    ref = csv("name,score,city", "Alice,90,NY", "Bob,80,LA")
    sub = csv("city,name,score", "NY,Alice,90", "LA,Bob,80")
    r = compare_csvs(ref, sub, cfg())
    assert r["score"] == 100.0


# ─── 5. Row order shuffled ───────────────────────────────────────────────────

def test_row_order_shuffled():
    ref = csv("name,score", "Alice,90", "Bob,80", "Carol,70")
    sub = csv("name,score", "Carol,70", "Alice,90", "Bob,80")
    r = compare_csvs(ref, sub, cfg())
    assert r["score"] == 100.0


# ─── 6. Missing rows in submission ───────────────────────────────────────────

def test_missing_rows():
    ref = csv("name,score", "Alice,90", "Bob,80", "Carol,70", "Dave,60")
    sub = csv("name,score", "Alice,90", "Bob,80")
    r = compare_csvs(ref, sub, cfg())
    assert r["missing_rows"] == 2
    assert r["score"] < 60.0


# ─── 7. Extra rows in submission ─────────────────────────────────────────────

def test_extra_rows_penalised():
    ref = csv("name,score", "Alice,90", "Bob,80")
    sub = csv("name,score", "Alice,90", "Bob,80", "Extra1,10", "Extra2,20")
    r_penalise = compare_csvs(ref, sub, cfg(penalize_extra=True))
    r_no_penalise = compare_csvs(ref, sub, cfg(penalize_extra=False))
    assert r_penalise["score"] < r_no_penalise["score"]
    assert r_no_penalise["score"] == 100.0


# ─── 8. Case insensitive ─────────────────────────────────────────────────────

def test_case_insensitive():
    ref = csv("name,city", "Alice,New York", "Bob,Boston")
    sub = csv("name,city", "ALICE,NEW YORK", "bob,boston")
    r = compare_csvs(ref, sub, cfg(lowercase=True))
    assert r["score"] == 100.0


def test_case_sensitive():
    ref = csv("name,city", "Alice,New York")
    sub = csv("name,city", "ALICE,NEW YORK")
    r = compare_csvs(ref, sub, cfg(lowercase=False))
    assert r["score"] < 100.0


# ─── 9. Numeric tolerance ────────────────────────────────────────────────────

def test_numeric_tolerance():
    ref = csv("val", "3.14159", "2.71828")
    sub = csv("val", "3.14160", "2.71829")
    r = compare_csvs(ref, sub, cfg(numeric_tolerance=True, tolerance=0.001))
    assert r["score"] == 100.0


def test_numeric_no_tolerance():
    ref = csv("val", "3.14159")
    sub = csv("val", "3.14160")
    r = compare_csvs(ref, sub, cfg(numeric_tolerance=False))
    assert r["score"] < 100.0


# ─── 10. Whitespace trimming ─────────────────────────────────────────────────

def test_whitespace_trimming():
    ref = csv("name", "Alice", "Bob")
    sub = csv("name", "  Alice  ", "  Bob  ")
    r = compare_csvs(ref, sub, cfg(trim=True))
    assert r["score"] == 100.0


# ─── 11. Empty cells ─────────────────────────────────────────────────────────

def test_empty_cells():
    ref = csv("name,score", "Alice,", "Bob,80")
    sub = csv("name,score", "Alice,", "Bob,80")
    r = compare_csvs(ref, sub, cfg())
    assert r["score"] == 100.0


# ─── 12. Duplicate rows ──────────────────────────────────────────────────────

def test_duplicate_rows():
    ref = csv("name,score", "Alice,90", "Alice,90", "Bob,80")
    sub = csv("name,score", "Alice,90", "Alice,90", "Bob,80")
    r = compare_csvs(ref, sub, cfg())
    assert r["score"] == 100.0


# ─── 13. Column name similarity ──────────────────────────────────────────────

def test_similar_column_names():
    ref = csv("Name,Score", "Alice,90", "Bob,80")
    sub = csv("name,score", "Alice,90", "Bob,80")
    r = compare_csvs(ref, sub, cfg(lowercase=True))
    assert r["score"] == 100.0


# ─── 14. Column weights ──────────────────────────────────────────────────────

def test_column_weights():
    ref = csv("name,score", "Alice,90", "Bob,80")
    sub = csv("name,score", "Alice,99", "Bob,99")  # names correct, scores wrong
    r_no_w = compare_csvs(ref, sub, cfg())
    r_name_heavy = compare_csvs(ref, sub, cfg(column_weights={"name": 10, "score": 1}))
    # name-heavy should score higher (names are all correct)
    assert r_name_heavy["score"] > r_no_w["score"]


# ─── 15. Single row ──────────────────────────────────────────────────────────

def test_single_row():
    ref = csv("x", "42")
    sub = csv("x", "42")
    r = compare_csvs(ref, sub, cfg())
    assert r["score"] == 100.0


# ─── 16. Malformed submission (extra/missing columns) ────────────────────────

def test_missing_column_in_submission():
    ref = csv("name,score,city", "Alice,90,NY")
    sub = csv("name,score", "Alice,90")  # missing city column
    r = compare_csvs(ref, sub, cfg())
    assert r["score"] < 100.0
    assert r["column_mapping"]["city"]["found"] is False
