"""
run_sfc_analysis.py
-------------------
Stage 7 orchestrator: Specific Fuel Consumption (SFC) Analysis.

Reads aerodynamic performance data from Stage 4 and estimates the SFC reduction
enabled by the variable pitch fan, comparing VPF (α_opt) vs fixed pitch (α_design).

Inputs:
    results/stage4_performance_metrics/tables/summary_table.csv
    config/engine_parameters.yaml

Outputs (in results/stage7_sfc_analysis/):
    tables/sfc_section_breakdown.csv     — ε, Δη per condition × section
    tables/sfc_analysis.csv              — aggregated results per condition
    tables/sfc_sensitivity.csv           — τ sweep × condition
    tables/mission_fuel_burn.csv         — fuel saving per mission phase
    figures/sfc_improvement_by_condition.png — CL/CD_fixed vs CL/CD_vpf per section
    figures/fuel_saving_vs_clcd.png          — fuel saving vs CL/CD (GE9X parametric)
    sfc_analysis_summary.txt
    finalresults_stage6.txt
"""

from __future__ import annotations

import logging
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import yaml

from vpf_analysis import settings as base_config
from vpf_analysis.shared.plot_style import (
    FLIGHT_LABELS,
    SECTION_LABELS,
    apply_style,
)
from vpf_analysis.stage7_sfc_analysis.core.domain.sfc_parameters import (
    EngineBaseline,
    MissionFuelBurnResult,
    MissionSummary,
    SfcAnalysisResult,
    SfcSectionResult,
    SfcSensitivityPoint,
)
from vpf_analysis.stage7_sfc_analysis.sfc_core import (
    _SEAL_LEAKAGE_PENALTY,
    compute_bypass_sensitivity_factor,
    compute_mission_fuel_burn,
    compute_sfc_analysis,
    compute_sfc_improvement,
    compute_sfc_reduction_percent,
    compute_sfc_sensitivity,
    generate_sfc_summary,
)
from vpf_analysis.stage7_sfc_analysis.engine.ge9x_analysis import run_ge9x_analysis

LOGGER = logging.getLogger(__name__)

_COLOR_BASELINE = "#4393C3"
_COLOR_VPF      = "#4DAC26"

_CONDITIONS_ORDER = ["takeoff", "climb", "cruise", "descent"]
_SECTIONS_ORDER   = ["root", "mid_span", "tip"]


# ---------------------------------------------------------------------------
# Figures
# ---------------------------------------------------------------------------

def generate_sfc_figures(
    sfc_results: list[SfcAnalysisResult],
    section_results: list[SfcSectionResult],
    sensitivity_results: list[SfcSensitivityPoint],
    figures_dir: Path,
    mission_phase_results: list[MissionFuelBurnResult] | None = None,
    mission_summary: MissionSummary | None = None,
) -> None:
    """Generate the essential Stage 7 figures."""
    figures_dir.mkdir(parents=True, exist_ok=True)
    with apply_style():
        _plot_fixed_vs_vpf_efficiency(section_results, figures_dir)
        _plot_efficiency_gain_map(sfc_results, figures_dir)
        if mission_phase_results:
            _plot_mission_fuel_burn_bars(mission_phase_results, figures_dir)


def _plot_fixed_vs_vpf_efficiency(
    section_results: list[SfcSectionResult],
    figures_dir: Path,
) -> None:
    """2×2 subplots: CL/CD fixed pitch vs VPF per section, for each condition.

    Saved as ``sfc_improvement_by_condition.png``.
    """
    fig, axes = plt.subplots(2, 2, figsize=(11, 8), sharey=False)
    conditions = [c for c in _CONDITIONS_ORDER]

    for ax, cond in zip(axes.flat, conditions):
        subset = [r for r in section_results if r.condition == cond]
        x = np.arange(len(_SECTIONS_ORDER))
        fixed = [next((r.cl_cd_fixed for r in subset if r.blade_section == s), 0.0)
                 for s in _SECTIONS_ORDER]
        vpf   = [next((r.cl_cd_vpf   for r in subset if r.blade_section == s), 0.0)
                 for s in _SECTIONS_ORDER]

        bars_f = ax.bar(x - 0.20, fixed, 0.35, label=r"Fixed pitch ($\alpha_{design}$)",
                        color=_COLOR_BASELINE, edgecolor="white", linewidth=0.5, zorder=3)
        bars_v = ax.bar(x + 0.20, vpf,   0.35, label=r"VPF ($\alpha_{opt}$)",
                        color=_COLOR_VPF,      edgecolor="white", linewidth=0.5, zorder=3)
        ax.bar_label(bars_f, fmt="%.0f", padding=2, fontsize=7)
        ax.bar_label(bars_v, fmt="%.0f", padding=2, fontsize=7)
        ax.set_xticks(x)
        ax.set_xticklabels([SECTION_LABELS[s] for s in _SECTIONS_ORDER])
        ax.set_title(FLIGHT_LABELS.get(cond, cond), fontsize=10, fontweight="bold")
        ax.set_ylabel(r"$C_L/C_D$", fontsize=8)
        ax.legend(fontsize=7, bbox_to_anchor=(1.02, 1), loc="upper left", borderaxespad=0)
        ax.grid(axis="y", alpha=0.3)

    fig.suptitle(
        "Profile efficiency: fixed pitch vs VPF per blade section",
        fontsize=11, fontweight="bold", y=1.01,
    )
    fig.tight_layout()
    fig.savefig(figures_dir / "sfc_improvement_by_condition.png", bbox_inches="tight")
    plt.close(fig)


