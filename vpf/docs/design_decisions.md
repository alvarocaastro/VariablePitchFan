# Design Decisions

This document records technical decisions that are not immediately obvious from the code alone.

## 1. Solidity as the Primary Blade Geometry Parameter

Decision: `blade_geometry` in `analysis_config.yaml` uses `solidity` (`sigma`) rather than chord length as the main blade-geometry input.

Reason: in Stages 5 to 7, chord mainly appears through non-dimensional relationships:

| Relationship | Use |
|---|---|
| `sigma = c * Z / (2*pi*r)` | Weinig cascade factor and Carter deviation. |
| `c/r = sigma * 2*pi/Z` | Snel rotational correction. |

Consequence: for cascade and rotational corrections, the result depends on `sigma` and blade count `Z`, not directly on the absolute fan scale. When dimensional chord is required, it is recovered with:

```python
c = sigma * 2 * math.pi * r / Z
```

## 2. Reynolds Numbers Declared in YAML

Decision: Reynolds numbers are specified as a `{condition: {section: Re}}` lookup table.

Reason: Reynolds number depends on atmosphere, relative velocity, chord, RPM, and viscosity. Declaring it explicitly makes the derivation auditable and allows deliberate scenario overrides without adding a runtime atmosphere model.

Risk: if fan geometry changes, Reynolds values do not update automatically.

## 3. Canonical `ld_corrected` Column

Decision: Stage 3 writes `ld_corrected` as the canonical corrected-efficiency column.

Reason: downstream stages can locate the corrected lift-to-drag ratio without knowing which stage produced the polar. Column resolution is centralized in `postprocessing/aerodynamics_utils.py`.

## 4. Split Aerodynamic and Engine Configuration

Decision: `analysis_config.yaml` and `engine_parameters.yaml` are separate.

| File | Changes When |
|---|---|
| `analysis_config.yaml` | Fan geometry, aerodynamic conditions, XFOIL setup, or airfoils change. |
| `engine_parameters.yaml` | Engine assumptions, mission model, SFC assumptions, or reverse-thrust assumptions change. |

This reduces accidental coupling between early aerodynamic analysis and later mission/SFC assumptions.

## 5. Centralized Physical Constants

Decision: empirical coefficients such as Carter, Snel, design-zone limits, and SFC caps live in configuration dataclasses, especially `PhysicsConstants`.

Reason: this reduces duplication, prevents silent drift between modules, and makes tests easier to reason about.

## 6. File-Based Stage Communication

Decision: stages exchange information through CSV files and artifacts in `results/`.

Reason: every intermediate result is inspectable, and later stages can be rerun from disk. `pipeline/contracts.py` validates the minimum artifacts required before advancing.

## 7. Second-Peak Efficiency Logic

Decision: `alpha_opt` uses second-peak logic and minimum-CL filters.

Reason: XFOIL can produce low-incidence `CL/CD` peaks caused by laminar-bubble behavior or very small drag values. Such points are not necessarily viable fan-blade operating points.

## 8. Partial Transfer of 2D Gain to SFC

Decision: profile efficiency gains are damped with `profile_efficiency_transfer` (`tau`) and physical caps in Stage 7.

Reason: a 2D airfoil improvement does not transfer perfectly to a real 3D fan because of tip clearance, shocks, secondary flows, distortion, and blade interactions.

## 9. Reverse-Thrust Scope Limited to Weight and Theoretical Documentation

Decision: Stage 6 computes mechanism weight via the D^2.5 fan-diameter scaling law (Raymer 2018) and reports a theoretical SFC penalty. No aerodynamic BEM simulation of the reverse-pitch condition is performed.

Reason: aerodynamic prediction in full reverse requires post-stall polar extrapolation (Viterna-Corrigan or equivalent) that is outside XFOIL's valid regime and has no available validation data for this fan geometry. Adding unvalidated BEM results would inflate confidence beyond what the model supports.

## 10. Known Modelling Limitations

The following limitations were identified during pipeline development and are accepted without correction. They are documented here so that future users understand the scope of the analysis.

| Area | Limitation | Impact | Justification for not fixing |
|---|---|---|---|
| Supersonic tip sections | XFOIL polars generated at M_ref = 0.2 (incompressible reference). Kármán-Tsien correction is clamped at M = 0.95 for sections where M_rel > 1.0 (tip at climb, cruise, descent). | L/D values at the tip under transonic conditions are extrapolated, not modelled. | Fixing would require a transonic solver (MISES, CFD). Clamping at M = 0.95 is conservative and the standard approach when only subsonic polars are available. |
| Snel 3D correction at root | The Snel (1993) rotational augmentation model is validated for c/r ≤ 0.3. The root section operates at c/r ≈ 0.68. | Root CL augmentation may be over-predicted. | A warning is logged. The Du-Selig model is applied in parallel as a cross-check. Both are secondary corrections; the primary result is the 2D XFOIL polar. |
| cruise_alpha_min inconsistency | Stage 4 evaluates cruise performance at alpha_min = 2.0–2.5°; Stage 2 XFOIL sweeps down to 3.0°. | Cruise operating point in Stage 4 metrics may be 0.5–0.8° off the polar edge. | Impact is confined to Stage 4 figures; blade twist (Stage 5) and SFC (Stage 7) use independent kinematics and are unaffected. Risk of introducing new errors > benefit. |
| Per-section epsilon cap | EPSILON_CAP = 3.0 in `sfc_parameters.py`. At descent/mid_span ε = 2.805, giving efficiency_gain_pct ≈ 180 % in `sfc_section_breakdown.csv`. | Per-section breakdown looks alarming but is aerodynamically real: the fixed blade is heavily off-design at descent. | Aggregate SFC results are protected by ETA_FAN_DELTA_CAP = 0.04 (4 % absolute cap). The section breakdown is an informational diagnostic, not a headline result. |
| Profile-efficiency transfer coefficient | tau = 0.08 — derived for UHBPR BPR=15, FPR=1.30. Multiplicative penalty factors applied to Cumpsty (2004) §4.3.2 baseline (τ≈0.35 for conventional fans): transonic tip shock factor × 0.45 (Gunn & Hall, GT2014-26698), low-h/t secondary flows × 0.55 (Koch & Smith 1976), tip clearance/endwall × 0.75 (Denton 1993, ASME 93-GT-435; Smith 1970) → ≈ 0.065, rounded up to 0.08. | SFC improvement is proportionally sensitive to tau. | Deliberately conservative: a lower tau is harder to rebut academically. Any challenger must rebut four independent bibliographic sources. |

