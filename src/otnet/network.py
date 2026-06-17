"""Construcción del grafo de la red y resumen de validación."""

from __future__ import annotations

import networkx as nx
import pandas as pd

from .parsers import NetvisioData
from .running_time import add_running_times


# --------------------------------------------------------------------------- #
# Grafo macroscópico (estaciones)
# --------------------------------------------------------------------------- #


def build_macroscopic_graph(netvisio: NetvisioData) -> nx.Graph:
    """Grafo no dirigido de estaciones.

    Nodos = estaciones (code, name, n_tracks). Aristas = adyacencias Netvisio.
    """
    g = nx.Graph()
    for row in netvisio.nodes.itertuples(index=False):
        g.add_node(
            row.code,
            name=row.name,
            n_tracks=netvisio.tracks_by_station.get(row.code),
        )
    for row in netvisio.edges.itertuples(index=False):
        if row.from_code and row.to_code:
            g.add_edge(row.from_code, row.to_code)
    return g


# --------------------------------------------------------------------------- #
# Grafo microscópico (vértices de vía)
# --------------------------------------------------------------------------- #


def build_microscopic_graph(metrolinx: pd.DataFrame) -> nx.DiGraph:
    """Grafo dirigido de vértices de vía con atributos físicos por arista.

    Cada arista lleva largo (m), velocidades, pendiente, radio y tiempos de marcha.
    Los IDs de vértice se prefijan con el documento para evitar colisiones entre
    corredores distintos.
    """
    df = add_running_times(metrolinx)
    g = nx.DiGraph()
    for r in df.itertuples(index=False):
        u = f"{r.document}:{r.v1_id}"
        v = f"{r.document}:{r.v2_id}"
        g.add_edge(
            u, v,
            edge_id=r.edge_id,
            document=r.document,
            length=r.length,
            speed_up=r.speed_1_1,
            speed_down=r.speed_2_1,
            gradient=r.gradient,
            curve_radius=r.curve_radius,
            t_up_s=r.t_up_s,
            t_down_s=r.t_down_s,
        )
    return g


# --------------------------------------------------------------------------- #
# Resumen de validación
# --------------------------------------------------------------------------- #


def network_summary(
    netvisio: NetvisioData,
    metrolinx: pd.DataFrame,
    macro: nx.Graph,
) -> dict:
    """Métricas para validar que la red quedó bien construida y conectada."""
    components = list(nx.connected_components(macro))
    components.sort(key=len, reverse=True)
    isolated = [n for n in macro.nodes if macro.degree(n) == 0]

    df = add_running_times(metrolinx)
    total_km = round(df["length"].sum() / 1000.0, 2)

    tracks = pd.Series(netvisio.tracks_by_station)

    return {
        "macro_estaciones": macro.number_of_nodes(),
        "macro_conexiones": macro.number_of_edges(),
        "componentes_conexas": len(components),
        "tamano_componente_mayor": len(components[0]) if components else 0,
        "estaciones_aisladas": isolated,
        "micro_aristas": len(df),
        "micro_corredores": df["document"].nunique(),
        "largo_total_km": total_km,
        "vias_por_estacion": {
            "min": int(tracks.min()) if not tracks.empty else None,
            "max": int(tracks.max()) if not tracks.empty else None,
            "media": round(float(tracks.mean()), 2) if not tracks.empty else None,
        },
    }


def degree_table(macro: nx.Graph) -> pd.DataFrame:
    """Tabla de estaciones con grado (nº de conexiones) y nº de vías."""
    rows = []
    for n, d in macro.nodes(data=True):
        rows.append({
            "code": n,
            "name": d.get("name"),
            "n_tracks": d.get("n_tracks"),
            "grado": macro.degree(n),
        })
    return (
        pd.DataFrame(rows)
        .sort_values(["grado", "n_tracks"], ascending=False, na_position="last")
        .reset_index(drop=True)
    )
