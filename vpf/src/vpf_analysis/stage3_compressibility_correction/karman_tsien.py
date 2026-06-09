"""Kármán–Tsien compressibility correction model.

The Kármán–Tsien rule is a higher-order (non-linear) correction more accurate
than Prandtl-Glauert above M ≈ 0.5.  Correction applied to the pressure
coefficient:

    Cp_KT = Cp_0 / (β + M²/(2(1+β)) × Cp_0)

For bulk lift-polar correction (thin-airfoil, Cp ≈ −CL/n) this gives a
point-wise CL correction.  Cm is scaled by the same CL correction factor
(both arise from the pressure distribution; applying the KT denominator to
Cm directly has no physical basis).

Wave drag above Mdd uses Lock's 4th-power law.  Points computed with
M_target > 0.90 are flagged as extrapolated in ``cd_wave_extrapolated``.

References:
    von Kármán, T. (1941). J. Aeronautical Sciences, 8(9), 337-356.
    Tsien, H.S. (1939). J. Aeronautical Sciences, 6(10), 399-407.
"""

from __future__ import annotations

import logging
import math

import numpy as np
import pandas as pd

from vpf_analysis.stage3_compressibility_correction.compressibility_case import (
    CompressibilityCase,
)
from vpf_analysis.stage3_compressibility_correction.critical_mach import (
    estimate_mdd,
    wave_drag_increment,
)

LOGGER = logging.getLogger(__name__)

_MACH_WAVE_DRAG_VALID_MAX = 0.90
_KT_RANGE_WARNED_MACHS: set[int] = set()   # int(M*1000) — rate-limit per unique M
_KT_EXTRAP_WARNED_MACHS: set[int] = set()  # int(M*1000) — rate-limit per unique M


class KarmanTsienModel:
    """Kármán–Tsien compressibility correction with Lock wave-drag."""

    def __init__(self, thickness_ratio: float = 0.10, korn_kappa: float = 0.87) -> None:
        self._tc = thickness_ratio
        self._kappa = korn_kappa

    @staticmethod
    def _kt_denominator(cl: float, mach: float) -> float:
        # Kármán-Tsien denominator for the CL-based correction (thin-airfoil form).
        # For a thin airfoil: Cp_0 ≈ −CL/n (n a geometry factor absorbed into calibration).
        # The correction applied point-wise to CL gives:
        #   CL_KT / CL_0 = denom(M_ref, CL_0) / denom(M_tgt, CL_0)
        # where denom(M, CL) = β + M²/(2(1+β)) × CL,  β = √(1−M²).
        # Source: von Kármán (1941) J. Aeronautical Sciences 8(9) 337-356,
        #         Anderson (2017) Fundamentals of Aerodynamics eq. 11.60.
        beta = math.sqrt(1.0 - mach * mach)
        return beta + (mach * mach / (2.0 * (1.0 + beta))) * cl

    def correct_polar(self, df: pd.DataFrame, case: CompressibilityCase) -> pd.DataFrame:
        """Apply Kármán–Tsien correction to polar data.

        Adds cl_kt, ld_kt, cm_kt (if cm present), cd_corrected, and
        cd_wave_extrapolated to the DataFrame.
        """
        from vpf_analysis.settings import get_settings
        kt_max = get_settings().physics.MACH_KT_VALID_MAX

        df_out = df.copy()
        cl_0 = df["cl"].values
        m_ref = case.reference_mach
        m_tgt = case.target_mach

        # KT is still the best subsonic model up to M~0.95; warn but never fall
        # back to PG, which over-estimates the correction linearly and loses the
        # non-linear behaviour near sonic.
        m_key = int(round(m_tgt * 1000))
        if m_tgt > kt_max and m_key not in _KT_RANGE_WARNED_MACHS:
            _KT_RANGE_WARNED_MACHS.add(m_key)
            LOGGER.warning(
                "M_target=%.3f exceeds KT experimental validation range (%.2f). "
                "Applying KT regardless — better than PG at this Mach.",
                m_tgt, kt_max,
            )

        # ── CL correction ────────────────────────────────────────────────────
        cl_kt: list[float] = []
        for cl in cl_0:
            denom_tgt = self._kt_denominator(cl, m_tgt)
            denom_ref = self._kt_denominator(cl, m_ref)
            if abs(denom_tgt) < 1e-6 or abs(denom_ref) < 1e-6:
                cl_kt.append(float("nan"))
            else:
                cl_kt.append(cl * denom_ref / denom_tgt)

        df_out["cl_kt"] = cl_kt

        # ── Cm correction — scale by the same CL factor ──────────────────────
        # Applying the KT denominator to cm directly has no physical basis; both
        # CL and Cm arise from the pressure distribution, so they share the factor.
        if "cm" in df.columns:
            cm_kt: list[float] = []
            for cm, cl, cl_c in zip(df["cm"].values, cl_0, cl_kt):
                if abs(cl) < 1e-9 or math.isnan(cl_c):
                    cm_kt.append(float("nan"))
                else:
                    cm_kt.append(cm * cl_c / cl)
            df_out["cm_kt"] = cm_kt

        # ── Wave drag ────────────────────────────────────────────────────────
        if m_tgt > _MACH_WAVE_DRAG_VALID_MAX and m_key not in _KT_EXTRAP_WARNED_MACHS:
            _KT_EXTRAP_WARNED_MACHS.add(m_key)
            LOGGER.warning(
                "M_target=%.3f > %.2f: Lock's law is extrapolated. "
                "cd_wave_extrapolated flag set in output.",
                m_tgt, _MACH_WAVE_DRAG_VALID_MAX,
            )

        cd_corrected: list[float] = []
        for cl, cd in zip(cl_0, df["cd"].values):
            # Do not clamp CL to 0: Korn's equation handles negative CL correctly,
            # and clamping creates an asymmetric drag correction at negative pitch angles.
            mdd = estimate_mdd(cl, self._tc, self._kappa)
            cd_corrected.append(cd + wave_drag_increment(m_tgt, mdd))

        df_out["cd_corrected"] = cd_corrected
        df_out["cd_wave_extrapolated"] = m_tgt > _MACH_WAVE_DRAG_VALID_MAX

        # ── Efficiencies ─────────────────────────────────────────────────────
        _cd_arr = np.array(df_out["cd_corrected"], dtype=float)
        _cl_kt_arr = np.array(df_out["cl_kt"], dtype=float)
        with np.errstate(divide="ignore", invalid="ignore"):
            df_out["ld_kt"] = np.where(
                (_cd_arr > 1e-9) & np.isfinite(_cl_kt_arr),
                _cl_kt_arr / _cd_arr,
                np.nan,
            )

        if "cl_pg" in df_out.columns:
            _cl_pg_arr = np.array(df_out["cl_pg"], dtype=float)
            with np.errstate(divide="ignore", invalid="ignore"):
                df_out["ld_pg"] = np.where(
                    (_cd_arr > 1e-9) & np.isfinite(_cl_pg_arr),
                    _cl_pg_arr / _cd_arr,
                    np.nan,
                )

        return df_out
