"""
sfc_parameters.py
-----------------
Modelos de dominio para el análisis de consumo específico de combustible (SFC).

Modelo físico:
    ε(r, cond)      = CL/CD_vpf / CL/CD_fixed    (Stage 4: max_eff / eff_at_design_alpha)
    ε_eff           = min(ε, EPSILON_CAP)         (cap 3D — Cumpsty 2004 p.280)
    Δη_profile      = (ε_eff − 1) × τ
    η_fan,new       = min(η_base × (1 + Δη_fan), ETA_FAN_ABS_CAP)
    SFC_new         = SFC_base / (1 + k × Δη_applied / η_base)
    k               = BPR / (1 + BPR)             (Saravanamuttoo 2017 §5.14)
"""

from __future__ import annotations

from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# Constantes físicas documentadas
# ---------------------------------------------------------------------------

#: Límite máximo del ratio de mejora CL/CD_VPF / CL/CD_paso_fijo.
#: Valor conservador que cubre los casos físicamente posibles en este modelo
#: (ε ≤ ~2.5 en condiciones extremas de despegue/descenso).
#: El límite operativamente activo es ETA_FAN_DELTA_CAP (4% de mejora absoluta
#: de η_fan), que es mucho más restrictivo en la práctica.
#: El valor anterior de 1.10 procedía de Cumpsty (2004) p.280 pero en ese
#: contexto se refería a la transferencia 2D→3D de η de perfil, no a ε directamente.
EPSILON_CAP: float = 3.0

#: Eficiencia isentrópica de fan máxima (estado del arte tecnología actual).
#: Ref: Cumpsty (2004) ch. 8.
ETA_FAN_ABS_CAP: float = 0.96

#: Mejora absoluta máxima de η_fan atribuible al VPF en condiciones reales.
#: Captura únicamente el mecanismo de perfil (2D CL/CD → fan 3D vía τ).
#: Ref: Cumpsty (2004) p. 280, datos empíricos de fans de paso variable.
ETA_FAN_DELTA_CAP: float = 0.04

# ---------------------------------------------------------------------------
# Mecanismo de mapa del fan (flow coefficient, φ = Va/U)
# ---------------------------------------------------------------------------

#: Coeficiente de pérdida cuadrática de eficiencia de mapa.
#: Δη_map = FAN_MAP_LOSS_COEFFICIENT × ((φ − φ_opt) / φ_opt)²
#:
#: Derivación: la eficiencia de un fan de paso variable en su mapa (fig. φ-ψ)
#: sigue una curva parabólica alrededor del punto de diseño. Un fan de paso fijo
#: se ve forzado a operar en puntos donde φ ≠ φ_opt (diferentes Va entre fases),
#: incurriendo en pérdidas proporcionales al cuadrado de la desviación relativa de φ.
#: VPF ajusta la incidencia de cada pala para recuperar parcialmente esta pérdida.
#:
#: Valor calibrado con recovery fraction ≈ 20% de la pérdida total de mapa
#: (conservador: el resto son pérdidas de endwall y tip clearance irrecuperables).
#: Ref: Cumpsty (2004) ch. 8 (fig. 8.10);
#:      Dickens & Day (2011). "The Design of Highly Loaded Axial Compressors".
#:      J. Turbomach. 133(3):031007.
FAN_MAP_LOSS_COEFFICIENT: float = 0.22

#: Cap del mecanismo de mapa (independiente del mecanismo de perfil).
#: Limita la ganancia atribuible a este mecanismo a un valor físicamente creíble.
#: Ref: Dickens & Day (2011); Cumpsty (2004) ch. 8.
ETA_FAN_MAP_CAP: float = 0.015

#: Cap combinado de ambos mecanismos (perfil + mapa).
#: Corresponde al límite superior del rango literario (ΔSFC ≈ 5%).
#: Ref: Cumpsty (2004) p. 280; Saravanamuttoo et al. (2017) §5.3.
ETA_FAN_COMBINED_CAP: float = 0.048


# ---------------------------------------------------------------------------
# Dominio de parámetros de motor
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class EngineBaseline:
    """Parámetros de motor de referencia para el análisis de SFC."""

    baseline_sfc: float      # SFC de crucero base [lb/(lbf·hr)]
    fan_efficiency: float    # Eficiencia isentrópica de fan base [0–1]
    bypass_ratio: float      # Relación de derivación (bypass ratio)


