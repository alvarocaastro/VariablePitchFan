# Results Documentation

This document is dedicated only to generated project results. It explains what the pipeline writes, where outputs are stored, what each result means, and how figures should be interpreted.

## Results Root

All generated outputs are under:

```text
results/
```

The directory is ignored by Git except for `.gitkeep`, so result sets should be archived separately when they are important for a report or release.

## Current Result Inventory

The current workspace contains:

| Artifact Type | Count | Notes |
|---|---:|---|
| PNG figures | 103 | Stage and sensitivity plots. |
| CSV tables | 58 | Polars, metrics, kinematics, SFC, sensitivity. |
| TXT summaries | 25 | Stage summaries and XFOIL text outputs. |
| DAT files | 17 | XFOIL polar outputs and selected airfoil marker. |
| TEX files | 1 | GE9X SFC improvement LaTeX table. |

## Intermediate vs Final Results

| Category | Examples | Interpretation |
|---|---|---|
| Intermediate aerodynamic data | Stage 1 candidate polars, Stage 2 raw polars, Stage 3 corrected polars | Used by later stages. Inspect for convergence, consistency, and physical plausibility. |
| Intermediate metrics | Stage 4 `summary_table.csv`, Stage 5 kinematics tables | Bridge between aerodynamic results and propulsion/SFC analysis. |
| Final project-level results | Stage 6 mechanism weight, Stage 7 SFC and mission fuel burn, sensitivity table | Main decision-support outputs. |
| Diagnostic figures | XFOIL per-case plots, correction plots, efficiency maps | Used to validate and understand the calculations. |
| Presentation figures | SFC comparison, GE9X fuel saving sweep, pitch maps | Suitable for technical reports after verifying assumptions. |

## Stage 1: Airfoil Selection

### Tables and Text Outputs

| Output | Path | Meaning |
|---|---|---|
| `scores.csv` | `results/stage1_airfoil_selection/airfoil_selection/scores.csv` | Candidate airfoil score table. Current best: NACA 65-410. |
| `selected_airfoil.dat` | `results/stage1_airfoil_selection/airfoil_selection/selected_airfoil.dat` | Text marker containing the selected airfoil name. Despite `.dat`, it is not a geometry file. |
| `*_polar.txt` | `results/stage1_airfoil_selection/airfoil_selection/` | Raw XFOIL polar text outputs for candidate-condition combinations. |
| `finalresults_stage1.txt` | `results/stage1_airfoil_selection/finalresults_stage1.txt` | Human-readable stage summary. |

Current detected score ranking:

| Rank | Airfoil | Notes |
|---:|---|---|
| 1 | NACA 65-410 | Highest total score. |
| 2 | NACA 0012 | Lower total score despite strong `max_ld`. |
| 3 | NACA 63-215 | Lower weighted score. |
| 4 | NACA 65-210 | Lowest detected score among candidates. |

### Figure: `polar_comparison.png`

| Field | Description |
|---|---|
| Path | `results/stage1_airfoil_selection/airfoil_selection/polar_comparison.png` |
| Generated in | `stage1_airfoil_selection/airfoil_selection_service.py`, `_save_comparison_figure()` |
| Data used | Stage 1 XFOIL polars for the primary weighted selection condition. |
| Visual content | `CL/CD` versus angle of attack for each candidate airfoil, with vertical markers at selected `alpha_opt`. |
| Purpose | Comparison and selection diagnostic. |
| Interpretation | The better candidate combines high `CL/CD`, robust peak width, and acceptable stall margin. |
| Conclusion enabled | Confirms why NACA 65-410 was selected by the scoring logic. |
| Limitations | Only shows the primary condition visually; final score is mission-weighted across all configured selection conditions. |

## Stage 2: Final XFOIL Simulations and Pitch Map

### Tables and Data Outputs

