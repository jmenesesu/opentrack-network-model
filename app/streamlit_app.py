"""App Streamlit de validación de la red OpenTrack.

Muestra el grafo macroscópico de estaciones, la tabla de estaciones con capacidad
(nº de vías) y los atributos físicos de las aristas microscópicas.

Ejecutar:
    streamlit run app/streamlit_app.py
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
    build_macroscopic_graph,
    network_summary,
    degree_table,
)
from otnet.running_time import (                          # noqa: E402
    add_running_times,
    running_time_by_document,
)

DEFAULT_DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "raw")

st.set_page_config(page_title="Red OpenTrack EFE Sur", layout="wide")


@st.cache_data(show_spinner=False)
def load_network(data_dir: str):
    netvisio, metrolinx = load_all(data_dir)
    macro = build_macroscopic_graph(netvisio)
    summary = network_summary(netvisio, metrolinx, macro)
    return netvisio, metrolinx, macro, summary


def graph_figure(macro: nx.Graph) -> go.Figure:
    # spring_layout no requiere scipy (a diferencia de kamada_kawai_layout);
    # seed fija para que el layout sea reproducible entre recargas.
    pos = nx.spring_layout(macro, seed=42, k=0.6, iterations=200)
    edge_x, edge_y = [], []
    for u, v in macro.edges():
        edge_x += [pos[u][0], pos[v][0], None]
        edge_y += [pos[u][1], pos[v][1], None]
    edge_trace = go.Scatter(
        x=edge_x, y=edge_y, mode="lines",
        line=dict(width=1, color="#9aa0a6"), hoverinfo="none",
    )
    node_x = [pos[n][0] for n in macro.nodes()]
    node_y = [pos[n][1] for n in macro.nodes()]
    tracks = [macro.nodes[n].get("n_tracks") or 1 for n in macro.nodes()]
    labels = [
        f"{n} — {macro.nodes[n].get('name')}<br>Vías: {macro.nodes[n].get('n_tracks')}"
        for n in macro.nodes()
    ]
    node_trace = go.Scatter(
        x=node_x, y=node_y, mode="markers+text",
        text=list(macro.nodes()), textposition="top center",
        textfont=dict(size=9),
        marker=dict(
            size=[8 + 2 * t for t in tracks],
            color=tracks, colorscale="Blues", showscale=True,
            colorbar=dict(title="Nº vías"), line=dict(width=1, color="#1f3864"),
        ),
        hovertext=labels, hoverinfo="text",
    )
    fig = go.Figure([edge_trace, node_trace])
    fig.update_layout(
        showlegend=False, margin=dict(l=0, r=0, t=10, b=0), height=600,
        xaxis=dict(visible=False), yaxis=dict(visible=False),
    )
    return fig


st.title("Caracterización de la red — EFE Sur (OpenTrack)")

data_dir = st.sidebar.text_input("Directorio de datos", value=DEFAULT_DATA_DIR)

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
    st.warning(
        f"La red tiene {summary['componentes_conexas']} componentes desconectadas. "
        f"Estaciones aisladas: {summary['estaciones_aisladas'] or 'ninguna'}"
    )
else:
    st.success("La red macroscópica está completamente conectada.")

tab1, tab2, tab3 = st.tabs(["Grafo", "Estaciones", "Corredores y aristas"])

with tab1:
    st.plotly_chart(graph_figure(macro), use_container_width=True)

with tab2:
    st.dataframe(degree_table(macro), use_container_width=True, hide_index=True)

with tab3:
    st.subheader("Tiempo de marcha libre por corredor")
    st.dataframe(
        running_time_by_document(add_running_times(metrolinx)),
        use_container_width=True, hide_index=True,
    )
    st.subheader("Aristas microscópicas (muestra)")
    cols = ["document", "v1_id", "v2_id", "length",
            "speed_1_1", "speed_2_1", "gradient", "curve_radius"]
    st.dataframe(metrolinx[cols].head(500), use_container_width=True, hide_index=True)

st.caption(
    "Tiempos de marcha = cota inferior en marcha libre (largo/velocidad máx.), "
    "sin aceleración ni paradas. Validar con la simulación de OpenTrack."
)