# ---------------------------------------------------------------------------
# Resultados por condición (nivel de etapa)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SfcAnalysisResult:
    """Resultado del análisis SFC para una condición de vuelo (agregado span-wise)."""

    condition: str
    # Eficiencia aerodinámica media entre secciones
    cl_cd_fixed: float              # CL/CD paso fijo (eff_at_design_alpha, Stage 4) [media]
    cl_cd_vpf: float                # CL/CD VPF (max_efficiency, Stage 4) [media]
    epsilon_mean: float             # ε medio entre secciones [–]
    delta_alpha_mean_deg: float     # Ajuste de pitch medio requerido [°]
    # Eficiencia de fan
    fan_efficiency_baseline: float  # η_fan base [–]
    fan_efficiency_new: float       # η_fan mejorado con VPF [–]
    delta_eta_fan: float            # Δη_fan aplicado (tras caps) [–]
    k_sensitivity: float            # k = BPR/(1+BPR), fracción de empuje del fan [–]
    # SFC
    sfc_baseline: float             # SFC base para esta condición [lb/(lbf·hr)]
    sfc_new: float                  # SFC mejorado con VPF [lb/(lbf·hr)]
    sfc_reduction_percent: float    # Reducción porcentual de SFC [%]
    # Desglose de mecanismos (opcional, NaN si no se calcula)
    delta_eta_profile: float = field(default=float("nan"))   # Δη del mecanismo de perfil [–]
    delta_eta_map: float = field(default=float("nan"))       # Δη del mecanismo de mapa φ [–]
    phi_design: float = field(default=float("nan"))          # φ_diseño = Va_cruise/U_mid [–]
    phi_condition: float = field(default=float("nan"))       # φ en esta condición [–]


# ---------------------------------------------------------------------------
# Resultados por sección (nivel de perfil)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SfcSectionResult:
    """Ratio de mejora por perfil para una sección × condición concreta.

    Compara CL/CD al ángulo de diseño (paso fijo) vs CL/CD óptimo (VPF),
    ambos evaluados a idéntico Mach y Reynolds por XFOIL en Stage 4.
    Incluye también la contribución del mecanismo de mapa del fan (φ-dependiente).
    """

    condition: str
    blade_section: str
    cl_cd_fixed: float          # eff_at_design_alpha (Stage 4) [–]
    cl_cd_vpf: float            # max_efficiency (Stage 4) [–]
    epsilon: float              # cl_cd_vpf / cl_cd_fixed [–]
    epsilon_eff: float          # min(epsilon, EPSILON_CAP) [–]
    delta_eta_profile: float    # (epsilon_eff − 1) × τ [–]
    efficiency_gain_pct: float  # (epsilon − 1) × 100 [%]
    delta_alpha_deg: float      # alpha_opt − alpha_fixed (triángulo de velocidades) [°]
    # Mecanismo de mapa del fan (campos opcionales, NaN si no se calculan)
    phi_condition: float = field(default=float("nan"))   # Va_cond / U_section [–]
    phi_design: float = field(default=float("nan"))      # Va_cruise / U_section [–]
    delta_eta_map: float = field(default=float("nan"))   # k_map × (Δφ/φ)² [–]
    delta_eta_total: float = field(default=float("nan")) # profile + map (antes del cap global) [–]


# ---------------------------------------------------------------------------
# Resultados de sensibilidad a τ
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Resultados de integración de misión
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class MissionFuelBurnResult:
    """Consumo de combustible y ahorro VPF para una fase de vuelo."""

    phase: str
    duration_min: float           # Duración de la fase [min]
    thrust_kN: float              # Empuje en la fase (design_thrust × thrust_fraction) [kN]
    sfc_baseline: float           # SFC sin VPF para esta fase [lb/(lbf·hr)]
    sfc_vpf: float                # SFC con VPF para esta fase [lb/(lbf·hr)]
    fuel_baseline_kg: float       # Combustible quemado sin VPF [kg]
    fuel_vpf_kg: float            # Combustible quemado con VPF [kg]
    fuel_saving_kg: float         # Ahorro de combustible (baseline − vpf) [kg]
    co2_saving_kg: float          # Ahorro en CO₂ (factor CORSIA 3.16 kg CO₂/kg fuel) [kg]
    cost_saving_usd: float        # Ahorro económico [USD]


@dataclass(frozen=True)
class MissionSummary:
    """Resumen agregado del ahorro de combustible en misión completa."""

    total_fuel_baseline_kg: float    # Total combustible sin VPF [kg]
    total_fuel_vpf_kg: float         # Total combustible con VPF [kg]
    total_fuel_saving_kg: float      # Total ahorro [kg]
    total_fuel_saving_pct: float     # Ahorro relativo [%]
    total_co2_saving_kg: float       # Total CO₂ ahorrado [kg]
    total_cost_saving_usd: float     # Total ahorro económico [USD]
    phase_results: list              # List[MissionFuelBurnResult]


@dataclass(frozen=True)
class SfcSensitivityPoint:
    """Un punto del barrido de sensibilidad sobre el coeficiente τ."""

    tau: float               # Coeficiente de transferencia de eficiencia de perfil [–]
    condition: str
    epsilon_mean: float      # ε medio entre secciones [–]
    delta_eta_fan: float     # Δη_fan aplicado (tras caps) [–]
    eta_fan_new: float       # η_fan resultante [–]
    sfc_baseline: float      # SFC base de la condición [lb/(lbf·hr)]
    sfc_new: float           # SFC mejorado [lb/(lbf·hr)]
    sfc_reduction_pct: float # Reducción porcentual [%]