| Output | Path | Meaning |
|---|---|---|
| `polars/{flight}_{section}.csv` | `results/stage2_xfoil_simulations/polars/` | Canonical raw XFOIL polar CSVs for 4 flight conditions x 3 sections. |
| `simulation_plots/{flight}/{section}/polar.csv` | Nested under `simulation_plots/` | Same per-case polar stored with plots and raw XFOIL `polar.dat`. |
| `pitch_map/blade_pitch_map.csv` | `results/stage2_xfoil_simulations/pitch_map/` | Converts `alpha_opt` into inflow angle `phi` and required blade pitch `beta`. |
| `finalresults_stage2.txt` | `results/stage2_xfoil_simulations/finalresults_stage2.txt` | Stage summary with simulations, Reynolds/Ncrit, stall margin, and pitch range. |

### Repeated Per-Case Figures

The following figures exist for each combination of:

- Flight condition: `takeoff`, `climb`, `cruise`, `descent`
- Blade section: `root`, `mid_span`, `tip`

That gives 12 cases and 36 per-case figures.

#### `efficiency_plot.png`

| Field | Description |
|---|---|
| Path pattern | `results/stage2_xfoil_simulations/simulation_plots/{flight}/{section}/efficiency_plot.png` |
| Generated in | `stage2_xfoil_simulations/final_analysis_service.py`, `_plot_all()` |
| Data used | The corresponding XFOIL `polar.csv`. |
| Visual content | `CL/CD` versus angle of attack, with `alpha_opt` highlighted when available. |
| Axes | X: `alpha` in degrees. Y: `CL/CD`. |
| Purpose | Diagnostic and comparison. |
| Interpretation | The peak indicates the most efficient 2D operating incidence for that case. |
| Limitations | Raw XFOIL result before Stage 3 compressibility corrections. Low-alpha artifacts may still exist. |

#### `cl_alpha_stall.png`

| Field | Description |
|---|---|
| Path pattern | `results/stage2_xfoil_simulations/simulation_plots/{flight}/{section}/cl_alpha_stall.png` |
| Generated in | `stage2_xfoil_simulations/final_analysis_service.py`, `_plot_all()` |
| Data used | The corresponding XFOIL `polar.csv`. |
| Visual content | `CL` versus `alpha`, with maximum lift and stall-onset marker. |
| Axes | X: `alpha` in degrees. Y: `CL`. |
| Purpose | Stall-margin diagnostic. |
| Interpretation | The marked point indicates the detected maximum lift in the positive-alpha range. |
| Limitations | Stall detection comes from XFOIL polar behavior, not wind-tunnel validation. |

#### `polar_plot.png`

| Field | Description |
|---|---|
| Path pattern | `results/stage2_xfoil_simulations/simulation_plots/{flight}/{section}/polar_plot.png` |
| Generated in | `stage2_xfoil_simulations/final_analysis_service.py`, `_plot_all()` |
| Data used | The corresponding XFOIL `polar.csv`. |
| Visual content | Lift-drag polar, `CL` versus `CD`. |
| Axes | X: `CD`. Y: `CL`. |
| Purpose | Aerodynamic polar diagnostic. |
| Interpretation | A cleaner polar has smooth drag rise and reasonable lift behavior. |
| Limitations | Still incompressible or low-Mach XFOIL baseline before Stage 3 corrections. |

### Pitch-Map Figures

#### `blade_pitch_map.png`

| Field | Description |
|---|---|
| Path | `results/stage2_xfoil_simulations/pitch_map/blade_pitch_map.png` |
| Generated in | `stage2_xfoil_simulations/pitch_map.py`, `plot_pitch_map()` |
| Data used | `blade_pitch_map.csv`, derived from `alpha_opt`, RPM, radius, and axial velocity. |
| Visual content | Grouped bars of required blade pitch angle `beta` by flight condition and section. |
| Purpose | Kinematic comparison and VPF requirement estimate. |
| Interpretation | Larger spread in `beta` means greater pitch actuation range is needed. |
| Limitations | Uses Stage 2 2D optima; Stage 5 later refines with 3D corrections. |

#### `alpha_opt_evolution.png`

