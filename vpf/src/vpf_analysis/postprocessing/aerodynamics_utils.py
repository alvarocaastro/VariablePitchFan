"""Shared aerodynamic utilities: efficiency column resolution, peak finding, polar file lookup."""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import pandas as pd

LOGGER = logging.getLogger(__name__)

# Priority-ordered list of known efficiency column names.
_EFFICIENCY_COLUMNS: tuple[str, ...] = (
    "ld_corrected",
    "ld",
)

# Structural second-peak detection thresholds.
# The valley between the two peaks must dip ≥ this fraction below the first peak,
# and the second peak must rise ≥ this fraction above the valley.
_VALLEY_DIP_MIN_REL: float = 0.05   # 5 % dip required for a true valley
_PEAK2_RISE_MIN_REL: float = 0.02   # 2 % rise required for a true second peak
_PEAK2_ALPHA_MIN_DEG: float = 5.0   # structural second peak must be at α ≥ 5°


def resolve_efficiency_column(df: pd.DataFrame) -> str:
    """Return the first available efficiency column (``ld_corrected`` → ``ld``).

    Raises ``KeyError`` if none is present.
    """
    for col in _EFFICIENCY_COLUMNS:
        if col in df.columns:
            return col
    raise KeyError(
        f"No efficiency column found. Available: {list(df.columns)}"
    )


def _detect_structural_second_peak(
    df_sorted: pd.DataFrame,
    efficiency_col: str,
    cl_min: float | None,
    cl_col: str,
) -> pd.Series | None:
    """Return the structural second-peak row if the double-hump shape is confirmed.

    Algorithm:
    1. Find global efficiency maximum (first structural peak, often the laminar bubble).
    2. Search for the valley in a limited window [α_peak + 0, α_peak + 12°] so the
       monotone descent at high alpha does not masquerade as a "valley".
    3. Find the maximum after the valley (second structural peak).
    4. Validate: valley dips ≥ 5 % below first peak AND second peak rises ≥ 2 %
       above valley AND second peak is at α ≥ 5°.

    Returns ``None`` if the double-hump shape is not confirmed so callers can fall
    back to the classic alpha_min-filter approach.
    """
    eff_arr = df_sorted[efficiency_col].to_numpy()
    alpha_arr = df_sorted["alpha"].to_numpy()
    n = len(eff_arr)

    if n < 5:
        return None

    i_gmax = int(np.argmax(eff_arr))
    eff_gmax = eff_arr[i_gmax]
    alpha_gmax = alpha_arr[i_gmax]

    if i_gmax >= n - 2:
        return None

    # Limit valley search to a 12° window after the first peak.
    # This prevents np.argmin from latching onto the monotone end-of-polar
    # descent which is not a true inter-hump valley.
    alpha_valley_cutoff = alpha_gmax + 12.0
    i_valley_end = int(np.searchsorted(alpha_arr, alpha_valley_cutoff, side="right"))
    i_valley_end = min(i_valley_end, n - 1)  # stay in bounds

    if i_valley_end <= i_gmax + 1:
        return None

    window = eff_arr[i_gmax + 1 : i_valley_end]
    i_valley = i_gmax + 1 + int(np.argmin(window))
    eff_valley = eff_arr[i_valley]

    if i_valley >= n - 1:
        return None

    tail2_eff = eff_arr[i_valley + 1:]
    i_peak2 = i_valley + 1 + int(np.argmax(tail2_eff))
    eff_peak2 = eff_arr[i_peak2]
    alpha_peak2 = alpha_arr[i_peak2]

    valley_ok = eff_valley < eff_gmax * (1.0 - _VALLEY_DIP_MIN_REL)
    rise_ok   = eff_peak2 > eff_valley * (1.0 + _PEAK2_RISE_MIN_REL)
    alpha_ok  = alpha_peak2 >= _PEAK2_ALPHA_MIN_DEG

    if not (valley_ok and rise_ok and alpha_ok):
        return None

    row = df_sorted.iloc[i_peak2]

    # Honour the CL filter if requested.
    if cl_min is not None and cl_col in df_sorted.columns:
        if float(row.get(cl_col, cl_min)) < cl_min:
            return None

    LOGGER.debug(
        "Structural second peak at α=%.1f° (eff=%.2f); "
        "first peak α=%.1f° (eff=%.2f), valley α=%.1f° (eff=%.2f).",
        alpha_peak2, eff_peak2,
        alpha_arr[i_gmax], eff_gmax,
        alpha_arr[i_valley], eff_valley,
    )
    return row


