"""Unit tests for Stage 7 SFC improvement model."""

from __future__ import annotations

import math

import pytest

from vpf_analysis.stage7_sfc_analysis.engine.sfc_model import compute_sfc_improvement


def test_no_change_gives_zero_saving() -> None:
    result = compute_sfc_improvement(100.0, 100.0, 1e-5)
    assert result["fuel_saving_pct"] == pytest.approx(0.0, abs=1e-9)


def test_higher_clcd_gives_positive_saving() -> None:
    result = compute_sfc_improvement(100.0, 120.0, 1e-5)
    assert result["fuel_saving_pct"] > 0.0


def test_lower_clcd_gives_zero_saving() -> None:
    # VPF never operates at a worse Cl/Cd than fixed-pitch; improvement is clamped to 0.
    result = compute_sfc_improvement(100.0, 80.0, 1e-5)
    assert result["fuel_saving_pct"] == pytest.approx(0.0, abs=1e-9)


def test_efficiency_model_scales_with_tau() -> None:
    # Δη_fan = (ε−1)·τ when below cap; higher τ → larger SFC improvement.
    ref, new, sfc = 100.0, 103.0, 1e-5  # ε=1.03, below cap for all τ
    r_low  = compute_sfc_improvement(ref, new, sfc, tau=0.30)
    r_high = compute_sfc_improvement(ref, new, sfc, tau=0.65)
    assert r_high["fuel_saving_pct"] > r_low["fuel_saving_pct"] > 0.0


def test_f_ratio_is_unity() -> None:
    # Thrust is fixed by aircraft drag; F_ratio = 1 in the efficiency model.
    result = compute_sfc_improvement(80.0, 100.0, 1e-5)
    assert result["F_ratio"] == pytest.approx(1.0, rel=1e-9)


def test_return_keys_complete() -> None:
    result = compute_sfc_improvement(100.0, 110.0, 1e-5)
    required = {
        "ClCd_ref", "ClCd_new", "F_ratio",
        "SFC_design_kgNs", "SFC_new_kgNs",
        "SFC_improvement_pct", "fuel_saving_pct", "delta_SFC_kgNs",
    }
    assert required <= result.keys()