def _plot_efficiency_gain_map(
    sfc_results: list[SfcAnalysisResult],
    figures_dir: Path,
) -> None:
    """Grouped bars: BPR10+Fixed vs BPR10+VPF vs BPR15+VPF for each flight phase.

    BPR10+VPF gain is back-computed from BPR15+VPF by the bypass sensitivity ratio
    k_BPR10/k_BPR15 so that only one pipeline run is needed.
    Saved as ``efficiency_gain_map.png``.
    """
    k_bpr10 = compute_bypass_sensitivity_factor(10.0)
    k_bpr15 = compute_bypass_sensitivity_factor(15.0)

    flight_conditions = [c for c in _CONDITIONS_ORDER if any(r.condition == c for r in sfc_results)]
    labels = [FLIGHT_LABELS.get(c, c.capitalize()) for c in flight_conditions]

    gain_vpf_bpr10: list[float] = []
    gain_vpf_bpr15: list[float] = []
    for cond in flight_conditions:
        res = next((r for r in sfc_results if r.condition == cond), None)
        if res is None:
            gain_vpf_bpr10.append(0.0)
            gain_vpf_bpr15.append(0.0)
        else:
            g15 = res.sfc_reduction_percent
            g10 = g15 * (k_bpr10 / k_bpr15)
            gain_vpf_bpr10.append(g10)
            gain_vpf_bpr15.append(g15)

    x = np.arange(len(flight_conditions))
    w = 0.25

    fig, ax = plt.subplots(figsize=(8.0, 5.0))
    bars_ref = ax.bar(x - w, [0.0] * len(flight_conditions), w,
                      label="BPR 10 + Fixed pitch (reference)",
                      color="#BBBBBB", edgecolor="white", linewidth=0.5, zorder=3)
    bars_b10 = ax.bar(x, gain_vpf_bpr10, w,
                      label="BPR 10 + VPF",
                      color="#4477AA", edgecolor="white", linewidth=0.5, zorder=3)
    bars_b15 = ax.bar(x + w, gain_vpf_bpr15, w,
                      label="BPR 15 + VPF (UHBPR)",
                      color="#228833", edgecolor="white", linewidth=0.5, zorder=3)

    # Reference bars are always 0 % — label them so the baseline is visible
    ax.bar_label(bars_ref, fmt="%.2f%%", padding=3, fontsize=7)
    # Non-reference bars: only label when the gain is non-trivial to avoid
    # overlapping "0.00%0.00%" labels at cruise (the reference condition)
    for bars, values in [(bars_b10, gain_vpf_bpr10), (bars_b15, gain_vpf_bpr15)]:
        for bar, val in zip(bars, values):
            if abs(val) > 0.005:
                ax.annotate(
                    f"{val:.2f}%",
                    xy=(bar.get_x() + bar.get_width() / 2, bar.get_height()),
                    xytext=(0, 3), textcoords="offset points",
                    ha="center", va="bottom", fontsize=7,
                )
    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.set_ylabel("SFC reduction vs BPR 10 Fixed pitch [%]")
    ax.set_title("VPF efficiency gain map: BPR scaling and variable-pitch fan benefit")
    ax.legend(bbox_to_anchor=(1.02, 1), loc="upper left", borderaxespad=0)
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(figures_dir / "efficiency_gain_map.png", bbox_inches="tight")
    plt.close(fig)


def _plot_mission_fuel_burn_bars(
    phase_results: list[MissionFuelBurnResult],
    figures_dir: Path,
) -> None:
    """10-bar grouped chart: fuel burned per phase × {baseline, VPF}.

    Five phase-pairs: (takeoff, climb, cruise, descent, hold).
    Left bar of each pair = fixed-pitch baseline; right bar = VPF.
    Annotations show the absolute saving and percentage for each pair.

    Saved as ``mission_fuel_burn_bars.png``.
    """
    _PHASE_ORDER  = ["takeoff", "climb", "cruise", "descent", "hold"]
    _PHASE_LABELS = {
        "takeoff": "Takeoff\n(TOGA)",
        "climb":   "Climb",
        "cruise":  "Cruise",
        "descent": "Descent\n(idle)",
        "hold":    "Hold",
    }

    indexed = {r.phase: r for r in phase_results}
    phases    = [p for p in _PHASE_ORDER if p in indexed]
    baselines = [indexed[p].fuel_baseline_kg for p in phases]
    vpfs      = [indexed[p].fuel_vpf_kg      for p in phases]
    savings   = [indexed[p].fuel_saving_kg   for p in phases]
    labels    = [_PHASE_LABELS.get(p, p.capitalize()) for p in phases]

    x = np.arange(len(phases))
    w = 0.35

    fig, ax = plt.subplots(figsize=(11.0, 6.0))

    bars_b = ax.bar(
        x - w / 2, baselines, w,
        label=r"Fixed pitch ($\alpha_{design}$)",
        color=_COLOR_BASELINE, edgecolor="white", linewidth=0.5, zorder=3,
    )
    bars_v = ax.bar(
        x + w / 2, vpfs, w,
        label=r"VPF ($\alpha_{opt}$)",
        color=_COLOR_VPF, edgecolor="white", linewidth=0.5, zorder=3,
    )

    ax.bar_label(
        bars_b,
        labels=[f"{v:,.0f} kg" for v in baselines],
        padding=4, fontsize=7, color="#333333",
    )
    ax.bar_label(
        bars_v,
        labels=[f"{v:,.0f} kg" for v in vpfs],
        padding=4, fontsize=7, color="#333333",
    )

    # Saving bracket between the pair tops
    for xi, (b, v, s) in enumerate(zip(baselines, vpfs, savings)):
        if abs(s) < 0.1:
            continue
        pct = s / b * 100
        top = max(b, v) * 1.02
        ax.annotate(
            f"−{s:,.0f} kg\n(−{pct:.1f} %)",
            xy=(xi, top),
            xytext=(0, 28), textcoords="offset points",
            ha="center", va="bottom", fontsize=7,
            color="#CC3311", fontweight="bold",
            arrowprops=dict(arrowstyle="-", color="#CC3311", lw=0.8),
        )

    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=9)
    ax.set_ylabel("Fuel burned per mission [kg]")
    ax.set_title("Mission fuel consumption per phase: fixed pitch vs VPF")
    ax.legend(bbox_to_anchor=(1.02, 1), loc="upper left", borderaxespad=0)
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(figures_dir / "mission_fuel_burn_bars.png", bbox_inches="tight")
    plt.close(fig)


