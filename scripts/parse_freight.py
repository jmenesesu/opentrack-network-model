"""Genera data/freight_corridor.csv (trenes de carga en el corredor CC-Coronel).

Uso:
    pip install pdfplumber
    python scripts/parse_freight.py --transap <2-421.pdf> --fepasa <2-416.pdf>
"""

from __future__ import annotations

import argparse
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from otnet.freight_pdf import parse_freight_corridor   # noqa: E402

DEFAULT_OUT = os.path.join(os.path.dirname(__file__), "..", "data")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--transap", help="PDF del programa TRANSAP")
    ap.add_argument("--fepasa", help="PDF del programa FEPASA")
    ap.add_argument("--out", default=DEFAULT_OUT)
    args = ap.parse_args()

    frames = []
    if args.transap:
        frames.append(parse_freight_corridor(args.transap, "TRANSAP"))
    if args.fepasa:
        frames.append(parse_freight_corridor(args.fepasa, "FEPASA"))
    if not frames:
        ap.error("Indica al menos --transap o --fepasa")

    fr = pd.concat(frames, ignore_index=True)
    path = os.path.join(args.out, "freight_corridor.csv")
    fr.to_csv(path, index=False, encoding="utf-8")
    print(f"Trenes de carga: {fr['train'].nunique()} | filas: {len(fr)}")
    print(f"Guardado: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
