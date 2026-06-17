"""Diagrama de Marey (malla horaria) e indicadores de operación.

Cada tren es una línea en el plano tiempo (X) vs kilometraje (Y). La pendiente es
proporcional a la velocidad; los cruces indican encuentros entre trenes. Incluye
ambos sentidos de pasajeros y la superposición de trenes de carga (restricción
fija de la operación).
"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

DIR_COLOR = {"CC->CW": "#1f3864", "CW->CC": "#2e7d32"}
DIR_LABEL = {"CC->CW": "Pasajeros Concepción→Coronel", "CW->CC": "Pasajeros Coronel→Concepción"}
FREIGHT_COLOR = {"TRANSAP": "#c0504d", "FEPASA": "#ed7d31"}


def _station_axis(stations: pd.DataFrame):
    s = stations.dropna(subset=["km"]).sort_values("km")
    return s["km"].tolist(), s["station"].tolist()


def marey_figure(trains: pd.DataFrame, stations: pd.DataFrame,
                 periods: list[str] | None = None,
                 directions: list[str] | None = None,
                 freight: pd.DataFrame | None = None) -> go.Figure:
    """Diagrama de Marey con ambos sentidos de pasajeros y carga opcional."""
    km_by = dict(zip(stations["station"], stations["km"]))
    df = trains.copy()
    if periods:
        df = df[df["period"].isin(periods)]
    if directions:
        df = df[df["direction"].isin(directions)]

    fig = go.Figure()
    seen = set()
    for (train, direction), g in df.groupby(["train", "direction"]):
        g = g.sort_values("stop_order")
        xs, ys = [], []
        for _, r in g.iterrows():
            km = r.get("km")
            if pd.isna(km):
                km = km_by.get(r["station"])
            if km is None:
                continue
            xs += [r["arr_s"] / 3600.0, r["dep_s"] / 3600.0]
            ys += [km, km]
        fig.add_trace(go.Scatter(
            x=xs, y=ys, mode="lines",
            line=dict(width=1.1, color=DIR_COLOR.get(direction, "#555")),
            name=DIR_LABEL.get(direction, direction),
            legendgroup=direction, showlegend=direction not in seen,
            hovertext=[f"Tren {train} ({direction})"] * len(xs), hoverinfo="text"))
        seen.add(direction)

    # superposición de carga
    if freight is not None and len(freight):
        for (op, train), g in freight.groupby(["operator", "train"]):
            g = g.sort_values("time_s")
            fig.add_trace(go.Scatter(
                x=(g["time_s"] / 3600.0).tolist(), y=g["km"].tolist(), mode="lines",
                line=dict(width=1.4, color=FREIGHT_COLOR.get(op, "#888"), dash="dash"),
                name=f"Carga {op}", legendgroup=f"f{op}",
                showlegend=f"f{op}" not in seen,
                hovertext=[f"Carga {op} {train}"] * len(g), hoverinfo="text"))
            seen.add(f"f{op}")

    kmvals, kmlabels = _station_axis(stations)
    fig.update_layout(
        title="Diagrama de Marey — Biotren Concepción ↔ Coronel (con carga)",
        xaxis_title="Hora del día", yaxis_title="Kilómetro (desde Concepción)",
        height=720, margin=dict(l=10, r=10, t=50, b=10),
        legend=dict(orientation="h", y=1.03, x=0))
    fig.update_yaxes(tickmode="array", tickvals=kmvals, ticktext=kmlabels,
                     autorange="reversed")
    fig.update_xaxes(tickmode="array", tickvals=list(range(5, 24)),
                     ticktext=[f"{h}:00" for h in range(5, 24)])
    return fig


def kpis(trains: pd.DataFrame, stations: pd.DataFrame) -> dict:
    """Indicadores agnósticos a la dirección (origen = primera parada de cada tren)."""
    def travel_per_dir(d):
        sub = trains[trains["direction"] == d]
        if sub.empty:
            return None
        first = sub.sort_values("stop_order").groupby("train").first()["dep_s"]
        last = sub.sort_values("stop_order").groupby("train").last()["arr_s"]
        tv = ((last - first).dropna()) / 60.0
        return round(float(tv.mean()), 1) if not tv.empty else None

    dirs = sorted(trains["direction"].unique())
    out = {
        "trenes_total": int(trains["train"].nunique()),
        "estaciones": int(len(stations)),
        "tiempo_viaje_min": {"media": travel_per_dir("CC->CW") or
                             (travel_per_dir(dirs[0]) if dirs else None)},
        "por_direccion": {d: {"trenes": int(trains[trains["direction"] == d]["train"].nunique()),
                              "viaje_medio_min": travel_per_dir(d)} for d in dirs},
    }
    return out


def headway_table(trains: pd.DataFrame, stations: pd.DataFrame,
                  direction: str = "CC->CW") -> pd.DataFrame:
    """Salidas desde el origen del sentido dado con su intervalo (headway)."""
    sub = trains[trains["direction"] == direction]
    orig = sub[sub["stop_order"] == 0][["train", "period", "dep_s"]].drop_duplicates()
    g = orig.sort_values("dep_s").reset_index(drop=True)
    g["salida"] = (g["dep_s"] // 3600).astype(int).astype(str) + ":" + \
                  ((g["dep_s"] % 3600) // 60).astype(int).astype(str).str.zfill(2)
    g["headway_min"] = (g["dep_s"].diff() / 60.0).round(1)
    return g[["train", "period", "salida", "headway_min"]]
