# Stage 6 README - Reverse-Thrust Mechanism Weight

## Purpose of This Stage

Stage 6 evaluates the reverse-thrust concept from a mechanism-weight and cruise-SFC perspective. It compares a VPF pitch mechanism against a conventional cascade thrust reverser.

This stage answers: **what is the weight and cruise SFC trade-off of replacing a conventional reverser with a variable-pitch fan mechanism?**

## Inputs

| Input | Path | Description |
|---|---|---|
| Reverse-thrust configuration | `config/engine_parameters.yaml`, `reverse_thrust` | Mechanism fractions, dry engine weight, aircraft L/D, reverse assumptions. |
| Mission configuration | `config/engine_parameters.yaml`, `mission` | Design thrust and cruise thrust fraction. |

## Code Location

| File | Responsibility |
|---|---|
| `src/vpf_analysis/stage6_reverse_thrust/application/run_reverse_thrust.py` | Main Stage 6 workflow. |
| `src/vpf_analysis/stage6_reverse_thrust/reverse_thrust_core.py` | Mechanism weight model and optional reverse BEM support. |
| `src/vpf_analysis/stage6_reverse_thrust/adapters/filesystem/results_writer.py` | Writes CSV and figure. |

## Method

The current main Stage 6 workflow:

1. Reads reverse-thrust and mission parameters.
2. Computes VPF mechanism weight:
   - `n_engines * engine_dry_weight_kg * mechanism_weight_fraction`.
3. Computes conventional reverser weight:
   - `n_engines * engine_dry_weight_kg * conventional_reverser_fraction`.
4. Computes weight saving versus conventional reverser.
5. Converts added or saved weight into equivalent cruise thrust change using aircraft `L/D`.
6. Estimates SFC penalty or benefit from that thrust change.
7. Writes a table, figure, and summary.

## Outputs

| Output | Path | Meaning |
|---|---|---|
| `mechanism_weight.csv` | `results/stage6_reverse_thrust/tables/` | Weight and SFC impact metrics. |
| `mechanism_weight_comparison.png` | `results/stage6_reverse_thrust/figures/` | Weight and SFC comparison figure. |
| `reverse_thrust_summary.txt` | `results/stage6_reverse_thrust/` | Stage summary and limitations. |

## Current Key Results

| Metric | Value | Meaning |
|---|---:|---|
| `mechanism_weight_kg` | 1097.4 kg | Estimated VPF mechanism weight for both engines. |
| `conventional_reverser_weight_kg` | 2606.3 kg | Estimated conventional cascade reverser (full TRU system) for both engines. |
| `weight_saving_vs_conventional_kg` | 1508.9 kg | Estimated weight saving versus conventional reverser. |
| `sfc_cruise_penalty_pct` | 0.225% | Penalty relative to no reverser. |
| `sfc_benefit_vs_conventional_pct` | 0.309% | Benefit relative to conventional reverser. |

Interpretation:

- VPF is heavier than having no reverser mechanism.
- VPF is lighter than the configured conventional cascade reverser.
- Relative to conventional reverser weight, VPF gives a modeled cruise SFC benefit.

## Figure Interpretation

### `mechanism_weight_comparison.png`

The figure has two panels:

1. System weight for:
   - no reverser baseline;
   - VPF mechanism;
   - conventional cascade reverser.
2. Cruise SFC penalty relative to no reverser.

It demonstrates:

- the VPF mechanism has a positive weight penalty versus no reverser;
- the conventional cascade reverser is heavier in the configured model;
- VPF can be interpreted as a net SFC benefit when replacing a conventional reverser.

## Important Considerations

- This stage is primarily a **weight and SFC trade study**.
- It does not validate whether the VPF can aerodynamically generate the required reverse thrust.
- The summary explicitly notes that reverse-thrust aerodynamic feasibility would need extended polar data or experimental validation.
- Stage 6 does not validate whether the VPF can aerodynamically generate the required reverse thrust — that would require post-stall polar data or experimental validation (see design_decisions.md §9).

## Model Restrictions

| Restriction | Meaning |
|---|---|
| Weight fractions are assumptions | Mechanism and reverser fractions drive the headline results. |
| No detailed structural model | Hardware mass is estimated parametrically. |
| No validated reverse-flow aerodynamics | Reverse thrust force is not proven by this stage. |
| Aircraft L/D conversion is simplified | SFC penalty from weight is estimated through equivalent cruise thrust. |
| No validated reverse-flow aerodynamics | Reverse thrust force is not proven by this stage. |

## Downstream Role

Stage 6 provides mechanism-weight SFC context to Stage 7. Its table may be read by Stage 7 for reporting/logging of mechanism penalty and conventional reverser comparison.

