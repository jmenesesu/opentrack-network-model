"""Tests de los parsers y la construcción del grafo sobre los datos reales."""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from otnet.parsers import load_all
from otnet.network import build_macroscopic_graph, build_microscopic_graph
from otnet.running_time import add_running_times, free_run_time

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "raw")
HAS_DATA = os.path.isdir(DATA_DIR) and bool(os.listdir(DATA_DIR))
skip_no_data = pytest.mark.skipif(not HAS_DATA, reason="sin datos en data/raw")


def test_free_run_time_basic():
    # 3600 m a 36 km/h (=10 m/s) => 360 s
    assert free_run_time(3600, 36) == pytest.approx(360.0)
    # velocidad inválida => NaN
    assert free_run_time(100, 0) != free_run_time(100, 0)  # NaN != NaN


@skip_no_data
def test_netvisio_loads():
    netvisio, _ = load_all(DATA_DIR)
    assert len(netvisio.nodes) > 0
    assert netvisio.tracks_by_station  # no vacío
    assert all(v >= 1 for v in netvisio.tracks_by_station.values())


@skip_no_data
def test_metrolinx_columns_numeric():
    _, metrolinx = load_all(DATA_DIR)
    assert len(metrolinx) > 0
    assert (metrolinx["length"] >= 0).all()
    assert metrolinx["document"].nunique() >= 1


@skip_no_data
def test_graphs_build():
    netvisio, metrolinx = load_all(DATA_DIR)
    macro = build_macroscopic_graph(netvisio)
    micro = build_microscopic_graph(metrolinx)
    assert macro.number_of_nodes() == len(netvisio.nodes)
    assert micro.number_of_edges() > 0


@skip_no_data
def test_running_times_present():
    _, metrolinx = load_all(DATA_DIR)
    df = add_running_times(metrolinx)
    assert "t_up_s" in df.columns
    assert df["t_up_s"].notna().any()