# ---------------------------------------------------------------------------
# I/O helpers
# ---------------------------------------------------------------------------

def _write_section_table(
    section_results: list[SfcSectionResult],
    output_path: Path,
) -> None:
    rows = [
        {
            "condition":           r.condition,
            "blade_section":       r.blade_section,
            "CL_CD_fixed":         r.cl_cd_fixed,
            "CL_CD_vpf":           r.cl_cd_vpf,
            "epsilon":             r.epsilon,
            "epsilon_eff":         r.epsilon_eff,
            "delta_eta_profile":   r.delta_eta_profile,
            "efficiency_gain_pct": r.efficiency_gain_pct,
            "delta_alpha_deg":     r.delta_alpha_deg,
        }
        for r in section_results
    ]
    df = pd.DataFrame(rows).sort_values(["condition", "blade_section"])
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False, float_format="%.6f")


def _write_sfc_table(
    sfc_results: list[SfcAnalysisResult],
    output_path: Path,
) -> None:
    rows = [
        {
            "condition":                r.condition,
            "CL_CD_fixed_mean":         r.cl_cd_fixed,
            "CL_CD_vpf_mean":           r.cl_cd_vpf,
            "epsilon_mean":             r.epsilon_mean,
            "delta_alpha_mean_deg":     r.delta_alpha_mean_deg,
            "k_sensitivity":            r.k_sensitivity,
            "delta_eta_fan":            r.delta_eta_fan,
            "fan_efficiency_baseline":  r.fan_efficiency_baseline,
            "fan_efficiency_new":       r.fan_efficiency_new,
            "SFC_baseline":             r.sfc_baseline,
            "SFC_new":                  r.sfc_new,
            "SFC_reduction_percent":    r.sfc_reduction_percent,
        }
        for r in sfc_results
    ]
    df = pd.DataFrame(rows).sort_values("condition")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False, float_format="%.6f")


def _write_sensitivity_table(
    sensitivity_results: list[SfcSensitivityPoint],
    output_path: Path,
) -> None:
    rows = [
        {
            "tau":               p.tau,
            "condition":         p.condition,
            "epsilon_mean":      p.epsilon_mean,
            "delta_eta_fan":     p.delta_eta_fan,
            "eta_fan_new":       p.eta_fan_new,
            "SFC_baseline":      p.sfc_baseline,
            "SFC_new":           p.sfc_new,
            "SFC_reduction_pct": p.sfc_reduction_pct,
        }
        for p in sensitivity_results
    ]
    df = pd.DataFrame(rows).sort_values(["tau", "condition"])
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False, float_format="%.6f")


