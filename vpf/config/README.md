# Configuration Reference

This document explains the physical basis of every parameter in `analysis_config.yaml`
and `engine_parameters.yaml`. Values are cross-referenced with the GE9X-105B1A
(Boeing 777X) public data and ISA atmosphere.

---

## Fan geometry (`fan_geometry`)

### RPM schedule

The GE9X N1 shaft runs at a maximum of **2355 RPM** at full takeoff thrust (100 % N1).
The pipeline models four operating points along the N1 curve:

| Condition | N1 [RPM] | % N1 | Basis |
|-----------|---------|------|-------|
| Takeoff   | 2355    | 100  | Maximum certified thrust |
| Climb     | 2200    | 93   | Typical climb power |
| Cruise    | 2050    | 87   | Design aerodynamic point |
| Descent   | 2000    | 85   | Flight-idle approach |

A single RPM across all conditions (as commonly assumed in academic studies) introduces
errors of up to 15 % in the blade tangential speed at takeoff vs cruise, directly
propagating to Reynolds number, flow angle and stage loading.

### Blade radii

Hub-to-tip ratio ≈ 0.31, consistent with GE9X design publications:

| Section  | Radius [m] | Notes |
|----------|------------|-------|
| Root     | 0.53       | Hub shoulder |
| Mid-span | 1.00       | Representative mean-line section |
| Tip      | 1.70       | Fan diameter = 2 × 1.70 = **3.40 m** (= 134 in) |

### Axial velocities (fan-face)

Axial velocity `Va` at the fan face is **not** the aircraft flight speed. It is derived
from the fan-face Mach number at each operating point:

| Condition | Altitude | a [m/s] | M_fan | Va [m/s] |
|-----------|----------|---------|-------|----------|
| Takeoff   | SL       | 340     | 0.53  | 180      |
| Climb     | FL150    | 322     | 0.48  | 155      |
| Cruise    | FL350    | 295     | 0.51  | 150      |
| Descent   | FL100    | 328     | 0.38  | 125      |

---

## Reynolds numbers (`reynolds`)

**Formula:** `Re = ρ · W_rel · c / μ`

where `W_rel = √(Va² + U²)` is the relative velocity at each blade section
and `U = ω · r` is the blade tangential speed.

ISA atmosphere per altitude:

| Condition | Alt [m] | ρ [kg/m³] | μ [Pa·s] |
|-----------|---------|-----------|---------|
| Takeoff   | 0       | 1.225     | 1.81e-5 |
| Climb     | 4575    | 0.769     | 1.63e-5 |
| Cruise    | 10668   | 0.364     | 1.42e-5 |
| Descent   | 3048    | 0.909     | 1.68e-5 |

### Resulting Reynolds table

| Condition | Section  | U [m/s] | W_rel [m/s] | c [m] | Re     |
|-----------|----------|---------|-------------|-------|--------|
| Takeoff   | Root     | 130.7   | 222         | 0.36  | 5.4e6  |
| Takeoff   | Mid-span | 246.7   | 305         | 0.46  | 9.5e6  |
| Takeoff   | Tip      | 419.4   | 456         | 0.46  | 14.2e6 |
| Climb     | Root     | 122.1   | 197         | 0.36  | 3.4e6  |
| Climb     | Mid-span | 230.4   | 278         | 0.46  | 6.0e6  |
| Climb     | Tip      | 391.7   | 421         | 0.46  | 9.1e6  |
| Cruise    | Root     | 113.8   | 188         | 0.36  | 1.7e6  |
| Cruise    | Mid-span | 214.7   | 262         | 0.46  | 3.1e6  |
| Cruise    | Tip      | 365.0   | 395         | 0.46  | 4.7e6  |
| Descent   | Root     | 110.9   | 167         | 0.36  | 3.3e6  |
| Descent   | Mid-span | 209.4   | 244         | 0.46  | 6.1e6  |
| Descent   | Tip      | 356.0   | 377         | 0.46  | 9.4e6  |

These values are consistent with published estimates for large turbofan wide-chord fans
(cruise mid-span Re ~ 3–4 × 10⁶, takeoff tip Re ~ 12–15 × 10⁶).

---

## Target Mach numbers (`target_mach`)

`M_rel = W_rel / a` evaluated at **mid-span** — the physically relevant Mach number
for 2D compressibility corrections on a rotating blade section.

| Condition | W_mid [m/s] | a [m/s] | M_rel |
|-----------|------------|---------|-------|
| Takeoff   | 305        | 340     | 0.90  |
| Climb     | 278        | 322     | 0.86  |
| Cruise    | 262        | 295     | **0.89** |
| Descent   | 244        | 328     | 0.74  |

Note: cruise M_rel = 0.89 is below the typical drag-rise Mach for NACA 6-series profiles
(M_dd ≈ 0.90–0.92 at design CL), meaning wave-drag correction is mild at the design point.
Stage 3 applies Kármán–Tsien correction fully; Korn wave-drag term activates only when
`M > M_dd`.

---

## Ncrit (`ncrit`)