| Field | Description |
|---|---|
| Path | `results/stage2_xfoil_simulations/pitch_map/alpha_opt_evolution.png` |
| Generated in | `stage2_xfoil_simulations/pitch_map.py`, `plot_alpha_opt_evolution()` |
| Data used | `alpha_eff_map` from Stage 2. |
| Visual content | `alpha_opt` across flight phases, one line per blade section. |
| Purpose | Diagnostic and VPF motivation. |
| Interpretation | If optimal incidence changes with flight phase, fixed pitch is off-design outside cruise. |
| Limitations | Based on raw XFOIL polars before compressibility and 3D corrections. |

#### `vpf_efficiency_{section}.png`

| Field | Description |
|---|---|
| Path pattern | `results/stage2_xfoil_simulations/pitch_map/vpf_efficiency_root.png`, `vpf_efficiency_mid_span.png`, `vpf_efficiency_tip.png` |
| Generated in | `stage2_xfoil_simulations/pitch_map.py`, `plot_vpf_efficiency_by_section()` |
| Data used | Stage 2 polar DataFrames and `alpha_eff_map`. |
| Visual content | `CL/CD` versus `alpha` for all flight phases in one section, with VPF operating points and cruise fixed-pitch reference. |
| Purpose | Direct fixed-pitch vs VPF diagnostic. |
| Interpretation | Off-cruise conditions operating far from their own peak show potential VPF benefit. |
| Limitations | 2D raw polar view only; corrected results are in later stages. |

#### `vpf_clcd_penalty.png`

| Field | Description |
|---|---|
| Path | `results/stage2_xfoil_simulations/pitch_map/vpf_clcd_penalty.png` |
| Generated in | `stage2_xfoil_simulations/pitch_map.py`, `plot_vpf_clcd_penalty()` |
| Data used | Stage 2 polars and cruise `alpha_opt` reference. |
| Visual content | Two panels: absolute `CL/CD` for VPF vs fixed pitch, and retained efficiency percentage. |
| Purpose | Comparison and presentation. |
| Interpretation | Values below 100 percent retained efficiency indicate loss from using cruise pitch outside cruise. |
| Limitations | Uses Stage 2 raw polars rather than Stage 3 corrected polars. |

## Stage 3: Compressibility Correction

### Tables and Data Outputs

| Output | Path | Meaning |
|---|---|---|
| `corrected_polar.csv` | `results/stage3_compressibility_correction/{flight}/{section}/` | Corrected polar with PG, KT, wave-drag, and `ld_corrected`. |
| `finalresults_stage3.txt` | `results/stage3_compressibility_correction/finalresults_stage3.txt` | Compressibility summary. |

### Per-Case Figure: `corrected_plots.png`

| Field | Description |
|---|---|
| Path pattern | `results/stage3_compressibility_correction/{flight}/{section}/corrected_plots.png` |
| Generated in | `stage3_compressibility_correction/correction_service.py`, `_plot_comparison()` |
| Data used | Original Stage 2 polar and corrected Stage 3 DataFrame. |
| Visual content | Two panels: `CL` vs `alpha` and `CL/CD` vs `alpha`, comparing XFOIL baseline, Prandtl-Glauert, and Karman-Tsien. |
| Purpose | Correction diagnostic and validation. |
| Interpretation | The gap between curves shows compressibility impact at the target Mach. Drag-rise behavior reduces efficiency where wave drag is significant. |
| Limitations | Uses engineering correction models, not CFD or measured transonic cascade data. |

### Section Summary Figures

#### `correction_comparison_{section}.png`

| Field | Description |
|---|---|
| Path pattern | `results/stage3_compressibility_correction/figures/correction_comparison_root.png`, `correction_comparison_mid_span.png`, `correction_comparison_tip.png` |
| Generated in | `stage3_compressibility_correction/correction_service.py`, `plot_section_summary()` |
| Data used | Corrected polars for all flight conditions in a section. |
| Visual content | Corrected `CL` and `CL/CD` versus `alpha` for all conditions. |
| Purpose | Cross-condition comparison after compressibility correction. |
| Interpretation | Shows how Mach and condition shift corrected lift and efficiency behavior within a blade section. |
| Limitations | Same correction-model limitations as the per-case plots. |

