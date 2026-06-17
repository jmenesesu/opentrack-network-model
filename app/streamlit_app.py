"""App Streamlit — caracterización de la red y operación Biotren (EFE Sur).

Pestañas:
- Red: grafo macroscópico, estaciones, corredores (desde exportaciones OpenTrack).
- Itinerario (Marey): malla horaria reconstruida del Biotren Concepción–Coronel
  e indicadores de operación.

Ejecutar:  streamlit run app/streamlit_app.py
"""

from __future__ import annotations

import os
import sys

import networkx as nx
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from otnet.parsers import load_all                       # noqa: E402
from otnet.network import (                               # noqa: E402
    build_macroscopic_graph, network_summary, degree_table,
)
from otnet.running_time import add_running_times, running_time_by_document  # noqa: E402
from otnet.marey import marey_figure, kpis, headway_table  # noqa: E402

BASE = os.path.join(os.path.dirname(__file__), "..")
DEFAULT_DATA_DIR = os.path.join(BASE, "data", "raw")
DATA_DIR = os.path.join(BASE, "data")

st.set_page_config(page_title="Red y operación — EFE Sur", layout="wide")


@st.cache_data(show_spinner=False)
def load_network(data_dir: str):
    netvisio, metrolinx = load_all(data_dir)
    macro = build_macroscopic_graph(netvisio)
    summary = network_summary(netvisio, metrolinx, macro)
    return netvisio, metrolinx, macro, summary


@st.cache_data(show_spinner=False)
def load_timetable():
    tt = pd.read_csv(os.path.join(DATA_DIR, "timetable_cc_coronel.csv"))
    st_ = pd.read_csv(os.path.join(DATA_DIR, "stations_cc_coronel.csv"))
    return tt, st_


def network_graph_figure(macro: nx.Graph) -> go.Figure:
    pos = nx.spring_layout(macro, seed=42, k=0.6, iterations=200)
    ex, ey = [], []
    for u, v in macro.edges():
        ex += [pos[u][0], pos[v][0], None]
        ey += [pos[u][1], pos[v][1], None]
    edge = go.Scatter(x=ex, y=ey, mode="lines",
                      line=dict(width=1, color="#9aa0a6"), hoverinfo="none")
    tracks = [macro.nodes[n].get("n_tracks") or 1 for n in macro.nodes()]
    node = go.Scatter(
        x=[pos[n][0] for n in macro.nodes()], y=[pos[n][1] for n in macro.nodes()],
        mode="markers+text", text=list(macro.nodes()), textposition="top center",
        textfont=dict(size=9),
        marker=dict(size=[8 + 2 * t for t in tracks], color=tracks,
                    colorscale="Blues", showscale=True,
                    colorbar=dict(title="Nº vías"), line=dict(width=1, color="#1f3864")),
        hovertext=[f"{n} — {macro.nodes[n].get('name')}<br>Vías: {macro.nodes[n].get('n_tracks')}"
                   for n in macro.nodes()], hoverinfo="text")
    fig = go.Figure([edge, node])
    fig.update_layout(showlegend=False, margin=dict(l=0, r=0, t=10, b=0), height=600,
                      xaxis=dict(visible=False), yaxis=dict(visible=False))
    return fig


st.title("Red y operación ferroviaria — EFE Sur")

tab_red, tab_marey = st.tabs(["Red (infraestructura)", "Itinerario Biotren (Marey)"])

# --------------------------------------------------------------------------- #
# Pestaña RED
# --------------------------------------------------------------------------- #
with tab_red:
    data_dir = st.text_input("Directorio de datos", value=DEFAULT_DATA_DIR)
    try:
        netvisio, metrolinx, macro, summary = load_network(data_dir)
    except FileNotFoundError as exc:
        st.error(f"No se pudieron cargar los datos: {exc}")
        st.stop()

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Estaciones", summary["macro_estaciones"])
    c2.metric("Conexiones", summary["macro_conexiones"])
    c3.metric("Corredores", summary["micro_corredores"])
    c4.metric("Largo total (km)", summary["largo_total_km"])

    if summary["componentes_conexas"] > 1:
        st.warning(f"La red tiene {summary['componentes_conexas']} componentes "
                   f"desconectadas. Estaciones aisladas: "
                   f"{summary['estaciones_aisladas'] or 'ninguna'}")
    else:
        st.success("La red macroscópica está completamente conectada.")

    sub1, sub2, sub3 = st.tabs(["Grafo", "Estaciones", "Corredores"])
    with sub1:
        st.plotly_chart(network_graph_figure(macro), use_container_width=True)
    with sub2:
        st.dataframe(degree_table(macro), use_container_width=True, hide_index=True)
    with sub3:
        st.dataframe(running_time_by_document(add_running_times(metrolinx)),
                     use_container_width=True, hide_index=True)

# --------------------------------------------------------------------------- #
# Pestaña MAREY
# --------------------------------------------------------------------------- #
with tab_marey:
    try:
        tt, stations = load_timetable()
    except FileNotFoundError:
        st.error("No se encontró el itinerario procesado. Ejecuta "
                 "`python scripts/parse_timetable.py --pdf <circular.pdf>`.")
        st.stop()

    k = kpis(tt, stations)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Trenes (Lun-Vie)", k["trenes_total"])
    c2.metric("Estaciones", k["estaciones"])
    c3.metric("Tiempo de viaje (min)", k["tiempo_viaje_min"]["media"])
    periodos = sorted(tt["period"].unique())
    c4.metric("Períodos", len(periodos))

    sel = st.multiselect("Períodos a mostrar", periodos, default=periodos)
    st.plotly_chart(marey_figure(tt, stations, periods=sel), use_container_width=True)

    colA, colB = st.columns(2)
    with colA:
        st.subheader("Indicadores por período")
        rows = [{"período": p, "trenes": v["trenes"],
                 "headway medio (min)": v["headway_medio_min"]}
                for p, v in k["por_periodo"].items()]
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    with colB:
        st.subheader("Salidas desde Concepción e intervalos")
        ht = headway_table(tt, stations)
        if sel:
            ht = ht[ht["period"].isin(sel)]
        st.dataframe(ht, use_container_width=True, hide_index=True, height=300)

    st.caption("Horario reconstruido desde la Circular 2/410 (tiempo de marcha por "
               "tramo + dwell). Tiempos validados contra las llegadas publicadas a Coronel.")
