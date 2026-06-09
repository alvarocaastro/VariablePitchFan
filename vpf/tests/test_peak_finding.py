"""Regression tests for find_second_peak_row and the laminar-bubble bug fix.

Key scenarios:
1. Polar with a laminar-bubble first peak at low alpha + stable second peak at higher alpha:
   must return the second peak.
2. Polar where XFOIL converged only at low alpha (simulates cruise convergence failure):
   must return NaN via ValueError rather than the laminar-bubble peak.
3. Polar with CD = 0 at one point: must not propagate inf into the result.
4. Empty polar: must raise ValueError.
5. cl_min filter: even without alpha_min, CL filter alone guards against the bubble.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from vpf_analysis.postprocessing.aerodynamics_utils import find_second_peak_row


def _make_polar(alphas, cls, cds) -> pd.DataFrame:
    ld = [cl / cd if cd > 1e-9 else float("nan") for cl, cd in zip(cls, cds)]
    return pd.DataFrame({"alpha": alphas, "cl": cls, "cd": cds, "ld": ld})


# ── Scenario 1: laminar bubble + stable second peak ──────────────────────────

def test_second_peak_selected_over_laminar_bubble():
    """Alpha-min filter must skip the laminar bubble (α=1.4°) and return the stable peak.

    Polar shape:
      α=1.4°: bubble peak  ld ≈ 0.6/0.006 = 100  (must be SKIPPED)
      α=7°:   stable peak  ld ≈ 1.08/0.0090 ≈ 120 (must be SELECTED)
    """
    alphas =  [-5,   -3,   -1,   0,    1,    1.4,  2,    3,    4,    5,    6,    7,    8,    9,    10]
    cls =     [-.3,  -.2,  -.05, .05,  .3,   .6,   .7,   .8,   .9,   1.0,  1.05, 1.08, 1.05, .95,  .80]
    # Note: ld at bubble (1.4°) = .6/.006=100; ld at 7° = 1.08/.009=120 — 7° is the true max
    cds =     [.02,  .018, .015, .013, .010, .006, .020, .014, .012, .011, .010, .009, .012, .015, .020]
    df = _make_polar(alphas, cls, cds)

    row = find_second_peak_row(df, "ld", alpha_min=3.0)
    assert float(row["alpha"]) >= 3.0, "Must skip laminar bubble (alpha < 3°)"
    assert float(row["alpha"]) == pytest.approx(7.0, abs=0.5)


# ── Scenario 2: only low-alpha data (cruise convergence failure) ──────────────

def test_cl_min_filter_returns_nan_when_only_laminar_bubble_available():
    """When XFOIL only converged up to alpha=2° (all CL < 0.3), cl_min filter
    must prevent selecting the bubble peak; find_second_peak_row should raise ValueError."""
    alphas = [-5, -3, -1, 0, 1, 1.4, 2.0]
    cls =    [-.3, -.2, -.05, .05, .15, .22, .28]   # all below CL_MIN_3D=0.30
    cds =    [.02, .018, .015, .013, .010, .006, .007]
    df = _make_polar(alphas, cls, cds)

    with pytest.raises(ValueError):
        find_second_peak_row(df, "ld", alpha_min=3.0, cl_min=0.30, cl_col="cl")


# ── Scenario 3: CD = 0 at one point — no inf propagation ─────────────────────

def test_cd_zero_does_not_propagate_inf():
    """A single CD=0 row must produce NaN in ld, not inf, and not corrupt peak selection."""
    alphas = [0, 2, 4, 6, 7, 8, 10]
    cls =    [.4, .6, .8, 1.0, 1.1, 1.05, .8]
    cds =    [.01, .009, 0.0, .0095, .010, .012, .018]   # CD=0 at alpha=4°
    df = _make_polar(alphas, cls, cds)

    row = find_second_peak_row(df, "ld", alpha_min=3.0)
    assert not np.isinf(float(row["ld"])), "inf must not appear in result"
    assert float(row["alpha"]) != pytest.approx(4.0, abs=0.1), "CD=0 point must be excluded"


# ── Scenario 4: empty polar ──────────────────────────────────────────────────

def test_empty_polar_raises():
    df = pd.DataFrame({"alpha": [], "cl": [], "cd": [], "ld": []})
    with pytest.raises(ValueError):
        find_second_peak_row(df, "ld")


# ── Scenario 5: cl_min alone guards against bubble (no alpha_min) ────────────

def test_cl_min_alone_skips_bubble():
    """Even with alpha_min=0, a CL filter of 0.5 must skip the low-CL laminar bubble."""
    alphas = [0, 0.5, 1.0, 1.4, 2.0, 5.0, 7.0, 9.0]
    cls =    [.05, .10, .18, .25, .35, .80, 1.0, .90]
    cds =    [.015, .012, .009, .006, .007, .009, .010, .013]
    df = _make_polar(alphas, cls, cds)

    row = find_second_peak_row(df, "ld", alpha_min=0.0, cl_min=0.5, cl_col="cl")
    assert float(row["cl"]) >= 0.5, "CL at result must be >= cl_min"
    assert float(row["alpha"]) >= 5.0


# ── Scenario 6: wave drag karman_tsien NaN trap ──────────────────────────────

def test_karman_tsien_ld_kt_no_inf():
    """ld_kt must contain no inf values for a normal polar run at M=0.85."""
    import numpy as _np
    from vpf_analysis.stage3_compressibility_correction.karman_tsien import KarmanTsienModel
    from vpf_analysis.stage3_compressibility_correction.compressibility_case import CompressibilityCase

    model = KarmanTsienModel(thickness_ratio=0.10, korn_kappa=0.87)
    df = pd.DataFrame({
        "alpha": [0.0, 5.0, 10.0, 15.0],
        "cl":    [0.3, 0.8, 1.1, 0.9],
        "cd":    [0.008, 0.009, 0.012, 0.020],
        "cm":    [-0.05, -0.07, -0.09, -0.08],
    })
    case = CompressibilityCase(flight_condition="cruise", reference_mach=0.2, target_mach=0.85)
    result = model.correct_polar(df, case)

    assert not _np.isinf(result["ld_kt"]).any(), "ld_kt must contain no inf values"
    assert result["ld_kt"].notna().all(), "ld_kt must have no NaN for a clean polar"


def test_stage3_trims_deep_post_stall_alpha():
    """Stage 3 should not carry deep post-stall points into correction models."""
    from vpf_analysis.stage3_compressibility_correction.correction_service import (
        CompressibilityCorrectionService,
    )

    df = pd.DataFrame({
        "alpha": list(range(-5, 24)),
        "cl": [
            -0.4, -0.3, -0.2, -0.1, 0.0,
            0.1, 0.2, 0.35, 0.5, 0.65,
            0.8, 0.95, 1.05, 1.15, 1.2,
            1.22, 1.18, 1.10, 0.95, 0.80,
            0.65, 0.50, 0.35, 0.20, 0.10,
            0.0, -0.05, -0.1, -0.15,
        ],
    })

    trimmed = CompressibilityCorrectionService._trim_post_stall_alpha(df)

    assert trimmed["alpha"].max() <= 17.0
    assert len(trimmed) < len(df)
