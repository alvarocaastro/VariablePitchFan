from __future__ import annotations

import dataclasses
from dataclasses import dataclass

import numpy as np
import pandas as pd

from vpf_analysis.postprocessing.aerodynamics_utils import (
    compute_stall_alpha,
    find_second_peak_row,
)

# Weights for VPF fan airfoil scoring (post-normalisation, applied to [0,1] metrics).
# VPF rationale: blades pitch across a wide incidence range (takeoff → descent),
# so robustness to angle-of-attack variation and stall margin are more critical
# than peak L/D alone (which is the design-point cruise metric for fixed-pitch blades).
# Weight breakdown (sum=2.55):
#   WEIGHT_MAX_LD        0.75  — 29%: peak efficiency still matters but is not dominant
#   WEIGHT_STABILITY_MARGIN 1.00 — 39%: large stall margin needed for reverse-pitch authority
#   WEIGHT_ROBUSTNESS_LD 0.80  — 31%: wide L/D plateau across the operating incidence range
WEIGHT_MAX_LD = 0.75
WEIGHT_ROBUSTNESS_LD = 0.80
WEIGHT_STABILITY_MARGIN = 1.00


@dataclass(frozen=True)
class AirfoilScore:
    airfoil: str
    max_ld: float
    alpha_opt: float
    stall_alpha: float
    stability_margin: float
    robustness_ld: float
    total_score: float


def score_airfoil(df: pd.DataFrame) -> AirfoilScore:
    """Fan-oriented score for one airfoil polar.

    1. ``max_ld``: second L/D peak (alpha >= 3°) to skip laminar-bubble artefact.
    2. ``stall_alpha``: first alpha where CL drops >5% below CL_max.
    3. ``stability_margin``: stall_alpha - alpha_opt.
    4. ``robustness_ld``: mean L/D within ±FWHM/2 of the peak (resolution-independent).

    total_score is raw here; call ``normalise_scores`` to get normalised totals.
    """
    if df.empty:
        return AirfoilScore(
            airfoil="", max_ld=np.nan, alpha_opt=np.nan, stall_alpha=np.nan,
            stability_margin=np.nan, robustness_ld=np.nan, total_score=np.nan,
        )

    airfoil_name = str(df["airfoil"].iloc[0])
    valid = df.replace([np.inf, -np.inf], np.nan).dropna(subset=["ld", "alpha", "cl"])
    if valid.empty:
        return AirfoilScore(
            airfoil=airfoil_name, max_ld=np.nan, alpha_opt=np.nan, stall_alpha=np.nan,
            stability_margin=np.nan, robustness_ld=np.nan, total_score=np.nan,
        )

    row_opt = find_second_peak_row(valid, "ld", alpha_min=3.0)
    max_ld = float(row_opt["ld"])
    alpha_opt = float(row_opt["alpha"])

    stall_alpha = compute_stall_alpha(valid, "cl")
    stability_margin = max(0.0, stall_alpha - alpha_opt)

    # FWHM of L/D curve → window half-width independent of alpha-sweep resolution
    above_half = valid[valid["ld"] >= max_ld / 2.0]
    if len(above_half) >= 2:
        half_fwhm = (float(above_half["alpha"].max()) - float(above_half["alpha"].min())) / 2.0
    else:
        half_fwhm = 1.0
    df_window = valid[
        (valid["alpha"] >= alpha_opt - half_fwhm) & (valid["alpha"] <= alpha_opt + half_fwhm)
    ]
    robustness_ld = float(df_window["ld"].mean()) if not df_window.empty else max_ld

    total_score = (
        WEIGHT_MAX_LD * max_ld
        + WEIGHT_ROBUSTNESS_LD * robustness_ld
        + WEIGHT_STABILITY_MARGIN * stability_margin
    )

    return AirfoilScore(
        airfoil=airfoil_name,
        max_ld=max_ld,
        alpha_opt=alpha_opt,
        stall_alpha=stall_alpha,
        stability_margin=stability_margin,
        robustness_ld=robustness_ld,
        total_score=total_score,
    )


