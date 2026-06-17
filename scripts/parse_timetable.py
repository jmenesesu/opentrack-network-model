"""Genera los CSV del itinerario Biotren CC->Coronel desde el PDF de la circular.

Uso:
    pip install pdfplumber
    python scripts/parse_timetable.py --pdf "ruta/al/itinerario.pdf"

Salida (en data/):
    timetable_cc_coronel.csv   -> horario largo (tren, estación, llegada, salida, período)
    stations_cc_coronel.csv    -> secuencia de estaciones con tiempo de marcha y dwell
"""

from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from otnet.timetable_pdf import parse_cc_coronel   # noqa: E402

DEFAULT_OUT = os.path.join(os.path.dirname(__file__), "..", "data")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", required=True, help="Ruta al PDF de la circular")
    ap.add_argument("--out", default=DEFAULT_OUT, help="Directorio de salida (data/)")
    args = ap.parse_args()

    tt = parse_cc_coronel(args.pdf)
    os.makedirs(args.out, exist_ok=True)
    tt_path = os.path.join(args.out, "timetable_cc_coronel.csv")
    st_path = os.path.join(args.out, "stations_cc_coronel.csv")
    tt.trains.to_csv(tt_path, index=False, encoding="utf-8")
    tt.stations.to_csv(st_path, index=False, encoding="utf-8")

    print(f"Trenes: {tt.trains['train'].nunique()} | filas: {len(tt.trains)}")
    print(f"Estaciones: {len(tt.stations)}")
    print(f"Guardado: {tt_path}")
    print(f"Guardado: {st_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