Ncrit controls the laminar-to-turbulent transition criterion in XFOIL's e^N method.

**Formula:** `Ncrit = −8.43 − 2.4 · ln(Tu)`

| Tu [%] | Ncrit | Environment |
|--------|-------|-------------|
| 0.1    | 11.0  | Free flight (clean) |
| 0.5    | 4.3   | Turbofan fan inlet |
| 1.0    | 2.6   | Wind tunnel (high Tu) |

All conditions use **Ncrit = 4.0**, corresponding to Tu ≈ 0.5 %, representative of
turbofan fan-face inflow with inlet distortion. Previous values of 5–6 (clean
wind-tunnel) over-estimated laminar run length and yielded non-physical CL/CD peaks.

Reference: Mack (1977); Drela & Youngren, XFOIL 6.9 documentation §4.

---

## Blade geometry (`blade_geometry`)

### Chord and solidity

Chord is a fixed geometric dimension (GE9X wide-chord composite blades).
Solidity `σ = c · Z / (2π · r)` is the primary cascade parameter:

| Section  | c [m] | r [m] | Z  | σ    |
|----------|-------|-------|----|------|
| Root     | 0.36  | 0.53  | 16 | 1.73 |
| Mid-span | 0.46  | 1.00  | 16 | 1.16 |
| Tip      | 0.46  | 1.70  | 16 | 0.69 |

Chord can be recovered at any section as: `c = σ · 2π · r / Z`.

### Camber angle

`theta_camber_deg = 8.0°` corresponds to a NACA 65-410 profile (10 % thick, design
lift coefficient 0.4). Used in Carter's cascade deviation rule:

`δ = m · θ / √σ`   where `m = 0.23` for NACA 6-series (Carter 1950).

---

## Airfoil geometry (`airfoil_geometry`)

Used exclusively in Stage 3 (compressibility corrections):

| Parameter | Value | Role |
|-----------|-------|------|
| `thickness_ratio` | 0.10 | t/c for NACA 65-410 |
| `korn_kappa` | 0.87 | Korn factor κ for NACA 6-series (conventional camber) |

Drag-divergence Mach: `M_dd ≈ κ/cos(Λ) − (t/c)/cos²(Λ) − CL/(10·cos³(Λ))`

For Λ = 0 (2D section), `M_dd ≈ 0.87 − 0.10 − CL/10`.
At design CL ≈ 0.4: `M_dd ≈ 0.73`. At lower cruise CL ≈ 0.2: `M_dd ≈ 0.75`.

---

## Alpha sweep (`alpha`)

| Parameter | Value | Notes |
|-----------|-------|-------|
| `min`     | −5.0° | Below zero-lift; captures negative-incidence reverse-thrust region |
| `max`     | 18.0° | Covers the realistic fan incidence range and captures NACA 6-series stall without forcing deep post-stall XFOIL points |
| `step`    | 0.15° | Resolution for peak search accuracy |

Stage 1 (airfoil selection) uses a narrower range: −2° to 18°, focused on the
operational incidence window.

---

## XFOIL settings (`xfoil`)

| Parameter | Value | Notes |
|-----------|-------|-------|
| `iter` | 200 | Max viscous iterations per α point (XFOIL `ITER` command) |
| `timeout_final_s` | 180.0 | Subprocess timeout for Stage 2 (12 long polars) |
| `timeout_selection_s` | 60.0 | Timeout for Stage 1 (single Re, short range) |
| `max_retries` | 3 | Retries on timeout or non-zero exit |
| `retry_wait_s` | 1.0 | Pause between retries |

---

## Engine parameters (`engine_parameters.yaml`)

| Parameter | Symbol | Value | Notes |
|-----------|--------|-------|-------|
| `baseline_sfc` | SFC₀ | 0.49 lb/(lbf·h) | GE9X-105B1A cruise SFC |
| `fan_efficiency` | η_fan | 0.90 | Polytropic fan efficiency |
| `bypass_ratio` | BPR | 15.0 | UHBPR target architecture |
| `profile_efficiency_transfer` | τ | 0.08 | Fraction of 2D gain reaching 3D fan η |

### τ — profile efficiency transfer coefficient

τ damps ideal 2D aerodynamic gains to account for 3D losses not modelled in
isolated-section XFOIL analysis. τ = 1.0 would imply perfect transfer; τ = 0.0
means no benefit reaches the engine.

The value τ = 0.08 is derived for UHBPR (BPR=15, FPR=1.30, h/t ≈ 0.28) by
applying multiplicative penalty factors to the Cumpsty (2004) §4.3.2 conventional
turbofan baseline (τ ≈ 0.35): transonic tip shock factor × 0.45 (Gunn & Hall,
GT2014-26698), low-h/t secondary flows × 0.55 (Koch & Smith 1976), tip clearance
and endwall boundary layer × 0.75 (Denton 1993; Smith 1970) → ≈ 0.065, rounded
up to 0.08 as a conservative safety margin. The sensitivity sweep covers
τ ∈ [0.05, 0.65] to bound the uncertainty range.
