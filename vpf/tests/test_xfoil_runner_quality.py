from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from vpf_analysis.xfoil_runner import (
    XfoilPolarRequest,
    _expected_alpha_values,
    _polar_coverage_quality,
)


def test_expected_alpha_values_match_aseq_grid() -> None:
    request = XfoilPolarRequest(
        airfoil_dat=Path("dummy.dat"),
        re=1.0e6,
        alpha_start=-0.3,
        alpha_end=0.3,
        alpha_step=0.15,
    )

    assert _expected_alpha_values(request) == [-0.3, -0.15, 0.0, 0.15, 0.3]


def test_polar_coverage_quality_counts_generated_rows(tmp_path: Path) -> None:
    polar = tmp_path / "polar.dat"
    polar.write_text(
        """
   alpha    CL        CD       CDp       CM     Top_Xtr  Bot_Xtr
  ------ -------- --------- --------- -------- -------- --------
  -1.000   0.1000   0.01000   0.00100  -0.0500   1.0000   1.0000
   0.000   0.2000   0.01100   0.00120  -0.0520   1.0000   1.0000
   1.000   0.3000   0.01200   0.00140  -0.0540   1.0000   1.0000
""",
        encoding="utf-8",
    )
    request = XfoilPolarRequest(
        airfoil_dat=tmp_path / "dummy.dat",
        re=1.0e6,
        alpha_start=-1.0,
        alpha_end=1.0,
        alpha_step=1.0,
        output_file=polar,
    )

    missing, rate, missing_alphas = _polar_coverage_quality(request, polar)

    assert missing == 0
    assert rate == pytest.approx(1.0)
    assert missing_alphas == []


def test_polar_coverage_quality_reports_missing_rows(tmp_path: Path) -> None:
    polar = tmp_path / "polar.dat"
    polar.write_text(
        """
   alpha    CL        CD       CDp       CM     Top_Xtr  Bot_Xtr
  ------ -------- --------- --------- -------- -------- --------
  -1.000   0.1000   0.01000   0.00100  -0.0500   1.0000   1.0000
   0.000   0.2000   0.01100   0.00120  -0.0520   1.0000   1.0000
""",
        encoding="utf-8",
    )
    request = XfoilPolarRequest(
        airfoil_dat=tmp_path / "dummy.dat",
        re=1.0e6,
        alpha_start=-1.0,
        alpha_end=1.0,
        alpha_step=1.0,
        output_file=polar,
    )

    missing, rate, missing_alphas = _polar_coverage_quality(request, polar)

    assert missing == 1
    assert rate == pytest.approx(2 / 3)
    assert missing_alphas == [1.0]


def test_polar_coverage_quality_detects_internal_missing_alpha(tmp_path: Path) -> None:
    polar = tmp_path / "polar.dat"
    polar.write_text(
        """
   alpha    CL        CD       CDp       CM     Top_Xtr  Bot_Xtr
  ------ -------- --------- --------- -------- -------- --------
  -1.000   0.1000   0.01000   0.00100  -0.0500   1.0000   1.0000
   1.000   0.3000   0.01200   0.00140  -0.0540   1.0000   1.0000
""",
        encoding="utf-8",
    )
    request = XfoilPolarRequest(
        airfoil_dat=tmp_path / "dummy.dat",
        re=1.0e6,
        alpha_start=-1.0,
        alpha_end=1.0,
        alpha_step=1.0,
        output_file=polar,
    )

    missing, rate, missing_alphas = _polar_coverage_quality(request, polar)

    assert missing == 1
    assert rate == pytest.approx(2 / 3)
    assert missing_alphas == [0.0]