## Stage 4: Aerodynamic Performance Metrics

### Tables

| Output | Path | Meaning |
|---|---|---|
| `summary_table.csv` | `results/stage4_performance_metrics/tables/summary_table.csv` | Main aerodynamic metrics table consumed by Stage 7. |
| `clcd_max_by_section.csv` | `results/stage4_performance_metrics/tables/clcd_max_by_section.csv` | Focused table for optimum `CL/CD`, `CL`, `CD`, stall margin, and fixed-pitch gain. |
| `finalresults_stage4.txt` | `results/stage4_performance_metrics/finalresults_stage4.txt` | Human-readable summary. |

Current detected `max_efficiency` range in `summary_table.csv`: approximately 38.65 to 139.27, average 66.25 across 12 cases.

### Figure: `compressibility_comparison.png`

| Field | Description |
|---|---|
| Path | `results/stage4_performance_metrics/figures/compressibility_comparison.png` |
| Generated in | `stage4_performance_metrics/plots.py`, `plot_efficiency_penalty_overview()` |
| Data used | Stage 4 metrics and Stage 3 corrected polars, default section `mid_span`. |
| Visual content | `CL/CD` vs `alpha` for conditions, with VPF optima and fixed-pitch reference. |
| Purpose | Fixed-pitch penalty overview. |
| Interpretation | Filled points show condition-specific optimum; hollow/fixed reference points show where a fixed cruise pitch would operate. |
| Limitations | Default summary section is `mid_span`; it is not a full radial integration. |

### Figures: `polar_efficiency_{flight}_{section}.png`

| Field | Description |
|---|---|
| Path pattern | `results/stage4_performance_metrics/figures/polar_efficiency_{flight}_{section}.png` |
| Generated in | `stage4_performance_metrics/plots.py`, `generate_efficiency_plots()` |
| Data used | Stage 3 corrected polar for one flight-condition and section pair. |
| Visual content | Corrected `CL/CD` vs `alpha`, with optimal point marked. |
| Purpose | Per-case diagnostic and presentation. |
| Interpretation | The marked optimum is the corrected aerodynamic operating point used in Stage 4 metrics. |
| Limitations | Section-level polar only; does not include full fan radial integration. |

There are 12 figures, one for each flight-section pair.

### Figures: `lift_drag_curves_{flight}.png`

| Field | Description |
|---|---|
| Path pattern | `results/stage4_performance_metrics/figures/lift_drag_curves_takeoff.png`, `climb`, `cruise`, `descent` |
| Generated in | `stage4_performance_metrics/plots.py`, `generate_section_polar_comparison()` |
| Data used | Stage 3 corrected polars for all sections in one condition. |
| Visual content | Two panels: `CL/CD` vs `alpha` and corrected `CL` vs `alpha`, all sections overlaid. |
| Purpose | Section comparison for a given flight condition. |
| Interpretation | Reveals how root, mid-span, and tip differ in efficiency and lift behavior. |
| Limitations | Uses three representative radial sections, not a continuous blade model. |

### Figures: `efficiency_map_{section}.png`

| Field | Description |
|---|---|
| Path pattern | `results/stage4_performance_metrics/figures/efficiency_map_root.png`, `mid_span`, `tip` |
| Generated in | `stage4_performance_metrics/plots.py`, `plot_efficiency_map()` |
| Data used | Corrected efficiency curves interpolated over angle of attack and condition Mach. |
| Visual content | Contour map of `CL/CD` in angle-of-attack vs Mach space, with operating points. |
| Purpose | Envelope visualization and diagnostic. |
| Interpretation | Operating points in higher `CL/CD` regions indicate better aerodynamic efficiency. |
| Limitations | Mach axis uses the discrete flight-condition Mach values, not a dense simulated Mach sweep. |

## Stage 5: Pitch Kinematics and 3D Fan Analysis

### Tables

