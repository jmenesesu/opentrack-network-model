"""Diagrama de Marey (malla horaria) e indicadores de operación.

El diagrama de Marey representa cada tren como una línea en el plano tiempo (eje X)
vs posición a lo largo de la línea (eje Y). La pendiente de la línea es proporcional
a la velocidad; las líneas paralelas indican servicios homogéneos y los cruces,
encuentros entre trenes.
"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

PERIOD_COLORS = {
    "Punta Mañana / Valle": "#1f3864",
    "Punta Tarde": "#c0504d",
    "Sábado": "#548235",
    "Domingo": "#7f6000",
    "s/d": "#808080",
}


def _to_min(series_s: pd.Series) -> pd.Series:
    return series_s / 60.0


def marey_figure(trains: pd.DataFrame, stations: pd.DataFrame,
                 periods: list[str] | None = None) -> go.Figure:
    """Construye el diagrama de Marey.

    trains: formato largo (train, station, arr_s, dep_s, period, stop_order).
    stations: secuencia con cum_pos_min (posición en el eje Y).
    """
    pos = dict(zip(stations["station"], stations["cum_pos_min"]))
    order = dict(zip(stations["station"], stations["order"]))

    df = trains.copy()
    if periods:
        df = df[df["period"].isin(periods)]

    fig = go.Figure()
    seen_periods = set()
    for train, g in df.groupby("train"):
        g = g.assign(_o=g["station"].map(order)).sort_values("_o")
        period = g["period"].iloc[0]
        # secuencia tiempo-posición: usar llegada y salida en cada estación
        xs, ys = [], []
        for _, r in g.iterrows():
            p = pos.get(r["station"])
            if p is None:
                continue
            xs.append(r["arr_s"] / 3600.0)
            ys.append(p)
            xs.append(r["dep_s"] / 3600.0)
            ys.append(p)
        fig.add_trace(go.Scatter(
            x=xs, y=ys, mode="lines",
            line=dict(width=1.2, color=PERIOD_COLORS.get(period, "#808080")),
            name=period if period not in seen_periods else None,
            legendgroup=period,
            showlegend=period not in seen_periods,
            hovertext=[f"Tren {train}<br>{period}"] * len(xs),
            hoverinfo="text",
        ))
        seen_periods.add(period)

    # eje Y: estaciones en su posición acumulada
    fig.update_layout(
        title="Diagrama de Marey — Biotren Concepción → Coronel",
        xaxis_title="Hora del día", yaxis_title="Estación (posición acumulada)",
        height=700, margin=dict(l=10, r=10, t=50, b=10),
        legend=dict(orientation="h", y=1.02, x=0),
    )
    fig.update_yaxes(
        tickmode="array",
        tickvals=stations["cum_pos_min"].tolist(),
        ticktext=stations["station"].tolist(),
        autorange="reversed",  # origen arriba, terminal abajo
    )
    fig.update_xaxes(
        tickmode="array",
        tickvals=list(range(5, 24)),
        ticktext=[f"{h}:00" for h in range(5, 24)],
    )
    return fig


def kpis(trains: pd.DataFrame, stations: pd.DataFrame) -> dict:
    """Indicadores de la operación a partir del itinerario reconstruido."""
    origin = stations.iloc[0]["station"]
    terminal = stations.iloc[-1]["station"]

    dep_origin = (trains[trains["station"] == origin]
                  .groupby("train")["dep_s"].min())
    arr_term = (trains[trains["station"] == terminal]
                .groupby("train")["arr_s"].min())
    travel = (arr_term - dep_origin).dropna() / 60.0

    out = {
        "trenes_total": int(trains["train"].nunique()),
        "tiempo_viaje_min": {
            "min": round(float(travel.min()), 1) if not travel.empty else None,
            "max": round(float(travel.max()), 1) if not travel.empty else None,
            "media": round(float(travel.mean()), 1) if not travel.empty else None,
        },
        "estaciones": int(len(stations)),
    }

    # trenes por período y headway medio por período (intervalo entre salidas)
    by_period = {}
    for period, g in trains.groupby("period"):
        deps = sorted(g[g["station"] == origin]["dep_s"].unique())
        headways = [(b - a) / 60.0 for a, b in zip(deps, deps[1:])]
        by_period[period] = {
            "trenes": int(g["train"].nunique()),
            "headway_medio_min": round(sum(headways) / len(headways), 1) if headways else None,
        }
    out["por_periodo"] = by_period
    return out


def headway_table(trains: pd.DataFrame, stations: pd.DataFrame) -> pd.DataFrame:
    """Tabla de salidas desde el origen con su intervalo (headway) en minutos."""
    origin = stations.iloc[0]["station"]
    g = (trains[trains["station"] == origin][["train", "period", "dep_s"]]
         .drop_duplicates().sort_values("dep_s").reset_index(drop=True))
    g["salida"] = (g["dep_s"] // 3600).astype(int).astype(str) + ":" + \
                  ((g["dep_s"] % 3600) // 60).astype(int).astype(str).str.zfill(2)
    g["headway_min"] = (g["dep_s"].diff() / 60.0).round(1)
    return g[["train", "period", "salida", "headway_min"]]
