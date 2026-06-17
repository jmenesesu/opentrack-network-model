"""Tiempo de marcha por arista (cota inferior en marcha libre).

El tiempo se calcula como ``largo / velocidad_máxima`` y representa una **cota
inferior**: ignora aceleración, frenado, paradas y restricciones de señalización.
Sirve para comparar escenarios y como semilla del optimizador; los tiempos finos
deben obtenerse de la simulación de OpenTrack (.otsimcor).

OpenTrack exporta 4 velocidades por sentido (categorías de tren / pendulación). Por
defecto usamos la primera de cada sentido (``speed_1_1`` ascendente, ``speed_2_1``
descendente), que corresponde a la velocidad base.
"""

from __future__ import annotations

import pandas as pd

KMH_TO_MS = 1.0 / 3.6


def free_run_time(length_m: float, speed_kmh: float) -> float:
    """Tiempo en segundos para recorrer ``length_m`` a velocidad constante."""
    if not speed_kmh or speed_kmh <= 0:
        return float("nan")
    return length_m / (speed_kmh * KMH_TO_MS)


def add_running_times(
    metrolinx: pd.DataFrame,
    speed_up: str = "speed_1_1",
    speed_down: str = "speed_2_1",
) -> pd.DataFrame:
    """Agrega columnas de tiempo de marcha por sentido a las aristas Metrolinx.

    Devuelve una copia con ``t_up_s`` y ``t_down_s`` (segundos).
    """
    df = metrolinx.copy()
    df["t_up_s"] = df.apply(
        lambda r: free_run_time(r["length"], r[speed_up]), axis=1
    )
    df["t_down_s"] = df.apply(
        lambda r: free_run_time(r["length"], r[speed_down]), axis=1
    )
    return df


def running_time_by_document(metrolinx_with_times: pd.DataFrame) -> pd.DataFrame:
    """Resumen de largo y tiempo de marcha libre agregado por documento/corredor."""
    g = metrolinx_with_times.groupby("document")
    out = g.agg(
        n_edges=("edge_id", "count"),
        length_km=("length", lambda s: round(s.sum() / 1000.0, 3)),
        t_up_min=("t_up_s", lambda s: round(s.sum() / 60.0, 2)),
        t_down_min=("t_down_s", lambda s: round(s.sum() / 60.0, 2)),
    ).reset_index()
    return out.sort_values("length_km", ascending=False).reset_index(drop=True)
