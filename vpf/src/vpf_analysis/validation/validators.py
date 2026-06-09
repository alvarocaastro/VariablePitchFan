"""validators.py — centralised validations for the VPF pipeline."""

from __future__ import annotations

import logging
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

LOGGER = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 1. File and directory validations
# ---------------------------------------------------------------------------

def require_file(path: Path, label: str = "") -> None:
    """Raise FileNotFoundError with context if *path* does not exist or is not a file."""
    ctx = f" [{label}]" if label else ""
    if not path.exists():
        raise FileNotFoundError(f"Required file not found{ctx}: {path}")
    if not path.is_file():
        raise FileNotFoundError(f"Path exists but is not a file{ctx}: {path}")


def require_dir(path: Path, label: str = "") -> None:
    """Raise FileNotFoundError if *path* does not exist or is not a directory."""
    ctx = f" [{label}]" if label else ""
    if not path.exists():
        raise FileNotFoundError(f"Required directory not found{ctx}: {path}")
    if not path.is_dir():
        raise FileNotFoundError(f"Path exists but is not a directory{ctx}: {path}")


def require_csv_columns(
    df: pd.DataFrame,
    required: Sequence[str],
    context: str = "",
) -> None:
    """Raise ValueError if expected columns are missing from a DataFrame."""
    missing = sorted(set(required) - set(df.columns))
    if missing:
        ctx = f" [{context}]" if context else ""
        raise ValueError(
            f"Missing columns in DataFrame{ctx}: {missing}. "
            f"Present columns: {sorted(df.columns.tolist())}"
        )


# ---------------------------------------------------------------------------
# 2. Physical range validations
# ---------------------------------------------------------------------------

def validate_physical_ranges(
    re: float,
    mach: float,
    context: str = "",
) -> None:
    """Validate that Re and Mach are within physically reasonable ranges."""
    ctx = f" [{context}]" if context else ""
    from vpf_analysis.settings import get_settings
    p = get_settings().physics

    if re <= 0 or re > p.REYNOLDS_MAX:
        raise ValueError(
            f"Reynolds out of range{ctx}: Re={re:.3e} "
            f"(expected: 0 < Re ≤ {p.REYNOLDS_MAX:.0e})"
        )
    if re < p.REYNOLDS_MIN:
        LOGGER.warning(
            "Low Reynolds%s: Re=%.2e (recommended minimum: %.0e)",
            ctx, re, p.REYNOLDS_MIN,
        )
    if mach < 0 or mach >= p.MACH_MAX_SUBSONIC:
        raise ValueError(
            f"Mach out of range{ctx}: M={mach:.3f} "
            f"(expected: 0 ≤ M < {p.MACH_MAX_SUBSONIC})"
        )


def validate_alpha_range(
    alpha_min: float,
    alpha_max: float,
    alpha_step: float,
    context: str = "",
) -> None:
    """Validate consistency of the angle-of-attack sweep range."""
    ctx = f" [{context}]" if context else ""
    if alpha_min >= alpha_max:
        raise ValueError(
            f"Inconsistent alpha range{ctx}: min={alpha_min}° ≥ max={alpha_max}°"
        )
    if alpha_step <= 0:
        raise ValueError(
            f"Invalid alpha step{ctx}: step={alpha_step}° must be > 0"
        )
    n_points = (alpha_max - alpha_min) / alpha_step
    if n_points < 10:
        LOGGER.warning(
            "Alpha range%s yields only %.0f points (min=%.1f, max=%.1f, step=%.2f) — "
            "polar may be insufficient.",
            ctx, n_points, alpha_min, alpha_max, alpha_step,
        )


# ---------------------------------------------------------------------------
# 3. Polar validations
# ---------------------------------------------------------------------------

def validate_polar_df(
    df: pd.DataFrame,
    context: str = "",
    min_rows: int | None = None,
) -> None:
    """Validate that a polar has sufficient data and required columns (alpha, cl, cd)."""
    from vpf_analysis.settings import get_settings
    p = get_settings().physics

    if min_rows is None:
        min_rows = p.POLAR_MIN_ROWS

    ctx = f" [{context}]" if context else ""

    if df is None or df.empty:
        raise ValueError(f"Empty polar{ctx}")

    if len(df) < min_rows:
        raise ValueError(
            f"Insufficient polar{ctx}: {len(df)} rows (minimum {min_rows}). "
            "Possible XFOIL convergence failure or alpha range too narrow."
        )

    require_csv_columns(df, ["alpha", "cl", "cd"], context)


