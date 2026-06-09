# Stage 7 README - SFC and Mission Analysis

## Purpose of This Stage

Stage 7 estimates how the aerodynamic benefit of variable pitch affects fan efficiency, specific fuel consumption, and mission fuel burn. It also runs a GE9X-oriented parametric analysis relating `CL/CD` to fuel saving.

This stage answers: **how much of the aerodynamic VPF benefit can plausibly translate into propulsion and mission-level fuel savings?**

## Inputs

| Input | Path | Description |
|---|---|---|
| Stage 4 metrics | `results/stage4_performance_metrics/tables/summary_table.csv` | Fixed-pitch and VPF aerodynamic efficiency values. |
| Stage 5 tables | `results/stage5_pitch_kinematics/tables/` | Kinematic and 3D context used when available. |
| Stage 3 corrected polars | `results/stage3_compressibility_correction/` | Used to evaluate fixed-pitch incidence with Stage 5 kinematics. |
| Engine parameters | `config/engine_parameters.yaml` | Baseline SFC, fan efficiency, BPR, `tau`, mission data. |
| Stage 6 mechanism table | `results/stage6_reverse_thrust/tables/mechanism_weight.csv` | Mechanism weight context when present. |

## Code Location

| File | Responsibility |
|---|---|
| `src/vpf_analysis/stage7_sfc_analysis/application/run_sfc_analysis.py` | Stage 7 orchestration, SFC tables, main SFC figure. |
| `src/vpf_analysis/stage7_sfc_analysis/sfc_core.py` | Core SFC, fan efficiency, mission fuel burn, and sensitivity calculations. |
| `src/vpf_analysis/stage7_sfc_analysis/engine/ge9x_analysis.py` | GE9X parametric `CL/CD` sweep and figures. |
| `src/vpf_analysis/stage7_sfc_analysis/engine/sfc_model.py` | Standalone SFC improvement model. |
| `src/vpf_analysis/stage7_sfc_analysis/engine/turbofan_cycle.py` | Simplified thermodynamic SFC model. |

## Method

Stage 7:

1. Reads Stage 4 aerodynamic metrics.
2. Loads baseline engine parameters.
3. Loads Stage 5 kinematic data when available.
4. Computes per-section efficiency ratio:
   - `epsilon = (CL/CD)_vpf / (CL/CD)_fixed`.
5. Applies caps to prevent unrealistic transfer of 2D gains.
6. Computes profile mechanism gain.
7. Computes fan-map mechanism gain from flow coefficient shifts.
8. Combines the gains with physical caps.
9. Converts fan efficiency change into new SFC.
10. Computes mission fuel burn, CO2 saving, and cost saving.
11. Writes SFC tables and figures.
12. Runs GE9X parametric `CL/CD` sweep.

## Outputs

| Output | Path | Meaning |
|---|---|---|
| `sfc_section_breakdown.csv` | `results/stage7_sfc_analysis/tables/` | Per-section fixed vs VPF aerodynamic efficiency. |
| `sfc_analysis.csv` | Same | Aggregated SFC result per condition. |
| `sfc_sensitivity.csv` | Same | Internal `tau` sensitivity by condition. |
| `mission_fuel_burn.csv` | Same | Mission fuel, CO2, and cost saving per phase. |
| `ge9x_sfc_parametric.csv` | Same | Parametric GE9X `CL/CD` sweep. |
| `ge9x_sfc_improvement.csv` | Same | Key GE9X sweep points. |
| `ge9x_sfc_improvement.tex` | Same | LaTeX table export. |
| PNG figures | `results/stage7_sfc_analysis/figures/` | SFC and GE9X plots. |
| `sfc_analysis_summary.txt` | Stage 7 folder | Detailed SFC text summary. |
| `finalresults_stage7.txt` | Stage 7 folder | Stage summary. |

## Current Key Results

### Aggregated SFC Results

