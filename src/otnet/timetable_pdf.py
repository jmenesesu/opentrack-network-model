"""Parser del itinerario de pasajeros (Circular EFE Sur) en PDF.

Extrae la malla Biotren Concepción -> Coronel desde las páginas de la circular y
reconstruye el horario en cada estación.

Lógica del documento (validada contra los tiempos de control publicados):
- Cada tabla tiene, en columnas fijas a la izquierda, el "Tiempo de Viaje" (tiempo
  de marcha por tramo, formato H:MM:SS) y la "Detención" (dwell, formato MM:SS) de
  cada estación.
- En la grilla de trenes solo aparecen tiempos de reloj en origen, terminal y algunos
  puntos de control; NO en todas las estaciones.
- Por eso el horario completo se reconstruye:
      llegada[k]   = salida_origen + Σ tiempo_marcha[1..k] + Σ dwell[1..k-1]
      salida[k]    = llegada[k] + dwell[k]
  Esta reconstrucción reproduce exactamente las llegadas publicadas a Coronel.

Requiere pdfplumber (solo para regenerar el CSV; la app consume el CSV ya procesado).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import pandas as pd

try:
    import pdfplumber
except ImportError:  # pragma: no cover
    pdfplumber = None

_TRAIN = re.compile(r"^20\d{3}$")
_CLK = re.compile(r"^\d{1,2}:\d{2}$")
_HMS = re.compile(r"^\d:\d{2}:\d{2}$")
_MS = re.compile(r"^\d{2}:\d{2}$")

# Páginas (1-indexadas) del sector Concepción-Coronel, tabla superior (ida),
# con su período de operación (asignación determinista según la circular 2/410).
CC_CORONEL_PAGES = (2, 3, 4, 5, 6)
PAGE_PERIOD = {
    2: "Punta Mañana / Valle",
    3: "Punta Mañana / Valle",
    4: "Punta Tarde",
    5: "Punta Tarde",
    6: "Punta Tarde",
}


def _to_seconds(s: str) -> int:
    parts = [int(x) for x in s.split(":")]
    if len(parts) == 3:
        return parts[0] * 3600 + parts[1] * 60 + parts[2]
    return parts[0] * 60 + parts[1]


def _hhmm(sec: float) -> str:
    sec = int(round(sec))
    return f"{sec // 3600}:{(sec % 3600) // 60:02d}"


def _period_of_page(text: str) -> str:
    t = text.lower()
    if "punta tarde" in t:
        return "Punta Tarde"
    if "punta mañana" in t or "horario valle" in t:
        return "Punta Mañana / Valle"
    if "sábado" in t:
        return "Sábado"
    if "domingo" in t:
        return "Domingo"
    return "s/d"


@dataclass
class TimetableTable:
    stations: pd.DataFrame      # order, station, seg_time_s, dwell_s, cum_pos_min
    trains: pd.DataFrame        # train, station, arr, dep, period (formato largo)


def _parse_top_table(page) -> tuple[list, dict, dict, list]:
    """Devuelve (station_rows, seg_time, dwell, train_cols) de la tabla superior."""
    words = page.extract_words()

    header_top = min(
        (w["top"] for w in words if _TRAIN.match(w["text"]) and w["top"] < 70),
        default=None,
    )
    if header_top is None:
        return [], {}, {}, []

    train_cols = sorted(
        {(w["text"], round(w["x0"], 1))
         for w in words if _TRAIN.match(w["text"]) and abs(w["top"] - header_top) < 3},
        key=lambda t: t[1],
    )

    # fila terminal CORONEL (delimita el rango vertical de la tabla superior)
    coronel_top = min(
        (w["top"] for w in words
         if w["text"] == "CORONEL" and w["x0"] < 95 and w["top"] > header_top),
        default=header_top + 150,
    )
    y_lo, y_hi = header_top + 28, coronel_top + 3

    # filas de estación (palabras alfabéticas a la izquierda, agrupadas por fila)
    grp: dict[int, list] = {}
    for w in words:
        if (w["x0"] < 95 and y_lo < w["top"] <= y_hi
                and re.search(r"[A-Za-zÁÉÍÓÚÑáéíóúñ]", w["text"])):
            grp.setdefault(round(w["top"]), []).append((w["x0"], w["text"]))
    station_rows = [
        (y, " ".join(t for _, t in sorted(v))) for y, v in sorted(grp.items())
    ]

    def col_by_row(xc: float, pat: re.Pattern) -> dict:
        out = {}
        for w in words:
            if abs(w["x0"] - xc) < 11 and pat.match(w["text"]) and y_lo < w["top"] <= y_hi:
                name = min(station_rows, key=lambda r: abs(r[0] - w["top"]))[1]
                out[name] = w["text"]
        return out

    seg_time = col_by_row(102, _HMS)   # Tiempo de Viaje
    dwell = col_by_row(157, _MS)        # Detención
    return station_rows, seg_time, dwell, train_cols


def parse_cc_coronel(pdf_path: str, pages=CC_CORONEL_PAGES) -> TimetableTable:
    """Parsea el sector Concepción->Coronel y reconstruye el horario por estación."""
    if pdfplumber is None:
        raise ImportError("pdfplumber es necesario para parsear el PDF "
                          "(pip install pdfplumber).")

    pdf = pdfplumber.open(pdf_path)

    # Perfil de estaciones desde la primera página (común a todas).
    station_rows, seg_time, dwell, _ = _parse_top_table(pdf.pages[pages[0] - 1])
    names = [n for _, n in station_rows]

    # DataFrame de estaciones con posición acumulada (proxy de distancia, en min).
    stations = pd.DataFrame({"order": range(len(names)), "station": names})
    stations["seg_time_s"] = stations["station"].map(lambda n: _to_seconds(seg_time.get(n, "0:00:00")))
    stations["dwell_s"] = stations["station"].map(lambda n: _to_seconds(dwell.get(n, "00:00")))
    stations["cum_pos_min"] = stations["seg_time_s"].cumsum() / 60.0

    seg_by_name = dict(zip(stations["station"], stations["seg_time_s"]))
    dwell_by_name = dict(zip(stations["station"], stations["dwell_s"]))

    def reconstruct(dep_clk: str) -> list[dict]:
        h, m = map(int, dep_clk.split(":"))
        t = h * 3600 + m * 60
        rows = []
        for i, name in enumerate(names):
            if i > 0:
                t += seg_by_name.get(name, 0)
            arr = t
            t += dwell_by_name.get(name, 0)
            dep = t
            rows.append({"station": name, "arr_s": arr, "dep_s": dep})
        return rows

    records = []
    for pno in pages:
        page = pdf.pages[pno - 1]
        period = PAGE_PERIOD.get(pno, _period_of_page(page.extract_text() or ""))
        words = page.extract_words()
        srows_p, _, _, train_cols = _parse_top_table(page)
        origin_top = srows_p[0][0] if srows_p else 94
        # salida de origen (CONCEPCIÓN) por tren
        for w in words:
            if _CLK.match(w["text"]) and abs(w["top"] - origin_top) < 4 and w["x0"] > 180:
                train = min(train_cols, key=lambda c: abs(c[1] - w["x0"]))[0]
                rec = reconstruct(w["text"])
                last = len(rec) - 1
                for i, r in enumerate(rec):
                    records.append({
                        "train": train, "period": period, "direction": "CC->CW",
                        "station": r["station"],
                        "arr": _hhmm(r["arr_s"]),
                        "dep": _hhmm(r["dep_s"]) if i < last else "",
                        "arr_s": r["arr_s"], "dep_s": r["dep_s"], "stop_order": i,
                    })

    trains = pd.DataFrame(records).drop_duplicates(subset=["train", "station"])
    return TimetableTable(stations=stations, trains=trains)