| Output | Meaning |
|---|---|
| `cascade_corrections.csv` | Section solidity, chord, Weinig factor, Carter deviation, and cascade-adjusted lift. |
| `rotational_corrections.csv` | Snel 3D correction outputs for each condition and section. |
| `rotational_corrections_du_selig.csv` | Du-Selig comparison model outputs. |
| `optimal_incidence.csv` | 3D optimal incidence and `CL/CD` maximum. |
| `pitch_adjustment.csv` | Aerodynamic pitch adjustment relative to cruise. |
| `blade_twist_design.csv` | Cruise blade twist and metal angle by section. |
| `off_design_incidence.csv` | Actual incidence and efficiency loss under a single-actuator compromise. |
| `stage_loading.csv` | Ideal free-pitch stage loading. |
| `stage_loading_single_actuator.csv` | Realistic single-actuator stage loading. |
| `kinematics_analysis.csv` | Velocity triangle and mechanical pitch variables. |

Current detected twist values:

| Section | `beta_metal_deg` | `twist_from_tip_deg` |
|---|---:|---:|
| root | 62.37 | 29.28 |
| mid_span | 45.54 | 12.45 |
| tip | 33.09 | 0.00 |

### Figures

#### `cascade_solidity_profile.png`

| Field | Description |
|---|---|
| Generated in | `stage5_pitch_kinematics/application/run_pitch_kinematics.py`, `_fig_cascade_solidity()` |
| Data used | `CascadeResult` list from `compute_cascade_corrections()`. |
| Visual content | Solidity `sigma` versus blade radius with regime bands. |
| Purpose | Cascade-regime diagnostic. |
| Interpretation | Root has higher solidity and stronger cascade behavior; tip is lower solidity. |
| Limitations | Uses three representative sections only. |

#### `cascade_cl_correction.png`

| Field | Description |
|---|---|
| Generated in | `_fig_cascade_cl_correction()` |
| Data used | Cascade results at cruise design `alpha_opt`. |
| Visual content | Bar comparison of isolated 2D `CL` and cascade-corrected `CL`. |
| Purpose | Cascade correction comparison. |
| Interpretation | Shows the lift reduction or adjustment from Weinig cascade effects. |
| Limitations | Evaluated at selected design points, not across the full polar. |

#### `deviation_angle_carter.png`

| Field | Description |
|---|---|
| Generated in | `_fig_deviation_carter()` |
| Data used | Carter deviation values from cascade results. |
| Visual content | Carter deviation by section and deviation trend versus solidity. |
| Purpose | Cascade-flow deviation diagnostic. |
| Interpretation | Higher solidity changes deviation behavior and affects pitch/twist interpretation. |
| Limitations | Uses Carter empirical rule for NACA 6-series assumptions. |

#### `polars_2d_vs_3d_root.png`

| Field | Description |
|---|---|
| Generated in | `_fig_polars_2d_vs_3d_root()` |
| Data used | Corrected 2D polars and Snel-corrected 3D polar map. |
| Visual content | Root-section `CL/CD` and `CL` curves comparing 2D and 3D. |
| Purpose | 3D rotational correction diagnostic. |
| Interpretation | Root is emphasized because rotational effects are strongest where `c/r` is large. |
| Limitations | Snel is an empirical correction, not a full 3D CFD model. |

#### `snel_correction_spanwise.png`

| Field | Description |
|---|---|
| Generated in | `_fig_snel_correction_spanwise()` |
| Data used | Snel rotational correction results. |
| Visual content | `delta_CL` versus `(c/r)^2` plus `CL` gain percentage by section and condition. |
| Purpose | Validate the expected spanwise trend of rotational lift correction. |
| Interpretation | Larger `(c/r)^2` should produce stronger Snel lift gain. |
| Limitations | Depends on empirical Snel coefficient. |

#### `rotational_model_comparison.png`

| Field | Description |
|---|---|
| Generated in | `_fig_rotational_model_comparison()` |
| Data used | Snel and Du-Selig correction tables. |
| Visual content | Side-by-side comparison of `alpha_opt_3D` and `(CL/CD)_max,3D`. |
| Purpose | Model sensitivity comparison. |
| Interpretation | Differences between Snel and Du-Selig indicate uncertainty in rotational correction. |
| Limitations | Both models are empirical and should be validated for the fan case. |

