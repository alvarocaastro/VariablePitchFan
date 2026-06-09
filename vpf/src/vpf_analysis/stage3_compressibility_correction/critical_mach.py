"""Critical Mach number estimation for subsonic airfoils.

References
----------
Korn, D.A. (1975). Numerical design of transonic cascades. NYU-CIMS Report.
    Korn's equation: Mdd = κ - t/c - CL/10.  κ = 0.87 for NACA 6-series
    conventional airfoils; κ ≈ 0.95 for supercritical sections.

Lock, R.C. (1955). The velocity distribution on the upper surface of a symmetrical
    aerofoil. ARC R&M 2952.
    Lock's 4th-power law: ΔCD_wave = K × (M - Mdd)^4.
    K = 20.0 is the standard empirical value for conventional NACA 6-series
    sections (validated for M - Mdd < 0.10). For modern supercritical airfoils
    K ≈ 10–15; for thicker sections K can reach 25.
    Cap of 0.025 (250 drag counts) prevents unphysical extrapolation far
    above Mdd where the 2-D subsonic model breaks down.
"""

from __future__ import annotations

import logging

LOGGER = logging.getLogger(__name__)

_LOCK_COEFFICIENT: float = 20.0
"""Lock's 4th-power law coefficient for NACA 6-series conventional airfoils.
Valid range: M - Mdd < 0.10. Larger exceedances should use SBLi-capable methods.
"""

_WAVE_DRAG_CAP: float = 0.025
"""Maximum wave drag increment (250 drag counts). Prevents physically unrealistic
values when operating well above Mdd, where the 2-D inviscid model is invalid.
"""

_LOCK_VALID_MARGIN: float = 0.10
"""Maximum M − Mdd for which Lock's law is empirically validated."""

_LOCK_WARNED: bool = False
"""Rate-limit Lock's-law warnings: emit only once per process lifetime."""


def estimate_mdd(cl_operating: float, thickness_ratio: float, korn_kappa: float) -> float:
    """Drag-divergence Mach via Korn's equation: Mdd = κ - t/c - CL/10.

    Negative CL is handled correctly — a negative operating lift coefficient
    increases Mdd (blade operates closer to its uncambered shape).
    """
    mdd = korn_kappa - thickness_ratio - cl_operating / 10.0
    return max(0.50, min(mdd, 0.99))


def estimate_mcr(
    cl_operating: float,
    thickness_ratio: float = 0.10,
    korn_kappa: float = 0.87,
) -> float:
    """Critical Mach derived from Mdd (Mcr ≈ Mdd − 0.02).

    Using Korn's equation instead of a hardcoded Küchemann value makes Mcr
    consistent with the wave-drag model and valid for any airfoil family.
    """
    mdd = estimate_mdd(cl_operating, thickness_ratio, korn_kappa)
    return max(0.50, min(mdd - 0.02, 0.99))


def wave_drag_increment(mach: float, mdd: float) -> float:
    """Wave drag increment via Lock's 4th-power law.

        ΔCDw = K × (M − Mdd)^4   if M > Mdd, else 0

    where K = 20.0 (Lock 1955, NACA 6-series). Capped at 250 drag counts.

    Emits a WARNING when M − Mdd > 0.10 (beyond Lock's validated range).
    The cap of 0.025 still limits the value physically, but the result is
    a saturated estimate rather than a physical prediction — the true wave
    drag in this regime requires shock-capturing CFD.
    """
    if mach <= mdd:
        return 0.0
    delta_m = mach - mdd
    cd_wave = min(_LOCK_COEFFICIENT * delta_m ** 4, _WAVE_DRAG_CAP)
    if delta_m > _LOCK_VALID_MARGIN:
        global _LOCK_WARNED
        if not _LOCK_WARNED:
            _LOCK_WARNED = True
            LOGGER.warning(
                "Lock's law operating outside validated range (M−Mdd up to %.2f > %.2f). "
                "Wave drag in transonic tip sections is a saturated cap estimate; "
                "use shock-capturing CFD (RANS) for accurate transonic wave drag.",
                delta_m, _LOCK_VALID_MARGIN,
            )
    return cd_wave