def _write_economic_analysis(
    phase_results: list[MissionFuelBurnResult],
    tables_dir: Path,
    eco_cfg: dict,
    fleet_cfg: dict,
    reverser_cfg: dict | None = None,
) -> None:
    """Write economic analysis CSVs in EUR: Block 1 (VPF aero), Block 2 (reverser weight), combined."""
    _CO2_KG_PER_KG_FUEL = 3.16   # ICAO CORSIA (2022) §1.4.5

    fuel_usd_per_kg = eco_cfg.get("fuel_price_iata_usd_per_kg", 0.75)
    eur_usd         = eco_cfg.get("eur_usd_rate", 1.085)
    engines         = int(eco_cfg.get("engines_per_aircraft", 2))
    seats           = int(eco_cfg.get("seats_per_aircraft", 350))
    avg_fare        = float(eco_cfg.get("avg_fare_eur", 520.0))
    mtow_kg         = float(eco_cfg.get("aircraft_mtow_kg", 352400.0))
    fleet_size      = int(fleet_cfg.get("aircraft_count", 205))
    flights_per_day = int(fleet_cfg.get("flights_per_day_per_aircraft", 2))
    reverser_cfg    = reverser_cfg or {}

    eur_per_kg       = fuel_usd_per_kg / eur_usd
    flights_per_year = fleet_size * flights_per_day * 365

    # ── Block 1: VPF aerodynamic savings ─────────────────────────────────
    total_saving_ac = sum(p.fuel_saving_kg  for p in phase_results) * engines
    total_baseline  = sum(p.fuel_baseline_kg for p in phase_results) * engines
    total_vpf       = sum(p.fuel_vpf_kg      for p in phase_results) * engines
    total_co2_aero  = sum(p.co2_saving_kg    for p in phase_results) * engines

    aero_cost_eur        = total_saving_ac * eur_per_kg
    aero_cost_yr_eur     = aero_cost_eur * flights_per_year
    aero_per_seat        = aero_cost_eur / seats
    aero_pct_fare        = aero_per_seat / avg_fare * 100

    # ── Block 2: reverser weight savings via Breguet approximation ───────
    # Net weight saved = (cascade TRU eliminated) - (VPF pitch mechanism added), per engine
    engine_dry_wt  = float(reverser_cfg.get("engine_dry_weight_kg", 8276.0))
    conv_frac      = float(reverser_cfg.get("conventional_reverser_fraction", 0.095))
    mech_frac      = float(reverser_cfg.get("mechanism_weight_fraction", 0.04))
    conv_wt_engine = engine_dry_wt * conv_frac     # cascade TRU weight per engine
    mech_wt_engine = engine_dry_wt * mech_frac     # VPF mechanism weight per engine
    net_wt_engine  = conv_wt_engine - mech_wt_engine
    net_wt_ac      = net_wt_engine * engines       # total aircraft structural weight saving

    # Breguet first-order approximation: Δfuel/fuel ≈ ΔW / W_avg
    # W_avg = arithmetic mean of take-off weight (MTOW) and landing weight (MTOW - fuel)
    w_final  = mtow_kg - total_baseline            # landing weight (approx, no reserves)
    w_avg    = (mtow_kg + w_final) / 2.0
    fuel_saving_wt_kg  = total_baseline * (net_wt_ac / w_avg)
    co2_saving_wt_kg   = fuel_saving_wt_kg * _CO2_KG_PER_KG_FUEL
    wt_cost_eur        = fuel_saving_wt_kg * eur_per_kg
    wt_cost_yr_eur     = wt_cost_eur * flights_per_year
    wt_per_seat        = wt_cost_eur / seats
    wt_pct_fare        = wt_per_seat / avg_fare * 100

    # ── Combined ─────────────────────────────────────────────────────────
    combined_cost_eur    = aero_cost_eur + wt_cost_eur
    combined_cost_yr_eur = combined_cost_eur * flights_per_year
    combined_per_seat    = combined_cost_eur / seats
    combined_pct_fare    = combined_per_seat / avg_fare * 100
    combined_fuel_kg     = total_saving_ac + fuel_saving_wt_kg
    combined_co2_kg      = total_co2_aero + co2_saving_wt_kg

    def _fmt(rows: list[dict]) -> pd.DataFrame:
        df = pd.DataFrame(rows)
        df["value"] = df["value"].apply(lambda v: f"{v:,.3f}" if isinstance(v, float) else str(v))
        return df

    # ── Table 1: per-flight VPF aerodynamic phase breakdown ──────────────
    rows_flight = []
    for p in phase_results:
        saving_ac   = p.fuel_saving_kg * engines
        baseline_ac = p.fuel_baseline_kg * engines
        vpf_ac      = p.fuel_vpf_kg * engines
        rows_flight.append({
            "phase":                     p.phase,
            "fuel_saving_kg_per_engine": round(p.fuel_saving_kg, 2),
            "fuel_saving_kg_aircraft":   round(saving_ac, 2),
            "fuel_cost_saving_eur":      round(saving_ac * eur_per_kg, 2),
            "fuel_cost_baseline_eur":    round(baseline_ac * eur_per_kg, 2),
            "fuel_cost_vpf_eur":         round(vpf_ac * eur_per_kg, 2),
            "co2_saving_kg_aircraft":    round(p.co2_saving_kg * engines, 2),
        })
    rows_flight.append({
        "phase":                     "VPF_AERO_TOTAL",
        "fuel_saving_kg_per_engine": round(total_saving_ac / engines, 2),
        "fuel_saving_kg_aircraft":   round(total_saving_ac, 2),
        "fuel_cost_saving_eur":      round(aero_cost_eur, 2),
        "fuel_cost_baseline_eur":    round(total_baseline * eur_per_kg, 2),
        "fuel_cost_vpf_eur":         round(total_vpf * eur_per_kg, 2),
        "co2_saving_kg_aircraft":    round(total_co2_aero, 2),
    })
    rows_flight.append({
        "phase":                     "REVERSER_WEIGHT",
        "fuel_saving_kg_per_engine": round(fuel_saving_wt_kg / engines, 2),
        "fuel_saving_kg_aircraft":   round(fuel_saving_wt_kg, 2),
        "fuel_cost_saving_eur":      round(wt_cost_eur, 2),
        "fuel_cost_baseline_eur":    "",
        "fuel_cost_vpf_eur":         "",
        "co2_saving_kg_aircraft":    round(co2_saving_wt_kg, 2),
    })
    rows_flight.append({
        "phase":                     "COMBINED_TOTAL",
        "fuel_saving_kg_per_engine": round(combined_fuel_kg / engines, 2),
        "fuel_saving_kg_aircraft":   round(combined_fuel_kg, 2),
        "fuel_cost_saving_eur":      round(combined_cost_eur, 2),
        "fuel_cost_baseline_eur":    "",
        "fuel_cost_vpf_eur":         "",
        "co2_saving_kg_aircraft":    round(combined_co2_kg, 2),
    })
    pd.DataFrame(rows_flight).to_csv(tables_dir / "economic_per_flight_eur.csv", index=False)

    # ── Table 2: fleet annual — two blocks + combined ─────────────────────
    def _r(block: str, metric: str, value, unit: str, notes: str = "") -> dict:
        return {"block": block, "metric": metric, "value": value, "unit": unit, "notes": notes}

    ets_eur_per_tonne = float(eco_cfg.get("eu_ets_carbon_price_eur_per_tonne", 65.0))
    co2_aero_t_yr    = total_co2_aero * flights_per_year / 1000
    co2_wt_t_yr      = co2_saving_wt_kg * flights_per_year / 1000
    co2_comb_t_yr    = combined_co2_kg  * flights_per_year / 1000
    ets_aero_yr      = co2_aero_t_yr  * ets_eur_per_tonne
    ets_wt_yr        = co2_wt_t_yr    * ets_eur_per_tonne
    ets_comb_yr      = co2_comb_t_yr  * ets_eur_per_tonne
    total_value_yr   = combined_cost_yr_eur + ets_comb_yr

    rows_fleet = [
        # assumptions
        _r("assumptions", "fuel_price_iata_usd_per_kg",        round(fuel_usd_per_kg, 3),  "USD/kg",    "IATA spot May 2026"),
        _r("assumptions", "eur_usd_rate",                       round(eur_usd, 3),           "-",         "ECB ref May 2026"),
        _r("assumptions", "fuel_price_eur_per_kg",              round(eur_per_kg, 4),        "EUR/kg",    "= USD / rate"),
        _r("assumptions", "fleet_size",                         fleet_size,                  "aircraft",  "Emirates firm order FY2024-25"),
        _r("assumptions", "flights_per_day_per_aircraft",       flights_per_day,             "fl/day",    "Emirates 777 utilisation ~12.8 bh/day"),
        _r("assumptions", "flights_per_year_fleet",             flights_per_year,            "fl/yr",     f"{fleet_size} x {flights_per_day} x 365"),
        _r("assumptions", "eu_ets_carbon_price_eur_per_tonne",  round(ets_eur_per_tonne, 0), "EUR/tCO2",  "ICAP 2024 average"),
        # block 1: VPF aerodynamic
        _r("vpf_aerodynamic", "fuel_saving_per_flight_kg",       round(total_saving_ac, 1),                    "kg/fl",    "Both engines, tau=0.08"),
        _r("vpf_aerodynamic", "fuel_cost_saving_per_flight_eur", round(aero_cost_eur, 1),                      "EUR/fl",   ""),
        _r("vpf_aerodynamic", "fuel_saving_per_year_tonnes",     round(total_saving_ac * flights_per_year / 1000, 1), "t/yr", ""),
        _r("vpf_aerodynamic", "fuel_cost_saving_per_year_meur",  round(aero_cost_yr_eur / 1e6, 2),             "M EUR/yr", ""),
        _r("vpf_aerodynamic", "co2_saving_per_year_tonnes",      round(co2_aero_t_yr, 0),                      "t/yr",     "3.16 kg CO2/kg fuel (ICAO CORSIA)"),
        _r("vpf_aerodynamic", "eu_ets_credit_per_year_meur",     round(ets_aero_yr / 1e6, 2),                  "M EUR/yr", f"{ets_eur_per_tonne:.0f} EUR/tCO2 x co2_saving"),
        # block 2: reverser weight — explicit gross / net breakdown
        _r("reverser_weight", "conv_reverser_per_engine_kg",     round(conv_wt_engine, 1),                     "kg/engine","cascade TRU eliminated (8276 x 0.095); note Stage 6 +0.225% SFC cruise is separate mechanism-only penalty"),
        _r("reverser_weight", "vpf_mechanism_per_engine_kg",     round(mech_wt_engine, 1),                     "kg/engine","pitch mechanism added (8276 x 0.04)"),
        _r("reverser_weight", "net_weight_saving_per_engine_kg", round(net_wt_engine, 1),                      "kg/engine","= conv - mech"),
        _r("reverser_weight", "net_weight_saving_aircraft_kg",   round(net_wt_ac, 1),                          "kg",        f"net/engine x {engines} engines"),
        _r("reverser_weight", "breguet_w_avg_kg",                round(w_avg, 0),                               "kg",        "(MTOW + W_landing) / 2"),
        _r("reverser_weight", "fuel_saving_per_flight_kg",       round(fuel_saving_wt_kg, 1),                  "kg/fl",    "total_fuel x net_wt/W_avg"),
        _r("reverser_weight", "fuel_cost_saving_per_flight_eur", round(wt_cost_eur, 1),                        "EUR/fl",   ""),
        _r("reverser_weight", "fuel_saving_per_year_tonnes",     round(fuel_saving_wt_kg * flights_per_year / 1000, 1), "t/yr", ""),
        _r("reverser_weight", "fuel_cost_saving_per_year_meur",  round(wt_cost_yr_eur / 1e6, 2),               "M EUR/yr", ""),
        _r("reverser_weight", "co2_saving_per_year_tonnes",      round(co2_wt_t_yr, 0),                        "t/yr",     ""),
        _r("reverser_weight", "eu_ets_credit_per_year_meur",     round(ets_wt_yr / 1e6, 2),                    "M EUR/yr", f"{ets_eur_per_tonne:.0f} EUR/tCO2 x co2_saving"),
        # combined — fuel + ETS total value
        _r("combined", "fuel_saving_per_flight_kg",              round(combined_fuel_kg, 1),                   "kg/fl",    "Block 1 + Block 2"),
        _r("combined", "fuel_cost_saving_per_flight_eur",        round(combined_cost_eur, 1),                  "EUR/fl",   "Block 1 + Block 2"),
        _r("combined", "fuel_saving_per_year_tonnes",            round(combined_fuel_kg * flights_per_year / 1000, 1), "t/yr", ""),
        _r("combined", "fuel_cost_saving_per_year_meur",         round(combined_cost_yr_eur / 1e6, 2),         "M EUR/yr", "Block 1 + Block 2"),
        _r("combined", "co2_saving_per_year_tonnes",             round(co2_comb_t_yr, 0),                      "t/yr",     ""),
        _r("combined", "eu_ets_credit_per_year_meur",            round(ets_comb_yr / 1e6, 2),                  "M EUR/yr", f"{ets_eur_per_tonne:.0f} EUR/tCO2 x co2_saving"),
        _r("combined", "total_economic_value_per_year_meur",     round(total_value_yr / 1e6, 2),               "M EUR/yr", "fuel saving + EU ETS credits"),
    ]
    pd.DataFrame(rows_fleet).to_csv(tables_dir / "economic_fleet_annual_eur.csv", index=False)

    # ── Table 3: per-seat — two blocks + combined ─────────────────────────
    fuel_baseline_per_seat = (total_baseline * eur_per_kg) / seats
    rows_seat = [
        # context
        _r("context", "seats_per_aircraft", seats,    "seats",    "Emirates 777-9 est. 4-class (Boeing 3-class spec: 349)"),
        _r("context", "avg_fare_eur",        avg_fare, "EUR/seat", "Emirates FY2024-25 avg revenue/pax (AED 2080 x 0.25)"),
        _r("context", "fuel_cost_per_seat_baseline_eur", round(fuel_baseline_per_seat, 2), "EUR/seat", "Full mission, both engines"),
        # block 1: VPF aerodynamic
        _r("vpf_aerodynamic", "fuel_saving_per_seat_per_flight_eur", round(aero_per_seat, 3),      "EUR/seat", ""),
        _r("vpf_aerodynamic", "fuel_saving_pct_of_fare",             round(aero_pct_fare, 3),      "%",        ""),
        _r("vpf_aerodynamic", "equivalent_free_seats_per_flight",    round(aero_cost_eur / avg_fare, 3), "seats", "fuel_saving_eur / avg_fare"),
        _r("vpf_aerodynamic", "equivalent_free_seats_per_year",      round(aero_cost_eur / avg_fare * flights_per_year, 0), "seats/yr", f"{fleet_size} ac x {flights_per_day} fl/day"),
        _r("vpf_aerodynamic", "equivalent_revenue_per_year_meur",    round(aero_cost_yr_eur / 1e6, 3), "M EUR/yr", "= cost saving (fuel saving monetised at avg fare)"),
        # block 2: reverser weight
        _r("reverser_weight", "fuel_saving_per_seat_per_flight_eur", round(wt_per_seat, 3),        "EUR/seat", "Breguet approx"),
        _r("reverser_weight", "fuel_saving_pct_of_fare",             round(wt_pct_fare, 3),        "%",        ""),
        _r("reverser_weight", "equivalent_free_seats_per_flight",    round(wt_cost_eur / avg_fare, 3), "seats", ""),
        _r("reverser_weight", "equivalent_free_seats_per_year",      round(wt_cost_eur / avg_fare * flights_per_year, 0), "seats/yr", ""),
        _r("reverser_weight", "equivalent_revenue_per_year_meur",    round(wt_cost_yr_eur / 1e6, 3), "M EUR/yr", ""),
        # combined — fuel + ETS
        _r("combined", "fuel_saving_per_seat_per_flight_eur", round(combined_per_seat, 3),           "EUR/seat", "Block 1 + Block 2"),
        _r("combined", "fuel_saving_pct_of_fare",             round(combined_pct_fare, 3),           "%",        ""),
        _r("combined", "equivalent_free_seats_per_flight",    round(combined_cost_eur / avg_fare, 3), "seats",   ""),
        _r("combined", "equivalent_free_seats_per_year",      round(combined_cost_eur / avg_fare * flights_per_year, 0), "seats/yr", ""),
        _r("combined", "equivalent_revenue_per_year_meur",    round(combined_cost_yr_eur / 1e6, 3), "M EUR/yr", "fuel saving only"),
        _r("combined", "eu_ets_credit_per_year_meur",         round(ets_comb_yr / 1e6, 3),          "M EUR/yr", f"{ets_eur_per_tonne:.0f} EUR/tCO2"),
        _r("combined", "total_economic_value_per_year_meur",  round(total_value_yr / 1e6, 3),       "M EUR/yr", "fuel saving + EU ETS"),
    ]
    pd.DataFrame(rows_seat).to_csv(tables_dir / "economic_seat_analysis_eur.csv", index=False)