#### `blade_twist_profile.png`

| Field | Description |
|---|---|
| Generated in | `_fig_blade_twist_profile()` |
| Data used | `blade_twist_design.csv` equivalent data. |
| Visual content | `beta_metal`, `phi_flow`, and `alpha_opt_3D_cruise` versus radius. |
| Purpose | Blade design-twist presentation and diagnostic. |
| Interpretation | Total twist is the root-to-tip change in metal angle at cruise design. |
| Limitations | Based on three radial stations. |

#### `off_design_incidence_heatmap.png`

| Field | Description |
|---|---|
| Generated in | `_fig_off_design_heatmap()` |
| Data used | `off_design_incidence.csv`. |
| Visual content | Heatmaps of actual incidence and incidence compromise relative to optimum. |
| Purpose | Single-actuator trade-off diagnostic. |
| Interpretation | Large deviations show sections that are not perfectly served by a single pitch command. |
| Limitations | Single-actuator assumption may differ from a real VPF mechanism design. |

#### `pitch_compromise_loss.png`

| Field | Description |
|---|---|
| Generated in | `_fig_pitch_compromise_loss()` |
| Data used | `off_design_incidence.csv`. |
| Visual content | Efficiency loss percentage by condition and section, excluding cruise. |
| Purpose | Quantifies off-design penalty from the pitch compromise. |
| Interpretation | Higher bars indicate greater loss from not matching each section's optimum. |
| Limitations | Loss is derived from corrected/3D modeled polars, not experimental fan maps. |

#### `work_distribution.png`

| Field | Description |
|---|---|
| Generated in | `_fig_work_distribution()` |
| Data used | `stage_loading.csv`. |
| Visual content | Specific work `W_specific_kJ_kg` by section and condition. |
| Purpose | Euler work distribution diagnostic. |
| Interpretation | Compares how much work each radial section contributes under ideal VPF operation. |
| Limitations | Section-based approximation only. |

#### `loading_profile_spanwise.png`

| Field | Description |
|---|---|
| Generated in | `_fig_loading_profile_spanwise()` |
| Data used | `stage_loading.csv`. |
| Visual content | Radial profile of work coefficient `psi` for cruise, climb, and takeoff. |
| Purpose | Spanwise loading comparison. |
| Interpretation | Shows whether loading is root-, mid-, or tip-dominated. |
| Limitations | Only three radial stations. |

#### `efficiency_curves_{condition}.png`

| Field | Description |
|---|---|
| Path pattern | `results/stage5_pitch_kinematics/figures/efficiency_curves_takeoff.png`, `climb`, `cruise`, `descent` |
| Generated in | `_fig_efficiency_curves()` |
| Data used | Snel-corrected 3D polar map. |
| Visual content | `CL_3D/CD` versus `alpha` for all sections in one condition. |
| Purpose | 3D efficiency comparison by condition. |
| Interpretation | Star markers identify section-specific 3D optima. |
| Limitations | Depends on cascade and Snel corrections. |

#### `alpha_opt_2d_vs_3d.png`

| Field | Description |
|---|---|
| Generated in | `_fig_alpha_opt_2d_vs_3d()` |
| Data used | `rotational_corrections.csv`. |
| Visual content | Bar comparison of 2D and 3D optimal angle by condition and section. |
| Purpose | Shows how 3D corrections shift operating incidence. |
| Interpretation | Difference between bars indicates the importance of 3D modeling. |
| Limitations | 3D values are empirical corrections. |

#### `alpha_opt_by_condition.png`

| Field | Description |
|---|---|
| Generated in | `_fig_alpha_opt_by_condition()` |
| Data used | Snel rotational correction results. |
| Visual content | `alpha_opt_3D` grouped by condition and section. |
| Purpose | Pitch requirement comparison. |
| Interpretation | Variation across phases motivates variable pitch. |
| Limitations | Uses discrete conditions only. |

#### `pitch_adjustment.png`

