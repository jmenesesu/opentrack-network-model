"""otnet: caracterización de la red ferroviaria de EFE Sur desde exportaciones de OpenTrack."""

from .parsers import (
    parse_netvisio,
    parse_metrolinx,
    NetvisioData,
)
from .network import (
    build_macroscopic_graph,
    build_microscopic_graph,
    network_summary,
)

__all__ = [
    "parse_netvisio",
    "parse_metrolinx",
    "NetvisioData",
    "build_macroscopic_graph",
    "build_microscopic_graph",
    "network_summary",
]

__version__ = "0.1.0"