@dataclass
class PolarQualityWarning:
    """Quality warning for an aerodynamic polar."""
    context: str
    code: str
    message: str


def validate_polar_quality(
    df: pd.DataFrame,
    context: str = "",
) -> list[PolarQualityWarning]:
    """Check aerodynamic quality indicators of a polar. Returns warnings; does not raise."""
    warnings: list[PolarQualityWarning] = []

    if df.empty:
        return warnings

    cl_max = df["cl"].max()
    cd_min = df["cd"].min()
    alpha_range = df["alpha"].max() - df["alpha"].min()

    if cl_max < 0.3:
        warnings.append(PolarQualityWarning(
            context=context, code="LOW_CL_MAX",
            message=f"CL_max={cl_max:.3f} < 0.3 — polar possibly not converged",
        ))

    if cd_min <= 0:
        warnings.append(PolarQualityWarning(
            context=context, code="NON_PHYSICAL_CD",
            message=f"CD_min={cd_min:.4f} ≤ 0 — non-physical value",
        ))

    if cd_min > 0.05:
        warnings.append(PolarQualityWarning(
            context=context, code="HIGH_CD_MIN",
            message=f"CD_min={cd_min:.4f} > 0.05 — high base drag (high Re or Mach?)",
        ))

    if alpha_range < 10.0:
        warnings.append(PolarQualityWarning(
            context=context, code="NARROW_ALPHA_RANGE",
            message=(
                f"Alpha range = {alpha_range:.1f}° < 10° — "
                "may not cover CL peak or stall"
            ),
        ))

    # Detect monotonically increasing CL without stall peak (truncated polar)
    if len(df) > 5:
        sorted_df = df.sort_values("alpha")
        positive_alpha = sorted_df[sorted_df["alpha"] > 5.0]
        if not positive_alpha.empty:
            cl_diff = positive_alpha["cl"].diff().dropna()
            if (cl_diff > 0).all():
                warnings.append(PolarQualityWarning(
                    context=context, code="NO_STALL_DETECTED",
                    message=(
                        "CL monotonically increasing at α > 5° — "
                        "possible polar truncated before stall"
                    ),
                ))

    return warnings


# ---------------------------------------------------------------------------
# 4. XFOIL convergence
# ---------------------------------------------------------------------------

@dataclass
class XfoilConvergenceInfo:
    """Result of parsing XFOIL stdout for convergence information."""
    n_convergence_failures: int = 0
    n_points_computed: int = 0
    failed_alpha_values: list[float] = field(default_factory=list)
    raw_warnings: list[str] = field(default_factory=list)

    @property
    def has_failures(self) -> bool:
        return self.n_convergence_failures > 0

    @property
    def convergence_rate(self) -> float:
        """Fraction of converged points (0–1)."""
        total = self.n_convergence_failures + self.n_points_computed
        if total == 0:
            return 0.0
        return self.n_points_computed / total


def check_xfoil_convergence(stdout: str) -> XfoilConvergenceInfo:
    """Parse XFOIL stdout and extract convergence information."""
    failures = 0
    computed = 0
    failed_alphas: list[float] = []
    raw_warnings: list[str] = []
    last_alpha: float | None = None

    _re_alpha_attempt = re.compile(r"a\s*=\s*([-\d.]+)", re.IGNORECASE)
    _re_converged    = re.compile(r"CL\s*=\s*[-\d.]+.*CD\s*=", re.IGNORECASE)
    _re_failure      = re.compile(r"convergence\s+failed", re.IGNORECASE)

    for line in stdout.splitlines():
        m_alpha = _re_alpha_attempt.search(line)
        if m_alpha:
            try:
                last_alpha = float(m_alpha.group(1))
            except ValueError:
                pass

        if _re_converged.search(line):
            computed += 1
            last_alpha = None

        if _re_failure.search(line):
            failures += 1
            raw_warnings.append(line.strip())
            if last_alpha is not None:
                failed_alphas.append(last_alpha)
                last_alpha = None

    return XfoilConvergenceInfo(
        n_convergence_failures=failures,
        n_points_computed=computed,
        failed_alpha_values=failed_alphas,
        raw_warnings=raw_warnings,
    )
