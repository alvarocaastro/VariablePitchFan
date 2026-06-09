# Maintenance Guide

## General Maintenance Principles

- Keep stage boundaries explicit. Prefer passing information through `results/` artifacts unless a deliberate architecture change is made.
- Keep physical assumptions in YAML or centralized dataclasses, not scattered constants.
- Treat generated outputs as reproducible artifacts, not source files.
- Run tests after changes to shared utilities, configuration loading, peak detection, or SFC logic.
- Validate XFOIL output quality before trusting downstream metrics.

## How to Add a New Airfoil

1. Add the `.dat` file to `data/airfoils/`.
2. Add an entry to `config/airfoils.yaml`:

```yaml
- name: "NEW AIRFOIL"
  dat_file: "new_airfoil.dat"
  family: "..."
  comment: "..."
```

3. Run:

```powershell
python run_analysis.py --from-stage 1 --to-stage 2
```

4. Inspect `results/stage1_airfoil_selection/airfoil_selection/scores.csv` and `polar_comparison.png`.

## How to Add a New Flight Condition

A new condition must be added consistently across configuration sections:

- `target_mach`
- `reynolds`
- `ncrit`
- `fan_geometry.rpm`
- `fan_geometry.axial_velocity`
- `flight_conditions`
- `engine_parameters.yaml` if SFC or mission analysis should include it

Then review all code with hard-coded condition order, including:

- `stage2_xfoil_simulations/pitch_map.py`
- `stage4_performance_metrics/plots.py`
- `stage5_pitch_kinematics/application/run_pitch_kinematics.py`
- `stage7_sfc_analysis/application/run_sfc_analysis.py`
- `stage7_sfc_analysis/engine/ge9x_analysis.py`
- `run_sensitivity.py`

Several plotting functions use fixed ordering lists. Update them before expecting the new condition to appear in all figures.

## How to Add a New Blade Section

Add the section consistently to:

- `analysis_config.yaml`: `blade_sections`
- `fan_geometry.radius`
- `blade_geometry.solidity`
- `reynolds` for every condition

Then review code with fixed section order:

- `root`
- `mid_span`
- `tip`

The following modules contain section-order assumptions:

- `stage2_xfoil_simulations/pitch_map.py`
- `stage4_performance_metrics/plots.py`
- `stage5_pitch_kinematics/application/run_pitch_kinematics.py`
- `stage6_reverse_thrust/reverse_thrust_core.py`
- `stage7_sfc_analysis/application/run_sfc_analysis.py`
- `stage7_sfc_analysis/sfc_core.py`

Adding a section is therefore more invasive than adding a new airfoil.

## How to Add New Results or Figures

1. Identify the stage responsible for the data.
2. Add calculation logic in the stage's core/service module when possible.
3. Add file writing in the stage's writer or orchestrator.
4. Add figure generation with the shared style from `shared/plot_style.py`.
5. Update `results.md` with:
   - Output name.
   - Code location.
   - Data used.
   - Visual meaning.
   - Interpretation.
   - Limitations.
6. Add tests if the result depends on non-trivial logic.

## How to Add New Data Columns

For CSV outputs:

1. Add the field to the relevant dataclass if it represents domain data.
2. Add it to the writer function.
3. Update any reader that expects a fixed schema.
4. Update downstream stages if they consume the table.
5. Update `data_documentation.md` and `results.md`.

Avoid silently changing column names used by later stages, especially:

- `ld_corrected`
- `max_efficiency`
- `alpha_opt_deg`
- `eff_at_design_alpha`
- `delta_alpha_deg`
- `CL_CD_fixed`
- `CL_CD_vpf`

## Testing Guidance

Run the full suite for shared or cross-stage changes:

```powershell
pytest
```

Run targeted tests for focused changes:

| Change Area | Suggested Tests |
|---|---|
| Airfoil parsing | `pytest tests/test_airfoil_reader.py -v` |
| Airfoil scoring | `pytest tests/test_airfoil_selection.py -v` |
| Peak selection | `pytest tests/test_peak_finding.py -v` |
| Compressibility | `pytest tests/test_prandtl_glauert.py -v` |
| SFC | `pytest tests/test_sfc_model.py -v` |
| Contracts | `pytest tests/test_pipeline_contracts.py -v` |
| Reverse extrapolation | `pytest tests/test_viterna_extrapolation.py -v` |

## Areas Requiring Special Care

| Area | Why It Is Fragile |
|---|---|
| XFOIL execution | External binary, convergence sensitivity, timeouts, file movement. |
| Peak detection | Low-alpha artifacts can produce false optima. |
| Column resolution | Downstream stages rely on expected names and priority order. |
| Stage 5 section ordering | Many plots and calculations assume root, mid-span, tip. |
| Stage 7 SFC caps | Small changes can strongly affect headline SFC results. |
| Stage 7 SFC caps | Small changes to tau or EPSILON_CAP can strongly affect per-section breakdown and headline SFC results. |

## Detected Technical Debt

| Item | Impact | Suggested Improvement |
|---|---|---|
| `scipy` present in environment but not declared in deps | If environment changes, imports may silently fail. | Add `scipy` to `pyproject.toml` or confirm it is not used after BEM removal. |
| Fixed condition and section order in several modules | Makes extension harder. | Centralize ordering from settings and update plots dynamically. |
| `results/` is not versioned | Reproducibility depends on local files. | Add result archiving workflow or checksums for report snapshots. |
| Stage numbering mismatch | Resolved: CLI options now use analysis stages 1 through 7. | Keep documentation and CLI help aligned with `run_analysis.py`. |
| Root README may drift from current outputs | Conflicting docs can confuse users. | Make `docs/` the authoritative documentation set or update README after major changes. |
| Stage 6 aerodynamic prediction intentionally absent | Stage 6 reports weight and theoretical SFC penalty only. No BEM simulation. | See design_decisions.md §9 for rationale. Do not add aerodynamic Stage 6 prediction without validated post-stall polars. |

## Future Improvements

- Add package metadata such as `pyproject.toml`.
- Add `scipy` or remove the optional dependency path.
- Add CI for tests.
- Add a reproducibility manifest for each run, including config hash, XFOIL path/version, timestamp, and git commit.
- Add a result index CSV summarizing all generated files.
- Add schema validation for all stage output CSV files.
- Add calibrated fan-map data if available.
- Add full radial integration instead of three-section approximations.
- Add experimental or CFD validation for compressibility, 3D corrections, and reverse thrust.
