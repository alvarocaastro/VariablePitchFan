# Stage 5 README - Pitch Kinematics and 3D Fan Analysis

## Purpose of This Stage

Stage 5 extends the 2D corrected polar analysis toward fan-relevant 3D behavior. It adds cascade effects, rotational lift corrections, 3D optimum incidence, pitch kinematics, blade twist, single-actuator compromise, and stage loading.

This stage answers: **how do the corrected 2D airfoil results translate into blade pitch, twist, radial loading, and 3D fan-section behavior?**

## Inputs

| Input | Path | Description |
|---|---|---|
| Stage 2 raw polars | `results/stage2_xfoil_simulations/polars/` | Used where raw 2D data are needed. |
| Stage 3 corrected polars | `results/stage3_compressibility_correction/` | Preferred working polars for 3D analysis. |
| Fan geometry | `config/analysis_config.yaml` | Radii, RPM, axial velocity. |
| Blade geometry | `config/analysis_config.yaml` | Blade count, solidity, camber angle. |

## Code Location

| File | Responsibility |
|---|---|
| `src/vpf_analysis/stage5_pitch_kinematics/pitch_kinematics_core.py` | Core calculations. |
| `src/vpf_analysis/stage5_pitch_kinematics/application/run_pitch_kinematics.py` | Stage 5 orchestration, figures, tables, summaries. |
| `src/vpf_analysis/stage5_pitch_kinematics/adapters/filesystem/data_loader.py` | Loads Stage 2 and Stage 3 data. |
| `src/vpf_analysis/stage5_pitch_kinematics/adapters/filesystem/results_writer.py` | Writes selected Stage 5 tables and summaries. |

## Method

Stage 5 performs:

1. Load raw and corrected aerodynamic polars.
2. Compute cascade corrections using Weinig and Carter logic.
3. Apply Weinig-corrected lift to working polars.
4. Compute 3D rotational corrections using Du-Selig (primary).
5. Compute Snel correction for comparison.
6. Build 3D polar maps.
7. Compute 3D optimum incidence and `CL/CD`.
8. Compute pitch adjustment relative to cruise.
9. Solve velocity triangles.
10. Compute cruise blade twist.
11. Compute off-design incidence under a single-actuator compromise.
12. Compute ideal and single-actuator stage loading.
13. Write tables, figures, and summaries.

## Outputs

| Output | Meaning |
|---|---|
| `cascade_corrections.csv` | Solidity, chord, Weinig factor, Carter deviation, cascade lift. |
| `rotational_corrections.csv` | Snel correction per condition-section case. |
| `rotational_corrections_du_selig.csv` | Alternative Du-Selig correction comparison. |
| `optimal_incidence.csv` | 3D optimum incidence and maximum 3D `CL/CD`. |
| `pitch_adjustment.csv` | Pitch adjustment relative to cruise. |
| `blade_twist_design.csv` | Cruise twist and metal angle. |
| `off_design_incidence.csv` | Actual incidence and loss under single-actuator compromise. |
| `stage_loading.csv` | Ideal stage loading. |
| `stage_loading_single_actuator.csv` | Single-actuator stage loading. |
| `kinematics_analysis.csv` | Full velocity triangle kinematics. |
| PNG figures | `results/stage5_pitch_kinematics/figures/` |

## Current Key Results

### Cascade Corrections

| Section | Solidity | `K_weinig` | Carter Deviation | `CL_2D` at Opt | `CL_cascade` at Opt |
|---|---:|---:|---:|---:|---:|
| root | 1.730 | 0.792 | 1.399 deg | 1.207 | 0.957 |
| mid_span | 1.160 | 0.861 | 1.708 deg | 1.322 | 1.138 |
| tip | 0.690 | 0.917 | 2.215 deg | 1.383 | 1.269 |

### Cruise Twist

| Section | `alpha_opt_3D_cruise` | `beta_metal_deg` | `twist_from_tip_deg` |
|---|---:|---:|---:|
| root | 9.55 deg | 62.37 deg | 29.28 deg |
| mid_span | 10.60 deg | 45.54 deg | 12.45 deg |
| tip | 10.75 deg | 33.09 deg | 0.00 deg |

### 3D Rotational Correction Highlights