| Field | Description |
|---|---|
| Generated in | `_fig_pitch_adjustment()` |
| Data used | `pitch_adjustment.csv`. |
| Visual content | Required `delta_alpha_3D` relative to cruise. |
| Purpose | Actuation requirement diagnostic. |
| Interpretation | Positive or negative bars show required pitch adjustment from cruise reference. |
| Limitations | Aerodynamic adjustment, not necessarily exact actuator command under full mechanism constraints. |

#### `kinematics_comparison.png`

| Field | Description |
|---|---|
| Generated in | `_fig_kinematics_comparison()` |
| Data used | `kinematics_analysis.csv` and pitch adjustments. |
| Visual content | Per-section comparison of aerodynamic `delta_alpha` and mechanical `delta_beta`. |
| Purpose | Links aerodynamic requirement to mechanical pitch command. |
| Interpretation | Differences arise from changing inflow angle and velocity triangle geometry. |
| Limitations | Simplified velocity-triangle model. |

## Stage 6: Reverse-Thrust Mechanism Weight

### Table: `mechanism_weight.csv`

| Metric | Current Value | Meaning |
|---|---:|---|
| `mechanism_weight_kg` | 634.4 | VPF pitch mechanism weight for both engines. |
| `conventional_reverser_weight_kg` | 1586.0 | Conventional cascade reverser equivalent. |
| `weight_saving_vs_conventional_kg` | 951.6 | Weight saved by VPF concept relative to conventional reverser. |
| `sfc_cruise_penalty_pct` | 0.6586 | Penalty relative to no reverser. |
| `sfc_benefit_vs_conventional_pct` | 0.9879 | Benefit relative to conventional reverser. |

### Figure: `mechanism_weight_comparison.png`

| Field | Description |
|---|---|
| Path | `results/stage6_reverse_thrust/figures/mechanism_weight_comparison.png` |
| Generated in | `stage6_reverse_thrust/adapters/filesystem/results_writer.py`, `_plot_weight_comparison()` |
| Data used | `MechanismWeightResult` from `compute_mechanism_weight()`. |
| Visual content | Two panels: reverser-system weight and cruise SFC penalty for no reverser, VPF, and conventional cascade reverser. |
| Purpose | Weight and SFC trade-off presentation. |
| Interpretation | VPF adds weight versus no reverser but saves weight versus a conventional reverser. |
| Limitations | Does not prove reverse-thrust aerodynamic performance; it is a theoretical weight comparison. |

## Stage 7: SFC and Mission Analysis

### Tables

| Output | Meaning |
|---|---|
| `sfc_section_breakdown.csv` | Per-condition and per-section fixed-pitch vs VPF `CL/CD`, epsilon, and profile gain. |
| `sfc_analysis.csv` | Aggregated SFC result per flight condition. |
| `sfc_sensitivity.csv` | Internal Stage 7 sweep over `tau` values. |
| `mission_fuel_burn.csv` | Baseline and VPF fuel burn by mission phase. |
| `ge9x_sfc_parametric.csv` | GE9X parametric sweep over `CL/CD`. |
| `ge9x_sfc_improvement.csv` | Key GE9X sweep points. |
| `ge9x_sfc_improvement.tex` | LaTeX export of key GE9X table. |

Current detected `sfc_analysis.csv` values:

| Condition | Baseline SFC | VPF SFC | Reduction |
|---|---:|---:|---:|
| climb | 0.514500 | 0.492988 | 4.181185% |
| cruise | 0.490000 | 0.490000 | 0.000000% |
| descent | 0.539000 | 0.516463 | 4.181185% |
| takeoff | 0.563500 | 0.557686 | 1.031744% |

Mission fuel saving detected:

| Phase | Fuel Saving kg | CO2 Saving kg | Cost Saving USD |
|---|---:|---:|---:|
| takeoff | 0.5187 | 1.6392 | 0.4669 |
| climb | 57.5828 | 181.9618 | 51.8246 |
| cruise | 0.0000 | 0.0000 | 0.0000 |
| descent | 5.0271 | 15.8856 | 4.5244 |

### Figure: `sfc_improvement_by_condition.png`

