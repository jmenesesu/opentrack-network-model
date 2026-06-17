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
from otnet.scenario import (                              # noqa: E402
    PeriodSpec, generate_timetable, fleet_estimate, compare_kpis,
)

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


@st.cache_data(show_spinner=False)
def load_freight():
    path = os.path.join(DATA_DIR, "freight_corridor.csv")
    return pd.read_csv(path) if os.path.exists(path) else None


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

tab_red, tab_marey, tab_scn = st.tabs([
    "Red (infraestructura)", "Itinerario Biotren (Marey)", "Escenarios / Optimización",
])

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

    freight = load_freight()
    k = kpis(tt, stations)
    por_dir = k.get("por_direccion", {})
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Pasajeros CC→CW", por_dir.get("CC->CW", {}).get("trenes", 0))
    c2.metric("Pasajeros CW→CC", por_dir.get("CW->CC", {}).get("trenes", 0))
    c3.metric("Tiempo de viaje (min)", k["tiempo_viaje_min"]["media"])
    c4.metric("Trenes de carga", int(freight["train"].nunique()) if freight is not None else 0)

    f1, f2, f3 = st.columns([2, 2, 1])
    periodos = sorted(tt["period"].unique())
    sel = f1.multiselect("Períodos", periodos, default=periodos)
    dirs = f2.multiselect("Sentidos", ["CC->CW", "CW->CC"], default=["CC->CW", "CW->CC"])
    show_freight = f3.checkbox("Mostrar carga", value=True)

    st.plotly_chart(
        marey_figure(tt, stations, periods=sel, directions=dirs,
                     freight=freight if show_freight else None),
        use_container_width=True)

    colA, colB = st.columns(2)
    with colA:
        st.subheader("Indicadores por sentido")
        rows = [{"sentido": d, "trenes": v["trenes"],
                 "viaje medio (min)": v["viaje_medio_min"]}
                for d, v in por_dir.items()]
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    with colB:
        st.subheader("Salidas e intervalos")
        dsel = st.radio("Sentido", ["CC->CW", "CW->CC"], horizontal=True)
        ht = headway_table(tt, stations, direction=dsel)
        if sel:
            ht = ht[ht["period"].isin(sel)]
        st.dataframe(ht, use_container_width=True, hide_index=True, height=260)

    st.caption("Pasajeros: horario reconstruido de la Circular 2/410 (validado contra "
               "llegadas a Coronel). Carga (TRANSAP/FEPASA): restricción fija de la "
               "operación; horarios de los programas 2/421 y 2/416.")

# --------------------------------------------------------------------------- #
# Pestaña ESCENARIOS / OPTIMIZACIÓN
# --------------------------------------------------------------------------- #
with tab_scn:
    try:
        tt, stations = load_timetable()
    except FileNotFoundError:
        st.error("Falta el itinerario procesado (data/timetable_cc_coronel.csv).")
        st.stop()

    st.markdown("Define la **frecuencia objetivo** por período y el modelo genera un "
                "itinerario cadenciado (headway constante) para Concepción → Coronel.")

    travel_min = kpis(tt, stations)["tiempo_viaje_min"]["media"] or 42.0

    cfg = st.columns(4)
    with cfg[0]:
        hw_pm = st.slider("Headway Punta Mañana (min)", 5, 40, 10)
        rng_pm = st.slider("Punta Mañana (h)", 5.0, 12.0, (6.0, 9.0), step=0.5)
    with cfg[1]:
        hw_v = st.slider("Headway Valle (min)", 5, 60, 20)
        rng_v = st.slider("Valle (h)", 8.0, 18.0, (9.0, 17.0), step=0.5)
    with cfg[2]:
        hw_pt = st.slider("Headway Punta Tarde (min)", 5, 40, 10)
        rng_pt = st.slider("Punta Tarde (h)", 16.0, 23.0, (17.0, 20.0), step=0.5)
    with cfg[3]:
        turnaround = st.slider("Tiempo de vuelta en terminal (min)", 0, 30, 10)

    periods = [
        PeriodSpec("Punta Mañana", rng_pm[0], rng_pm[1], hw_pm),
        PeriodSpec("Valle", rng_v[0], rng_v[1], hw_v),
        PeriodSpec("Punta Tarde", rng_pt[0], rng_pt[1], hw_pt),
    ]
    scenario = generate_timetable(stations, periods)

    fleet = max(fleet_estimate(travel_min, hw, turnaround) for hw in (hw_pm, hw_v, hw_pt))
    m = st.columns(4)
    m[0].metric("Trenes/día (escenario)", scenario["train"].nunique())
    m[1].metric("Trenes/día (actual)", tt["train"].nunique())
    m[2].metric("Flota máx. estimada", f"{fleet} trenes")
    m[3].metric("Tiempo de viaje (min)", round(travel_min, 0))

    st.plotly_chart(marey_figure(scenario, stations), use_container_width=True)

    st.subheader("Comparación con la operación actual")
    st.dataframe(compare_kpis(tt, scenario, stations),
                 use_container_width=True, hide_index=True)

    st.caption("Flota estimada = ceil((2·viaje + 2·vuelta) / headway); aproximada, "
               "pendiente de validar con material rodante y el sentido inverso. "
               "El optimizador formal de cruces se incorpora al sumar Coronel→Concepción.")

