"""
stage7_sfc_analysis
-------------------
Estima la reducción de consumo específico de combustible (SFC) derivada de
las mejoras aerodinámicas que permite el fan de paso variable (VPF).

Modelo:
    η_fan,new = η_base · [1 + τ · ((CL/CD)_VPF / (CL/CD)_base − 1)]
    SFC_new   = SFC_base / (1 + Δη_fan / η_base)

donde τ = profile_efficiency_transfer (factor de amortiguamiento, actualmente 0.08)
que recoge las pérdidas 3D (choques transónicos en punta, flujos secundarios, huelgo en punta).
Derivado bibliográficamente: Cumpsty (2004) × Gunn-Hall (2014) × Koch-Smith (1976) × Denton (1993).

"""