| Field | Description |
|---|---|
| Path | `results/stage7_sfc_analysis/figures/sfc_improvement_by_condition.png` |
| Generated in | `stage7_sfc_analysis/application/run_sfc_analysis.py`, `_plot_fixed_vs_vpf_efficiency()` |
| Data used | `SfcSectionResult` values. |
| Visual content | 2x2 subplots comparing fixed-pitch `CL/CD` and VPF `CL/CD` by blade section for each condition. |
| Purpose | SFC source-mechanism explanation. |
| Interpretation | Higher VPF bars indicate aerodynamic efficiency improvement that feeds the SFC model. |
| Limitations | SFC conversion still depends on damping coefficient `tau` and caps. |

### Figure: `fuel_saving_vs_clcd.png`

| Field | Description |
|---|---|
| Path | `results/stage7_sfc_analysis/figures/fuel_saving_vs_clcd.png` |
| Generated in | `stage7_sfc_analysis/engine/ge9x_analysis.py`, `_plot_fuel_saving()` |
| Data used | `ge9x_sfc_parametric.csv`, cruise reference `CL/CD`, and condition optima. |
| Visual content | Fuel saving percentage versus new `CL/CD`, with reference line and condition markers. |
| Purpose | GE9X parametric validation and presentation. |
| Interpretation | Moving right of the reference `CL/CD` increases predicted fuel saving. |
| Limitations | Parametric model uses simplified transfer from aerodynamic efficiency to fuel saving. |

### Figure: `sfc_sensitivity_k_throttle.png`

| Field | Description |
|---|---|
| Path | `results/stage7_sfc_analysis/figures/sfc_sensitivity_k_throttle.png` |
| Generated in | `stage7_sfc_analysis/engine/ge9x_analysis.py`, `_plot_sensitivity()` |
| Data used | GE9X `CL/CD` sweep and several `k_throttle` variants. |
| Visual content | Fuel saving versus `CL/CD` for different part-power SFC sensitivity coefficients. |
| Purpose | Sensitivity analysis. |
| Interpretation | Spread between curves shows uncertainty due to throttle/SFC modeling. |
| Limitations | `k_throttle` values are model parameters, not directly calibrated in this repository. |

## Additional Sensitivity Results

### Table: `sensitivity_table.csv`

Path: `results/sensitivity/sensitivity_table.csv`

Columns:

- `rpm_delta_pct`: fan RPM deviation from design point.
- `tau`: profile efficiency transfer coefficient.
- `sfc_reduction_pct`: mean predicted SFC reduction.

Current detected range: approximately 0.6192% to 3.8462% SFC reduction across the sweep.

### Figure: `sensitivity_heatmap.png`

| Field | Description |
|---|---|
| Path | `results/sensitivity/sensitivity_heatmap.png` |
| Generated in | `run_sensitivity.py` |
| Data used | `sensitivity_table.csv` pivoted by `tau` and RPM deviation. |
| Visual content | Heatmap of `Delta SFC (%)` as a function of `tau` and RPM deviation. |
| Purpose | Sensitivity and uncertainty analysis. |
| Interpretation | Higher cells show parameter regions with stronger predicted SFC reduction. |
| Limitations | Uses existing Stage 3 and Stage 4 data; it does not rerun XFOIL or compressibility corrections for new RPM values. |

## Recommendations for Output Interpretation

1. Start with `finalresults_stage*.txt` to understand whether each stage completed and what headline values were produced.
2. Use Stage 2 plots to inspect raw XFOIL convergence behavior and polar quality.
3. Use Stage 3 plots before trusting corrected metrics, especially at high Mach.
4. Treat Stage 4 `summary_table.csv` as the central aerodynamic performance table.
5. Treat Stage 5 as the bridge from 2D corrected polar behavior to fan-relevant pitch and loading behavior.
6. Treat Stage 6 as a mechanism-weight trade study, not a validated aerodynamic reverse-thrust prediction.
7. Treat Stage 7 SFC numbers as model-based estimates controlled by `tau`, physical caps, and mission assumptions.
8. Archive result sets externally before rerunning the full pipeline.