def find_second_peak_row(
    df: pd.DataFrame,
    efficiency_col: str,
    alpha_min: float | None = None,
    cl_min: float | None = None,
    cl_col: str = "cl",
) -> pd.Series:
    """Return the row at the structural second aerodynamic peak.

    NACA 65-series polars show a double-humped CL/CD curve: a first (laminar
    bubble) peak at α ≈ 0–2° and a structural second peak at α ≈ 9–12°.  The
    function first tries to detect the structural second peak directly (global
    max → valley → max after valley).  If the double-hump shape is not
    confirmed it falls back to the classic approach: return ``idxmax`` for
    rows with α ≥ *alpha_min* (default 3°) and optionally CL ≥ *cl_min*.

    Raises ``ValueError`` if no valid row can be found at all.
    """
    if alpha_min is None:
        from vpf_analysis.settings import get_settings
        alpha_min = get_settings().physics.ALPHA_MIN_OPT_DEG

    df_clean = df.replace([np.inf, -np.inf], np.nan).dropna(
        subset=[efficiency_col, "alpha"]
    )
    if df_clean.empty:
        raise ValueError(
            f"No valid data after removing inf/nan values "
            f"(efficiency column: '{efficiency_col}')."
        )

    df_sorted = df_clean.sort_values("alpha").reset_index(drop=True)

    # --- Structural second-peak detection (primary path) ---
    structural_row = _detect_structural_second_peak(df_sorted, efficiency_col, cl_min, cl_col)
    if structural_row is not None:
        return structural_row

    # --- Fallback: alpha_min filter + idxmax ---
    alpha_mask = df_clean["alpha"] >= alpha_min
    if cl_min is not None and cl_col in df_clean.columns:
        cl_mask = df_clean[cl_col] >= cl_min
        df_peak = df_clean[alpha_mask & cl_mask]
        if df_peak.empty:
            df_peak = df_clean[cl_mask]
            if not df_peak.empty:
                LOGGER.warning(
                    "No data at alpha >= %.1f° with CL >= %.2f. "
                    "Relaxing alpha constraint (CL filter kept).",
                    alpha_min, cl_min,
                )
    else:
        df_peak = df_clean[alpha_mask]

    if df_peak.empty:
        if cl_min is not None:
            raise ValueError(
                f"No data with CL >= {cl_min} (column '{cl_col}') in polar. "
                "Cannot determine second aerodynamic peak."
            )
        LOGGER.debug(
            "No data at alpha >= %.1f°. Falling back to full data range.", alpha_min
        )
        df_peak = df_clean

    return df_peak.loc[df_peak[efficiency_col].idxmax()]


def compute_stall_alpha(df: pd.DataFrame, cl_col: str) -> float:
    """Estimate the stall angle: first alpha where CL drops >5 % below CL_max.

    Returns the last available alpha if no clear stall is detected.
    """
    df_clean = (
        df[["alpha", cl_col]]
        .replace([np.inf, -np.inf], np.nan)
        .dropna()
        .sort_values("alpha")
        .reset_index(drop=True)
    )

    if df_clean.empty:
        raise ValueError(f"No valid data in polar for stall detection (column: '{cl_col}').")

    idx_clmax = int(df_clean[cl_col].idxmax())
    cl_max = float(df_clean[cl_col].iloc[idx_clmax])
    threshold = 0.05 * cl_max

    post_peak = df_clean.iloc[idx_clmax + 1 :]
    stall_rows = post_peak[post_peak[cl_col] < (cl_max - threshold)]

    if stall_rows.empty:
        alpha_stall = float(df_clean["alpha"].iloc[-1])
        LOGGER.debug(
            "No clear stall detected (CL never drops %.0f%% below CL_max=%.3f). "
            "Using last alpha=%.2f° as stall estimate.",
            5,
            cl_max,
            alpha_stall,
        )
        return alpha_stall

    return float(stall_rows["alpha"].iloc[0])


def lookup_efficiency_at_alpha(
    df: pd.DataFrame,
    efficiency_col: str,
    alpha_target: float,
) -> float:
    """Return efficiency at the polar point closest to *alpha_target*."""
    df_clean = (
        df[["alpha", efficiency_col]]
        .replace([np.inf, -np.inf], np.nan)
        .dropna()
    )
    if df_clean.empty:
        return float("nan")
    idx = (df_clean["alpha"] - alpha_target).abs().idxmin()
    return float(df_clean.loc[idx, efficiency_col])


def resolve_polar_file(base_dir: Path, condition: str, section: str) -> Path | None:
    """Locate a polar CSV: hierarchical Stage-3/Stage-2 layout, then flat fallback."""
    base = base_dir / condition.lower() / section
    for name in ("corrected_polar.csv", "polar.csv"):
        candidate = base / name
        if candidate.exists():
            return candidate

    flat = base_dir / f"{condition}_{section}.csv"
    if flat.exists():
        return flat

    return None
