"""
stage5_pitch_kinematics
-----------------------
Análisis integrado de incidencia óptima, ajuste de paso aerodinámico y
cinemática de triángulos de velocidad.

Fusión de los anteriores Stage 6 (VPF Analysis) y Stage 7 (Kinematics Analysis):
  - Calcula α_opt por condición/sección (desde polares de Stage 2/3)
  - Calcula Δα relativo a crucero (ajuste de paso aerodinámico)
  - Convierte Δα en Δβ_mech mediante triángulos de velocidad
  - Exporta tablas y figuras a results/stage5_pitch_kinematics/
"""