def _write_mission_table(
    phase_results: list[MissionFuelBurnResult],
    output_path: Path,
) -> None:
    rows = [
        {
            "phase":              p.phase,
            "duration_min":       p.duration_min,
            "thrust_kN":          p.thrust_kN,
            "sfc_baseline":       p.sfc_baseline,
            "sfc_vpf":            p.sfc_vpf,
            "fuel_baseline_kg":   p.fuel_baseline_kg,
            "fuel_vpf_kg":        p.fuel_vpf_kg,
            "fuel_saving_kg":     p.fuel_saving_kg,
            "co2_saving_kg":      p.co2_saving_kg,
            "cost_saving_usd":    p.cost_saving_usd,
        }
        for p in phase_results
    ]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(output_path, index=False, float_format="%.4f")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def run_sfc_analysis() -> None:
    """Ejecuta el Stage 7 completo: análisis de SFC."""
    LOGGER.info("=" * 70)
    LOGGER.info("STAGE 7: Specific Fuel Consumption (SFC) Impact Analysis")
    LOGGER.info("=" * 70)

    stage7_dir  = base_config.get_stage_dir(7)
    stage7_dir.mkdir(parents=True, exist_ok=True)
    tables_dir  = stage7_dir / "tables"
    figures_dir = stage7_dir / "figures"
    tables_dir.mkdir(parents=True, exist_ok=True)
    figures_dir.mkdir(parents=True, exist_ok=True)

    # ── 1. Cargar métricas de Stage 4 (fuente primaria) ──────────────────
    stage4_tables = base_config.get_stage_dir(4) / "tables"
    metrics_path  = stage4_tables / "summary_table.csv"
    if not metrics_path.exists():
        LOGGER.error(
            "summary_table.csv no encontrado en %s — Stage 4 debe ejecutarse primero.",
            stage4_tables,
        )
        return
    metrics_df = pd.read_csv(metrics_path)
    LOGGER.info("Métricas de Stage 4 cargadas: %d filas", len(metrics_df))

    required_cols = {"flight_condition", "blade_section", "max_efficiency", "eff_at_design_alpha"}
    missing = required_cols - set(metrics_df.columns)
    if missing:
        LOGGER.error("Missing columns in summary_table.csv: %s", missing)
        return

    n_cruise_valid = (metrics_df["flight_condition"] == "cruise").sum()
    LOGGER.info("Reference condition 'cruise': %d sections", n_cruise_valid)

    # ── 2. Cargar parámetros base del motor ─────────────────────────────
    engine_config_path = base_config.ROOT_DIR / "config" / "engine_parameters.yaml"
    with engine_config_path.open("r", encoding="utf-8") as f:
        _cfg = yaml.safe_load(f)
    engine_baseline = EngineBaseline(
        baseline_sfc=_cfg["baseline_sfc"],
        fan_efficiency=_cfg["fan_efficiency"],
        bypass_ratio=_cfg["bypass_ratio"],
    )
    LOGGER.info(
        "Motor: SFC_base=%.4f, η_fan=%.3f, BPR=%.1f",
        engine_baseline.baseline_sfc, engine_baseline.fan_efficiency, engine_baseline.bypass_ratio,
    )

    mw_path = base_config.get_stage_dir(6) / "tables" / "mechanism_weight.csv"
    if mw_path.exists():
        df_mw = pd.read_csv(mw_path)
        idx = df_mw.set_index("metric")["value"]
        LOGGER.info("VPF mechanism weight penalty: +%.3f%% SFC cruise", float(idx["sfc_cruise_penalty_pct"]))
        LOGGER.info("VPF vs conventional reverser: −%.3f%% SFC cruise", float(idx["sfc_benefit_vs_conventional_pct"]))

    # ── 3. Compute SFC improvements ────────────────────────────────────────
    stage5_dir = base_config.get_stage_dir(5)
    stage3_dir = base_config.get_stage_dir(3)
    sfc_results, section_results = compute_sfc_analysis(
        metrics_df, engine_baseline, engine_config_path,
        stage5_dir=stage5_dir,
        stage3_dir=stage3_dir,
    )
    LOGGER.info("SFC analysis: %d conditions, %d sections", len(sfc_results), len(section_results))

    # Synthesise "hold" SfcAnalysisResult from an N1-weighted blend of climb and
    # descent, so compute_mission_fuel_burn() finds an entry for the hold phase.
    # Hold at Mach 0.5, 20 000 ft operates at N1≈72%, intermediate between
    # climb (N1≈90%) and descent (N1≈60%).  Linear interpolation in N1-space:
    #   w_climb  = |60 − 72| / |60 − 90| = 0.40
    #   w_descent = |90 − 72| / |60 − 90| = 0.60
    # This gives hold an aerodynamic improvement and Δβ between the two phases,
    # reflecting that the fan is more off-design than at climb but less than at
    # idle descent.
    import dataclasses as _dc
    _W_HOLD_CLIMB   = 0.40
    _W_HOLD_DESCENT = 0.60
    hold_phase_cfg = _cfg.get("mission", {}).get("phases", {}).get("hold", {})
    if hold_phase_cfg and not any(r.condition == "hold" for r in sfc_results):
        _climb   = next((r for r in sfc_results if r.condition == "climb"),   None)
        _descent = next((r for r in sfc_results if r.condition == "descent"), None)
        _src = _climb or _descent
        if _src is not None:
            if _climb is not None and _descent is not None:
                _cl_cd_fixed  = _W_HOLD_CLIMB * _climb.cl_cd_fixed  + _W_HOLD_DESCENT * _descent.cl_cd_fixed
                _cl_cd_vpf    = _W_HOLD_CLIMB * _climb.cl_cd_vpf    + _W_HOLD_DESCENT * _descent.cl_cd_vpf
                _epsilon      = _cl_cd_vpf / _cl_cd_fixed if _cl_cd_fixed > 0 else 1.0
                _delta_alpha  = _W_HOLD_CLIMB * _climb.delta_alpha_mean_deg + _W_HOLD_DESCENT * _descent.delta_alpha_mean_deg
                _delta_eta    = _W_HOLD_CLIMB * _climb.delta_eta_fan        + _W_HOLD_DESCENT * _descent.delta_eta_fan
                _eta_new      = engine_baseline.fan_efficiency + _delta_eta
            else:
                _cl_cd_fixed = _src.cl_cd_fixed
                _cl_cd_vpf   = _src.cl_cd_vpf
                _epsilon     = _src.epsilon_mean
                _delta_alpha = _src.delta_alpha_mean_deg
                _delta_eta   = _src.delta_eta_fan
                _eta_new     = _src.fan_efficiency_new

            _hold_mult     = _cfg.get("sfc_multipliers", {}).get("hold", 1.08)
            _hold_sfc_base = engine_baseline.baseline_sfc * _hold_mult * (1.0 + _SEAL_LEAKAGE_PENALTY)
            _hold_sfc_new  = compute_sfc_improvement(
                sfc_baseline=_hold_sfc_base,
                delta_eta_fan=_delta_eta,
                eta_fan_baseline=engine_baseline.fan_efficiency,
                k=_src.k_sensitivity,
            )
            _hold_reduction = compute_sfc_reduction_percent(_hold_sfc_base, _hold_sfc_new)
            sfc_results.append(_dc.replace(
                _src,
                condition="hold",
                cl_cd_fixed=_cl_cd_fixed,
                cl_cd_vpf=_cl_cd_vpf,
                epsilon_mean=_epsilon,
                delta_alpha_mean_deg=_delta_alpha,
                delta_eta_fan=_delta_eta,
                fan_efficiency_new=_eta_new,
                sfc_baseline=_hold_sfc_base,
                sfc_new=_hold_sfc_new,
                sfc_reduction_percent=_hold_reduction,
            ))
            LOGGER.info(
                "Hold phase synthesised from climb/descent blend "
                "(w_c=%.0f%%, w_d=%.0f%%): SFC_base=%.4f, reduction=%.2f%%",
                _W_HOLD_CLIMB * 100, _W_HOLD_DESCENT * 100,
                _hold_sfc_base, _hold_reduction,
            )

    # ── 4. Sensitivity analysis to τ ─────────────────────────────────────
    sensitivity_results = compute_sfc_sensitivity(
        metrics_df, engine_baseline, config_path=engine_config_path,
    )
    LOGGER.info("Sensitivity: %d points (τ × condition)", len(sensitivity_results))

    # ── 5. Mission analysis ──────────────────────────────────────────────
    try:
        from vpf_analysis.config_loader import get_mission_profile
        mission_profile = get_mission_profile()
        mission_summary, mission_phase_results = compute_mission_fuel_burn(
            sfc_results, mission_profile,
        )
        LOGGER.info(
            "Mission: saving=%.1f kg (%.2f%%), CO2=%.1f kg, cost=$%.0f",
            mission_summary.total_fuel_saving_kg,
            mission_summary.total_fuel_saving_pct,
            mission_summary.total_co2_saving_kg,
            mission_summary.total_cost_saving_usd,
        )
    except Exception as exc:
        LOGGER.warning("Mission analysis not available: %s", exc)
        mission_summary = None
        mission_phase_results = []

    # ── Fleet CO₂ annualization ──────────────────────────────────────────
    if mission_summary is not None:
        try:
            from vpf_analysis.config_loader import get_fleet_co2_config
            fleet_cfg = get_fleet_co2_config()
            n_aircraft  = fleet_cfg.get("aircraft_count", 205)
            flights_day = fleet_cfg.get("flights_per_day_per_aircraft", 2)
            annual_co2_saving_t = (
                mission_summary.total_co2_saving_kg * n_aircraft * flights_day * 365 / 1000
            )
            LOGGER.info(
                "Ahorro CO₂ anualizado (flota %d aviones): %.0f t/año",
                n_aircraft, annual_co2_saving_t,
            )
        except Exception as exc:
            LOGGER.warning("Fleet CO2 calculation not available: %s", exc)

    # ── 6. Figures ───────────────────────────────────────────────────────
    generate_sfc_figures(
        sfc_results, section_results, sensitivity_results, figures_dir,
        mission_phase_results=mission_phase_results or None,
        mission_summary=mission_summary,
    )

    # ── 7. Tables ────────────────────────────────────────────────────────
    _write_section_table(section_results, tables_dir / "sfc_section_breakdown.csv")
    _write_sfc_table(sfc_results,         tables_dir / "sfc_analysis.csv")
    _write_sensitivity_table(sensitivity_results, tables_dir / "sfc_sensitivity.csv")
    if mission_phase_results:
        _write_mission_table(mission_phase_results, tables_dir / "mission_fuel_burn.csv")
        eco_cfg      = _cfg.get("economic_analysis", {})
        fleet_cfg    = _cfg.get("fleet_co2", {})
        reverser_cfg = _cfg.get("reverse_thrust", {})
        _write_economic_analysis(mission_phase_results, tables_dir, eco_cfg, fleet_cfg, reverser_cfg)

    # ── 8. Text summaries ────────────────────────────────────────────────
    summary_text = generate_sfc_summary(sfc_results, section_results, mission_summary=mission_summary)
    (stage7_dir / "sfc_analysis_summary.txt").write_text(summary_text, encoding="utf-8")

    from vpf_analysis.postprocessing.stage_summary_generator import (
        generate_stage7_summary,
        write_stage_summary,
    )
    stage7_summary = generate_stage7_summary(stage7_dir)
    write_stage_summary(7, stage7_summary, stage7_dir)

    # ── 9. GE9X turbofan thermodynamic SFC analysis ─────────────────────
    stage2_dir = base_config.get_stage_dir(2)
    try:
        run_ge9x_analysis(
            stage4_dir=base_config.get_stage_dir(4),
            stage2_dir=stage2_dir,
            tables_dir=tables_dir,
        )
    except Exception as exc:
        LOGGER.warning("GE9X analysis failed (non-fatal): %s", exc)

    # ── 10. Log summary ──────────────────────────────────────────────────
    if sfc_results:
        mean_reduction = sum(r.sfc_reduction_percent for r in sfc_results) / len(sfc_results)
        max_reduction  = max(r.sfc_reduction_percent for r in sfc_results)
        LOGGER.info("Mean SFC reduction: %.2f%%", mean_reduction)
        LOGGER.info("Max SFC reduction: %.2f%%", max_reduction)

    LOGGER.info("=" * 70)
    LOGGER.info("Stage 7 complete.")
    LOGGER.info("  Tables:  %s", tables_dir)
    LOGGER.info("  Figures: %s", figures_dir)
    LOGGER.info("=" * 70)


if __name__ == "__main__":
    import logging as _logging
    _logging.basicConfig(level=_logging.INFO,
                         format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    run_sfc_analysis()
