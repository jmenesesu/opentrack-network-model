"""Lectores de las exportaciones de infraestructura de OpenTrack.

Soporta dos formatos exportados desde
``Functions -> Exchange Infrastructure Data -> Export ...``:

- **Netvisio**: vista macroscópica. Tres archivos hermanos (``.node``, ``.nodeattr``,
  ``.edge``) con estaciones, atributos por estación (nº de vías) y adyacencias.
- **Metrolinx**: vista microscópica. Un ``.txt`` tab-separado con una fila por arista
  de vía, incluyendo largo, velocidades por sentido, pendiente y radio de curva.

Todos los archivos vienen en codificación ISO-8859-1 (Latin-1).
"""

from __future__ import annotations

import glob
import os
from dataclasses import dataclass, field

import pandas as pd

ENCODING = "iso-8859-1"

# --------------------------------------------------------------------------- #
# Netvisio (macroscópico)
# --------------------------------------------------------------------------- #


@dataclass
class NetvisioData:
    """Contenedor de los tres archivos Netvisio ya parseados."""

    nodes: pd.DataFrame          # columnas: code, name, x, y
    node_attrs: pd.DataFrame     # columnas: code, attr, value
    edges: pd.DataFrame          # columnas: from_code, to_code
    tracks_by_station: dict[str, int] = field(default_factory=dict)


def _find_one(data_dir: str, pattern: str) -> str | None:
    matches = sorted(glob.glob(os.path.join(data_dir, pattern)))
    return matches[0] if matches else None


def parse_netvisio(data_dir: str) -> NetvisioData:
    """Lee los archivos Netvisio (.node, .nodeattr, .edge) de un directorio."""
    node_path = _find_one(data_dir, "*.node")
    attr_path = _find_one(data_dir, "*.nodeattr")
    edge_path = _find_one(data_dir, "*.edge")

    if node_path is None:
        raise FileNotFoundError(f"No se encontró un archivo .node en {data_dir!r}")

    nodes = pd.read_csv(
        node_path, sep="\t", header=None, encoding=ENCODING,
        names=["code", "name", "x", "y"], dtype={"code": str, "name": str},
    )
    nodes["code"] = nodes["code"].str.strip()
    nodes["name"] = nodes["name"].str.strip()

    if attr_path and os.path.getsize(attr_path) > 0:
        node_attrs = pd.read_csv(
            attr_path, sep="\t", header=None, encoding=ENCODING,
            names=["code", "attr", "value"], dtype={"code": str, "attr": str},
        )
        node_attrs["code"] = node_attrs["code"].str.strip()
        node_attrs["attr"] = node_attrs["attr"].str.strip()
    else:
        node_attrs = pd.DataFrame(columns=["code", "attr", "value"])

    if edge_path and os.path.getsize(edge_path) > 0:
        edges = pd.read_csv(
            edge_path, sep="\t", header=None, encoding=ENCODING,
            names=["from_code", "to_code"], dtype=str,
        )
        edges["from_code"] = edges["from_code"].str.strip()
        edges["to_code"] = edges["to_code"].str.strip()
    else:
        edges = pd.DataFrame(columns=["from_code", "to_code"])

    tracks = (
        node_attrs[node_attrs["attr"].str.lower() == "number of tracks"]
        .assign(value=lambda d: pd.to_numeric(d["value"], errors="coerce"))
        .dropna(subset=["value"])
        .set_index("code")["value"].astype(int).to_dict()
    )

    return NetvisioData(nodes=nodes, node_attrs=node_attrs, edges=edges,
                        tracks_by_station=tracks)


# --------------------------------------------------------------------------- #
# Metrolinx (microscópico)
# --------------------------------------------------------------------------- #

# Orden de columnas según el encabezado (comentado con //) del export Metrolinx.
METROLINX_COLUMNS = [
    "document", "line", "track", "edge_name", "edge_id", "length",
    "v1_id", "v2_id", "v1_name", "v2_name", "v1_km", "v2_km",
    "v1_sig", "v2_sig", "v1_switch_time", "v2_switch_time",
    "v1_station_id", "v2_station_id",
    "speed_1_1", "speed_1_2", "speed_1_3", "speed_1_4",
    "speed_2_1", "speed_2_2", "speed_2_3", "speed_2_4",
    "gradient", "curve_radius",
]

_NUMERIC_COLS = [
    "length", "v1_km", "v2_km",
    "speed_1_1", "speed_1_2", "speed_1_3", "speed_1_4",
    "speed_2_1", "speed_2_2", "speed_2_3", "speed_2_4",
    "gradient", "curve_radius",
]


def parse_metrolinx(path: str) -> pd.DataFrame:
    """Lee el ``.txt`` Metrolinx y devuelve un DataFrame con una fila por arista.

    Las líneas de comentario empiezan con ``//`` (incluido el encabezado), por lo que
    se omiten y las columnas se asignan según :data:`METROLINX_COLUMNS`.
    """
    df = pd.read_csv(
        path, sep="\t", header=None, names=METROLINX_COLUMNS,
        comment="/", encoding=ENCODING, dtype=str, skip_blank_lines=True,
    )
    # Limpieza de strings
    for col in ["document", "v1_id", "v2_id", "edge_id"]:
        df[col] = df[col].astype(str).str.strip()
    # Conversión numérica (coma/punto: OpenTrack usa punto decimal aquí)
    for col in _NUMERIC_COLS:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["length"]).reset_index(drop=True)
    return df


def load_all(data_dir: str) -> tuple[NetvisioData, pd.DataFrame]:
    """Atajo: carga Netvisio + Metrolinx desde un directorio."""
    netvisio = parse_netvisio(data_dir)
    mtx_path = _find_one(data_dir, "*Metrolinx*")
    if mtx_path is None:
        raise FileNotFoundError(f"No se encontró el export Metrolinx en {data_dir!r}")
    metrolinx = parse_metrolinx(mtx_path)
    return netvisio, metrolinx