| Condition | Fixed Mean `CL/CD` | VPF Mean `CL/CD` | `epsilon_mean` | New Fan Efficiency | SFC Baseline | SFC New | SFC Reduction |
|---|---:|---:|---:|---:|---:|---:|---:|
| climb | 42.091 | 60.519 | 1.412 | 0.9432 | 0.5145 | 0.4930 | 4.181% |
| cruise | 41.111 | 41.111 | 1.000 | 0.9000 | 0.4900 | 0.4900 | 0.000% |
| descent | 51.827 | 132.213 | 2.563 | 0.9432 | 0.5390 | 0.5165 | 4.181% |
| takeoff | 45.464 | 45.587 | 1.002 | 0.9103 | 0.5635 | 0.5577 | 1.032% |

Interpretation:

- Cruise shows zero improvement because it is the fixed-pitch design reference.
- Climb and descent reach the same applied fan-efficiency cap in the current result set.
- Takeoff has a smaller modeled SFC benefit.

### Mission Fuel Burn

| Phase | Fuel Baseline | Fuel VPF | Fuel Saving | CO2 Saving | Cost Saving |
|---|---:|---:|---:|---:|---:|
| takeoff | 50.278 kg | 49.760 kg | 0.519 kg | 1.639 kg | 0.467 USD |
| climb | 1377.190 kg | 1319.607 kg | 57.583 kg | 181.962 kg | 51.825 USD |
| cruise | 10492.874 kg | 10492.874 kg | 0.000 kg | 0.000 kg | 0.000 USD |
| descent | 120.231 kg | 115.204 kg | 5.027 kg | 15.886 kg | 4.524 USD |

Current total mission fuel saving is approximately **63.13 kg** for the configured mission phases.

## Figure Interpretation

### `sfc_improvement_by_condition.png`

Shows fixed-pitch `CL/CD` versus VPF `CL/CD` by section for each condition.

It demonstrates:

- the aerodynamic input driving SFC changes;
- which sections and flight phases provide the largest modeled VPF gain;
- why cruise is a reference case with no gain.

How to interpret:

- Larger green VPF bars relative to blue fixed-pitch bars mean stronger aerodynamic benefit.
- Similar bars mean low SFC benefit from pitch variation.

### `fuel_saving_vs_clcd.png`

Shows GE9X parametric fuel saving as a function of new `CL/CD`.

It demonstrates:

- how fuel saving scales with aerodynamic efficiency improvement;
- where configured operating conditions sit relative to the cruise reference.

How to interpret:

- Values to the right of the reference line indicate higher `CL/CD` than the fixed reference.
- The curve is a model response, not a measured engine map.

### `sfc_sensitivity_k_throttle.png`

Shows fuel saving versus `CL/CD` for multiple `k_throttle` assumptions.

It demonstrates:

- uncertainty in the relationship between aerodynamic efficiency and fuel saving;
- the sensitivity of results to part-power SFC modeling.

How to interpret:

- Wider separation between curves means model uncertainty is important.
- A single headline fuel-saving value should be read together with this sensitivity.

## Important Considerations

- Stage 7 converts aerodynamic gains to SFC using damping and physical caps.
- Large aerodynamic `epsilon` values do not translate linearly into SFC reduction.
- Cruise has zero benefit by construction because it defines the fixed-pitch design reference.
- Mission savings depend strongly on phase duration and thrust fraction.
- The current mission gives most fuel saving in climb because climb combines nonzero SFC benefit with meaningful duration and thrust.

## Model Restrictions

| Restriction | Meaning |
|---|---|
| Empirical SFC transfer | `tau` controls how much profile gain reaches fan efficiency. |
| Physical caps | Fan efficiency gains are capped to avoid unrealistic results. |
| Simplified mission profile | Only configured phases are modeled. |
| No full engine deck | The GE9X analysis is simplified and parametric. |
| No direct coupling to structural/weight changes except Stage 6 context | SFC is mainly aerodynamic-efficiency driven. |
| Sensitivity assumptions | `k_throttle` and `tau` are uncertain model parameters. |

## Downstream Role

Stage 7 is the final project-level performance stage. Its outputs are the main basis for interpreting VPF benefit at propulsion and mission level.

