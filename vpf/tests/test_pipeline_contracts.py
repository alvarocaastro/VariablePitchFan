"""
Tests for pipeline stage contracts.

Verifies that each StageNResult.validate() correctly enforces its
output invariants: required directories, minimum artifact counts,
and key scalar constraints.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from vpf_analysis.pipeline.contracts import (
    Stage4Result,
    Stage5Result,
    Stage6Result,
    Stage7Result,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_dirs(*paths: Path) -> None:
    for p in paths:
        p.mkdir(parents=True, exist_ok=True)


def _valid_s6(tmp_path: Path, **kwargs) -> Stage6Result:
    tables_dir  = tmp_path / "tables"
    figures_dir = tmp_path / "figures"
    _make_dirs(tables_dir, figures_dir)
    defaults = dict(
        tables_dir=tables_dir,
        figures_dir=figures_dir,
        n_tables=1,
        n_figures=1,
        mechanism_weight_kg=634.0,
        sfc_cruise_penalty_pct=0.66,
        stage_dir=tmp_path,
    )
    defaults.update(kwargs)
    return Stage6Result(**defaults)


def _valid_s7(tmp_path: Path, **kwargs) -> Stage7Result:
    tables_dir  = tmp_path / "tables"
    figures_dir = tmp_path / "figures"
    _make_dirs(tables_dir, figures_dir)
    defaults = dict(
        tables_dir=tables_dir,
        figures_dir=figures_dir,
        mean_sfc_reduction_pct=2.61,
        stage_dir=tmp_path,
    )
    defaults.update(kwargs)
    return Stage7Result(**defaults)


# ---------------------------------------------------------------------------
# Stage4Result
# ---------------------------------------------------------------------------

class TestStage4ResultValidation:

    def test_passes_with_valid_metrics_and_dirs(self, tmp_path: Path) -> None:
        tables_dir  = tmp_path / "tables"
        figures_dir = tmp_path / "figures"
        _make_dirs(tables_dir, figures_dir)

        s4 = Stage4Result(
            metrics=[object()],
            tables_dir=tables_dir,
            figures_dir=figures_dir,
            stage_dir=tmp_path,
        )
        s4.validate()

    def test_raises_when_metrics_empty(self, tmp_path: Path) -> None:
        tables_dir = tmp_path / "tables"
        _make_dirs(tables_dir)

        s4 = Stage4Result(
            metrics=[],
            tables_dir=tables_dir,
            figures_dir=tmp_path / "figures",
            stage_dir=tmp_path,
        )
        with pytest.raises(ValueError, match="metrics list is empty"):
            s4.validate()

    def test_raises_when_tables_dir_missing(self, tmp_path: Path) -> None:
        s4 = Stage4Result(
            metrics=[object()],
            tables_dir=tmp_path / "nonexistent_tables",
            figures_dir=tmp_path,
            stage_dir=tmp_path,
        )
        with pytest.raises((ValueError, FileNotFoundError)):
            s4.validate()


# ---------------------------------------------------------------------------
# Stage5Result
# ---------------------------------------------------------------------------

class TestStage5ResultValidation:

    def test_passes_at_minimum_table_count(self, tmp_path: Path) -> None:
        tables_dir  = tmp_path / "tables"
        figures_dir = tmp_path / "figures"
        _make_dirs(tables_dir, figures_dir)

        s5 = Stage5Result(
            tables_dir=tables_dir,
            figures_dir=figures_dir,
            n_tables=9,
            n_figures=16,
            twist_total_deg=5.0,
            max_off_design_loss_pct=2.0,
            stage_dir=tmp_path,
        )
        s5.validate()

    def test_raises_when_fewer_than_9_tables(self, tmp_path: Path) -> None:
        tables_dir  = tmp_path / "tables"
        figures_dir = tmp_path / "figures"
        _make_dirs(tables_dir, figures_dir)

        s5 = Stage5Result(
            tables_dir=tables_dir,
            figures_dir=figures_dir,
            n_tables=8,
            n_figures=16,
            twist_total_deg=5.0,
            max_off_design_loss_pct=2.0,
            stage_dir=tmp_path,
        )
        with pytest.raises(ValueError, match="tables"):
            s5.validate()

    def test_raises_when_tables_dir_missing(self, tmp_path: Path) -> None:
        s5 = Stage5Result(
            tables_dir=tmp_path / "missing_tables",
            figures_dir=tmp_path,
            n_tables=9,
            n_figures=16,
            twist_total_deg=5.0,
            max_off_design_loss_pct=2.0,
            stage_dir=tmp_path,
        )
        with pytest.raises((ValueError, FileNotFoundError)):
            s5.validate()

    def test_raises_when_figures_dir_missing(self, tmp_path: Path) -> None:
        tables_dir = tmp_path / "tables"
        _make_dirs(tables_dir)

        s5 = Stage5Result(
            tables_dir=tables_dir,
            figures_dir=tmp_path / "missing_figures",
            n_tables=9,
            n_figures=16,
            twist_total_deg=5.0,
            max_off_design_loss_pct=2.0,
            stage_dir=tmp_path,
        )
        with pytest.raises((ValueError, FileNotFoundError)):
            s5.validate()

    def test_nan_twist_blocks_validation(self, tmp_path: Path) -> None:
        tables_dir  = tmp_path / "tables"
        figures_dir = tmp_path / "figures"
        _make_dirs(tables_dir, figures_dir)

        s5 = Stage5Result(
            tables_dir=tables_dir,
            figures_dir=figures_dir,
            n_tables=9,
            n_figures=0,
            twist_total_deg=float("nan"),
            max_off_design_loss_pct=float("nan"),
            stage_dir=tmp_path,
        )
        with pytest.raises(ValueError, match="twist_total_deg is NaN"):
            s5.validate()


# ---------------------------------------------------------------------------
# Stage6Result — Reverse Thrust Modeling
# ---------------------------------------------------------------------------

class TestStage6ResultValidation:

    def test_passes_with_valid_mechanism_weight(self, tmp_path: Path) -> None:
        _valid_s6(tmp_path).validate()

    def test_raises_when_no_tables(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="tables"):
            _valid_s6(tmp_path, n_tables=0).validate()

    def test_raises_when_mechanism_weight_zero(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="mechanism_weight"):
            _valid_s6(tmp_path, mechanism_weight_kg=0.0).validate()

    def test_raises_when_tables_dir_missing(self, tmp_path: Path) -> None:
        tables_dir  = tmp_path / "missing_tables"
        figures_dir = tmp_path / "figures"
        _make_dirs(figures_dir)
        s6 = Stage6Result(
            tables_dir=tables_dir,
            figures_dir=figures_dir,
            n_tables=1,
            n_figures=1,
            mechanism_weight_kg=634.0,
            sfc_cruise_penalty_pct=0.66,
            stage_dir=tmp_path,
        )
        with pytest.raises((ValueError, FileNotFoundError)):
            s6.validate()

    def test_raises_when_figures_dir_missing(self, tmp_path: Path) -> None:
        tables_dir  = tmp_path / "tables"
        _make_dirs(tables_dir)
        s6 = Stage6Result(
            tables_dir=tables_dir,
            figures_dir=tmp_path / "missing_figures",
            n_tables=1,
            n_figures=1,
            mechanism_weight_kg=634.0,
            sfc_cruise_penalty_pct=0.66,
            stage_dir=tmp_path,
        )
        with pytest.raises((ValueError, FileNotFoundError)):
            s6.validate()


# ---------------------------------------------------------------------------
# Stage7Result — SFC Impact Analysis
# ---------------------------------------------------------------------------

class TestStage7ResultValidation:

    def test_passes_with_valid_sfc_reduction(self, tmp_path: Path) -> None:
        _valid_s7(tmp_path).validate()

    def test_raises_when_sfc_reduction_is_nan(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="NaN"):
            _valid_s7(tmp_path, mean_sfc_reduction_pct=float("nan")).validate()

    def test_raises_when_tables_dir_missing(self, tmp_path: Path) -> None:
        figures_dir = tmp_path / "figures"
        _make_dirs(figures_dir)
        s7 = Stage7Result(
            tables_dir=tmp_path / "missing_tables",
            figures_dir=figures_dir,
            mean_sfc_reduction_pct=2.61,
            stage_dir=tmp_path,
        )
        with pytest.raises((ValueError, FileNotFoundError)):
            s7.validate()

    def test_raises_when_figures_dir_missing(self, tmp_path: Path) -> None:
        tables_dir = tmp_path / "tables"
        _make_dirs(tables_dir)
        s7 = Stage7Result(
            tables_dir=tables_dir,
            figures_dir=tmp_path / "missing_figures",
            mean_sfc_reduction_pct=2.61,
            stage_dir=tmp_path,
        )
        with pytest.raises((ValueError, FileNotFoundError)):
            s7.validate()

    @pytest.mark.parametrize("sfc_pct", [0.0, 0.5, 2.61, 5.0, -0.1])
    def test_accepts_any_finite_sfc_reduction(self, tmp_path: Path, sfc_pct: float) -> None:
        _valid_s7(tmp_path, mean_sfc_reduction_pct=sfc_pct).validate()
