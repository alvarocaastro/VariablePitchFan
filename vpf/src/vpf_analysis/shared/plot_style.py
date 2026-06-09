"""
Shared matplotlib style and colour constants for all pipeline stages.

Apply with:
    from vpf_analysis.shared.plot_style import apply_style, COLORS, SECTION_COLORS

    with apply_style():
        fig, ax = plt.subplots(...)
        ...
"""

from __future__ import annotations

import contextlib
from collections.abc import Generator

import matplotlib as mpl

mpl.use("Agg", force=True)

# ── Colour palette (Paul Tol's colorblind-safe "bright") ─────────────────────
COLORS = {
    "takeoff":  "#EE6677",   # rose
    "climb":    "#CCBB44",   # yellow-olive
    "cruise":   "#4477AA",   # blue
    "descent":  "#228833",   # green
    "root":     "#4477AA",   # blue
    "mid_span": "#EE6677",   # rose
    "tip":      "#228833",   # green
    "neutral":  "#BBBBBB",
}

FLIGHT_LABELS = {
    "takeoff": "Takeoff",
    "climb":   "Climb",
    "cruise":  "Cruise",
    "descent": "Descent",
}

SECTION_LABELS = {
    "root":     "Root",
    "mid_span": "Mid-span",
    "tip":      "Tip",
}

_RC = {
    # Font
    "font.family":        "sans-serif",
    "font.size":          10,
    "axes.titlesize":     11,
    "axes.titleweight":   "bold",
    "axes.labelsize":     10,
    "xtick.labelsize":    9,
    "ytick.labelsize":    9,
    "legend.fontsize":    9,
    "legend.title_fontsize": 9,

    # Lines & markers
    "lines.linewidth":    2.0,
    "lines.markersize":   7,
    "patch.linewidth":    0.8,

    # Axes
    "axes.spines.top":    False,
    "axes.spines.right":  False,
    "axes.linewidth":     0.8,
    "axes.grid":          True,
    "grid.linestyle":     ":",
    "grid.linewidth":     0.6,
    "grid.alpha":         0.6,
    "axes.facecolor":     "white",
    "figure.facecolor":   "white",

    # Legend
    "legend.framealpha":  0.9,
    "legend.edgecolor":   "#CCCCCC",
    "legend.frameon":     True,

    # Save
    "savefig.dpi":        300,
    "savefig.bbox":       "tight",
    "savefig.facecolor":  "white",
}


@contextlib.contextmanager
def apply_style() -> Generator[None, None, None]:
    """Context manager that temporarily applies the publication style."""
    with mpl.rc_context(_RC):
        yield


# ── Per-section colour aliases ────────────────────────────────────────────────
# Imported by stages that need to colour-code blade sections consistently.
SECTION_COLORS: dict[str, str] = {
    "root":     COLORS["root"],
    "mid_span": COLORS["mid_span"],
    "tip":      COLORS["tip"],
}
