"""Generación de escenarios de operación (itinerarios regulares).

Dado el perfil de marcha y dwell de una línea (tabla de estaciones) y una
frecuencia objetivo por período, genera un itinerario regular: salidas
equiespaciadas desde el origen y horario reconstruido en cada estación.

Es la base del optimizador: un itinerario cadenciado (headway constante) es la
solución regular de referencia para objetivos de frecuencia/capacidad y de
robustez (los intervalos parejos absorben mejor las perturbaciones).
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass
class PeriodSpec:
    """Definición de un período de operación."""
    name: str
    start_h: float          # hora de la primera salida (ej. 6.0 = 06:00)
    end_h: float            # hora límite de salidas (no se generan después)
    headway_min: float      # intervalo entre salidas, en minutos


def _reconstruct(dep_s: int, stations: pd.DataFrame) -> list[dict]:
    """Reconstruye el paso por cada estación desde una salida de origen (seg)."""
    st = stations.sort_values("order")
    rows = []
    t = dep_s
    last = len(st) - 1
    for i, r in enumerate(st.itertuples(index=False)):
        if i > 0:
            t += int(r.seg_time_s)
        arr = t
        t += int(r.dwell_s)
        rows.append({
            "station": r.station, "arr_s": arr, "dep_s": t, "stop_order": i,
            "arr": _hhmm(arr), "dep": _hhmm(t) if i < last else "",
        })
    return rows


def _hhmm(sec: float) -> str:
    sec = int(round(sec))
    return f"{sec // 3600}:{(sec % 3600) // 60:02d}"


def generate_timetable(stations: pd.DataFrame, periods: list[PeriodSpec],
                       direction: str = "CC->CW") -> pd.DataFrame:
    """Genera el itinerario regular (formato largo, igual que el parseado)."""
    records = []
    n = 0
    for p in periods:
        if p.headway_min <= 0:
            continue
        t = int(p.start_h * 3600)
        end = int(p.end_h * 3600)
        step = int(p.headway_min * 60)
        while t <= end:
            n += 1
            train = f"S{n:03d}"
            for row in _reconstruct(t, stations):
                records.append({
                    "train": train, "period": p.name, "direction": direction,
                    **row,
                })
            t += step
    return pd.DataFrame(records)


def fleet_estimate(travel_min: float, headway_min: float,
                   turnaround_min: float = 10.0) -> int:
    """Trenes necesarios para sostener un headway (cadencia) dado.

    Tiempo de ciclo = 2 x viaje + 2 x vuelta. Flota = ceil(ciclo / headway).
    """
    if headway_min <= 0:
        return 0
    cycle = 2 * travel_min + 2 * turnaround_min
    import math
    return math.ceil(cycle / headway_min)


def compare_kpis(current: pd.DataFrame, scenario: pd.DataFrame,
                 stations: pd.DataFrame) -> pd.DataFrame:
    """Tabla comparativa de KPIs entre operación actual y escenario."""
    from .marey import kpis

    def flatten(tt, label):
        k = kpis(tt, stations)
        return {
            "escenario": label,
            "trenes": k["trenes_total"],
            "tiempo_viaje_min": k["tiempo_viaje_min"]["media"],
        }

    rows = [flatten(current, "Actual"), flatten(scenario, "Escenario")]
    return pd.DataFrame(rows)