def aggregate_weighted_scores(
    scores_by_condition: dict[str, list[AirfoilScore]],
    weights: dict[str, float],
    primary_label: str | None = None,
) -> list[AirfoilScore]:
    """Aggregate per-condition normalised scores into a single mission-weighted score.

    For each condition the scores are normalised with ``normalise_scores`` (min-max
    across candidates within that condition).  The final ``total_score`` for each
    airfoil is the weighted mean of those normalised totals, ignoring conditions
    where XFOIL failed (NaN) and renormalising the weights accordingly.

    Display metrics (max_ld, alpha_opt, stall_alpha, stability_margin, robustness_ld)
    are taken from the condition with the highest weight (the *primary* condition),
    falling back to a weighted mean when the primary data are NaN.
    """
    if not scores_by_condition:
        return []

    # Normalise within each condition independently
    normalised: dict[str, list[AirfoilScore]] = {
        lbl: normalise_scores(scores) for lbl, scores in scores_by_condition.items()
    }

    labels = list(normalised.keys())
    n_airfoils = len(normalised[labels[0]])

    if primary_label is None or primary_label not in normalised:
        primary_label = max(weights, key=lambda l: weights.get(l, 0.0))

    result: list[AirfoilScore] = []
    for i in range(n_airfoils):
        airfoil_name = normalised[labels[0]][i].airfoil

        # Weighted total_score, skipping NaN conditions for this airfoil
        w_sum = 0.0
        weighted_total = 0.0
        for lbl in labels:
            s = normalised[lbl][i]
            if np.isnan(s.total_score):
                continue
            w = weights.get(lbl, 0.0)
            weighted_total += w * s.total_score
            w_sum += w

        agg_total = weighted_total / w_sum if w_sum > 0.0 else np.nan

        # Display metrics from primary condition; fall back to weighted mean when NaN
        primary = normalised[primary_label][i]
        if not np.isnan(primary.max_ld):
            disp = primary
            result.append(dataclasses.replace(disp, total_score=agg_total))
        else:
            # Weighted mean of non-NaN metric values across conditions
            def _wmean(attr: str) -> float:
                ws, vs = 0.0, 0.0
                for lbl in labels:
                    v = getattr(normalised[lbl][i], attr)
                    if not np.isnan(v):
                        w = weights.get(lbl, 0.0)
                        vs += w * v
                        ws += w
                return vs / ws if ws > 0.0 else np.nan

            result.append(AirfoilScore(
                airfoil=airfoil_name,
                max_ld=_wmean("max_ld"),
                alpha_opt=_wmean("alpha_opt"),
                stall_alpha=_wmean("stall_alpha"),
                stability_margin=_wmean("stability_margin"),
                robustness_ld=_wmean("robustness_ld"),
                total_score=agg_total,
            ))

    return result


def normalise_scores(scores: list[AirfoilScore]) -> list[AirfoilScore]:
    """Return new AirfoilScore list with total_score recomputed after min-max normalisation.

    Each component (max_ld, robustness_ld, stability_margin) is scaled to [0, 1]
    across all valid candidates before the weights are applied, so no single
    metric dominates by magnitude.
    """
    valid_idx = [i for i, s in enumerate(scores) if not np.isnan(s.max_ld)]
    if len(valid_idx) < 2:
        return scores

    def _minmax(vals: list[float]) -> list[float]:
        arr = np.array(vals, dtype=float)
        lo, hi = float(np.nanmin(arr)), float(np.nanmax(arr))
        if hi == lo:
            return [0.5] * len(vals)
        return [(v - lo) / (hi - lo) for v in vals]

    max_lds_n = _minmax([scores[i].max_ld for i in valid_idx])
    rob_n = _minmax([scores[i].robustness_ld for i in valid_idx])
    stab_n = _minmax([scores[i].stability_margin for i in valid_idx])

    result = list(scores)
    for j, i in enumerate(valid_idx):
        total = (
            WEIGHT_MAX_LD * max_lds_n[j]
            + WEIGHT_ROBUSTNESS_LD * rob_n[j]
            + WEIGHT_STABILITY_MARGIN * stab_n[j]
        )
        result[i] = dataclasses.replace(scores[i], total_score=float(total))
    return result
