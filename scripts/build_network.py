"""CLI: construye la red desde data/raw e imprime un resumen de validación.

Uso:
    python scripts/build_network.py --data-dir data/raw
"""

from __future__ import annotations

import argparse
import os
import sys

# Permitir ejecutar sin instalar el paquete
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from otnet.parsers import load_all                       # noqa: E402
from otnet.network import (                               # noqa: E402
    build_macroscopic_graph,
    build_microscopic_graph,
    network_summary,
    degree_table,
)
from otnet.running_time import (                          # noqa: E402
    add_running_times,
    running_time_by_document,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Construye la red OpenTrack.")
    parser.add_argument("--data-dir", default="data/raw",
                        help="Directorio con las exportaciones (default: data/raw)")
    args = parser.parse_args()

    netvisio, metrolinx = load_all(args.data_dir)
    macro = build_macroscopic_graph(netvisio)
    build_microscopic_graph(metrolinx)  # se construye para validar que no falla
    summary = network_summary(netvisio, metrolinx, macro)

    print("=" * 60)
    print("RESUMEN DE LA RED")
    print("=" * 60)
    print(f"Estaciones (macro)        : {summary['macro_estaciones']}")
    print(f"Conexiones (macro)        : {summary['macro_conexiones']}")
    print(f"Componentes conexas       : {summary['componentes_conexas']}")
    print(f"Mayor componente          : {summary['tamano_componente_mayor']} estaciones")
    print(f"Estaciones aisladas       : {summary['estaciones_aisladas'] or 'ninguna'}")
    print(f"Aristas microscópicas     : {summary['micro_aristas']}")
    print(f"Corredores                : {summary['micro_corredores']}")
    print(f"Largo total de vía        : {summary['largo_total_km']} km")
    print(f"Vías por estación         : {summary['vias_por_estacion']}")

    print("\nTiempo de marcha libre por corredor:")
    rt = running_time_by_document(add_running_times(metrolinx))
    print(rt.to_string(index=False))

    print("\nEstaciones por grado de conexión (top 10):")
    print(degree_table(macro).head(10).to_string(index=False))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