| Condition | Section | `CL/CD` 2D | `CL/CD` 3D | `CL_gain_pct` |
|---|---|---:|---:|---:|
| cruise | root | 38.655 | 59.624 | 138.46% |
| cruise | mid_span | 41.461 | 48.910 | 62.25% |
| cruise | tip | 43.218 | 41.216 | 22.03% |
| descent | root | 116.288 | 183.163 | 138.46% |
| descent | mid_span | 129.512 | 151.908 | 62.25% |
| descent | tip | 139.273 | 131.111 | 22.03% |

The root section receives the strongest modeled rotational lift correction because `c/r` is largest there.

## Figure Interpretation

### `cascade_cl_correction.png`

Compares isolated 2D `CL` with cascade-corrected `CL`.

It demonstrates:

- how Weinig correction changes lift at the design point;
- which sections lose more lift in cascade.

### `deviation_angle_carter.png`

Shows Carter deviation by section and deviation versus solidity.

It demonstrates:

- expected deviation trend from the empirical Carter rule;
- impact of solidity on flow turning interpretation.

### `polars_2d_vs_3d_root.png`

Compares 2D and 3D-corrected root-section polars.

It demonstrates:

- why root rotational correction matters;
- how 3D correction shifts `CL` and `CL/CD`.

### `snel_correction_spanwise.png`

Shows Snel lift increment versus `(c/r)^2` and gain by condition-section.

It demonstrates:

- spanwise dependence of rotational correction;
- root-dominant lift gain.

### `rotational_model_comparison.png`

Compares Snel and Du-Selig results.

It demonstrates:

- model sensitivity in `alpha_opt_3D` and maximum 3D `CL/CD`;
- uncertainty in empirical rotational correction choice.

### `blade_twist_profile.png`

Shows cruise `beta_metal`, inflow angle `phi`, and `alpha_opt_3D` versus radius.

It demonstrates:

- required blade twist from root to tip;
- how flow angle dominates root pitch angle.

### `off_design_incidence_heatmap.png`

Shows actual incidence and incidence compromise across section-condition pairs.

It demonstrates:

- where a single actuator cannot perfectly match every radial section;
- which sections/conditions carry off-design incidence penalties.

### `pitch_compromise_loss.png`

Shows efficiency loss from the single-actuator compromise.

It demonstrates:

- which non-cruise cases lose most efficiency due to shared pitch command;
- whether compromise loss is small or design-critical.

### `loading_profile_spanwise.png`

Shows radial work coefficient profile.

It demonstrates:

- whether loading is root-, mid-, or tip-heavy;
- how takeoff, climb, and cruise compare.

### `efficiency_curves_{condition}.png`

Shows 3D-corrected `CL/CD` curves by section for one flight condition.

It demonstrates:

- 3D optimum operating points;
- section-level efficiency after cascade and rotational effects.

### `alpha_opt_2d_vs_3d.png`

Compares 2D and 3D optimum incidence.

It demonstrates:

- how much the 3D corrections shift the chosen incidence.

### `alpha_opt_by_condition.png`

Shows 3D optimum incidence across conditions and sections.

It demonstrates:

- the VPF pitch requirement after 3D corrections.

### `pitch_adjustment.png`

Shows required pitch adjustment relative to cruise.

It demonstrates:

- how much pitch movement is needed by phase and section.

### `kinematics_comparison.png`

Compares aerodynamic and mechanical pitch adjustment.

It demonstrates:

- how velocity-triangle effects translate aerodynamic incidence needs into mechanical blade pitch motion.

## Important Considerations

- Stage 5 is where the analysis moves beyond isolated 2D airfoil behavior.
- Snel and Du-Selig corrections are empirical and should be treated as model estimates.
- Current analysis uses three representative radial sections.
- The single-actuator model is a simplification of real VPF mechanical architecture.

## Model Restrictions

| Restriction | Meaning |
|---|---|
| Empirical 3D corrections | Snel and Du-Selig are not equivalent to CFD or rig data. |
| Simplified cascade model | Weinig and Carter provide engineering approximations. |
| Three radial stations | No continuous radial integration. |
| Simplified actuator model | Real mechanisms may have structural, control, and nonlinear limits. |
| Stage loading reference zone | The fixed-pitch design zone is diagnostic, not an absolute pass/fail criterion. |

## Downstream Role

Stage 5 outputs are used by Stage 7 to improve SFC calculations with kinematic and 3D context.

