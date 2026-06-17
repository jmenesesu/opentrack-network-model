"""Parser del itinerario de pasajeros (Circular EFE Sur) en PDF.

Extrae la malla Biotren Concepción <-> Coronel (AMBOS sentidos) y reconstruye el
horario en cada estación.

Cada página tiene dos tablas apiladas: arriba Concepción->Coronel, abajo
Coronel->Concepción. En cada tabla, las columnas izquierdas dan el "Tiempo de
Viaje" (marcha por tramo, H:MM:SS) y la "Detención" (dwell, MM:SS) por estación;
la grilla de trenes solo trae horas de reloj en origen/terminal/controles. El
horario completo se reconstruye:
    llegada[k] = salida_origen + Σ marcha[1..k] + Σ dwell[1..k-1]
    salida[k]  = llegada[k] + dwell[k]
Validado contra las llegadas publicadas.

Además asigna kilometraje a cada estación, anclando a los km del corredor del
programa de carga (Concepción 0, Lomas Coloradas 11.5, Coronel 27.7) e
interpolando el resto por tiempo de marcha acumulado.
"""

from __future__ import annotations

import re
import unicodedata
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

CC_CORONEL_PAGES = (2, 3, 4, 5, 6)
PAGE_PERIOD = {2: "Punta Mañana / Valle", 3: "Punta Mañana / Valle",
               4: "Punta Tarde", 5: "Punta Tarde", 6: "Punta Tarde"}

# Anclas de kilometraje (corredor CC-Coronel, según programa de carga).
_KM_ANCHORS = {"concepcion": 0.0, "lomas coloradas": 11.5, "coronel": 27.7}


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    return re.sub(r"\s+", " ", s).strip()


def _to_seconds(s: str) -> int:
    p = [int(x) for x in s.split(":")]
    return p[0] * 3600 + p[1] * 60 + p[2] if len(p) == 3 else p[0] * 60 + p[1]


def _hhmm(sec: float) -> str:
    sec = int(round(sec))
    return f"{sec // 3600}:{(sec % 3600) // 60:02d}"


@dataclass
class TimetableTable:
    stations: pd.DataFrame
    trains: pd.DataFrame


def _parse_table(words, header_top, y_lo, y_hi):
    """Extrae (station_rows, seg_time, dwell, train_cols) de una tabla."""
    train_cols = sorted(
        {(w["text"], round(w["x0"], 1)) for w in words
         if _TRAIN.match(w["text"]) and abs(w["top"] - header_top) < 3},
        key=lambda t: t[1])
    grp: dict[int, list] = {}
    for w in words:
        if (w["x0"] < 95 and y_lo < w["top"] <= y_hi
                and re.search(r"[A-Za-zÁÉÍÓÚÑáéíóúñ]", w["text"])):
            grp.setdefault(round(w["top"]), []).append((w["x0"], w["text"]))
    station_rows = [(y, " ".join(t for _, t in sorted(v))) for y, v in sorted(grp.items())]

    def col_by_row(xc, pat):
        out = {}
        for w in words:
            if abs(w["x0"] - xc) < 11 and pat.match(w["text"]) and y_lo < w["top"] <= y_hi:
                name = min(station_rows, key=lambda r: abs(r[0] - w["top"]))[1]
                out[name] = w["text"]
        return out

    return station_rows, col_by_row(102, _HMS), col_by_row(157, _MS), train_cols


def _assign_km(stations: pd.DataFrame) -> pd.DataFrame:
    """Asigna km por interpolación de tiempo acumulado entre anclas conocidas."""
    df = stations.sort_values("order").reset_index(drop=True)
    breaks = []  # (cum_pos_min, km)
    for _, r in df.iterrows():
        km = _KM_ANCHORS.get(_norm(r["station"]))
        if km is not None:
            breaks.append((r["cum_pos_min"], km))
    breaks.sort()

    def interp(t):
        if not breaks:
            return None
        if t <= breaks[0][0]:
            return breaks[0][1]
        for (t0, k0), (t1, k1) in zip(breaks, breaks[1:]):
            if t0 <= t <= t1:
                return k0 + (k1 - k0) * (t - t0) / (t1 - t0) if t1 > t0 else k0
        return breaks[-1][1]

    df["km"] = df["cum_pos_min"].map(interp)
    return df


def parse_cc_coronel(pdf_path: str, pages=CC_CORONEL_PAGES) -> TimetableTable:
    if pdfplumber is None:
        raise ImportError("pip install pdfplumber")
    pdf = pdfplumber.open(pdf_path)

    # Perfil de estaciones (sentido CC->CW) desde la primera página.
    p0 = pdf.pages[pages[0] - 1]
    w0 = p0.extract_words()
    htop = min(w["top"] for w in w0 if _TRAIN.match(w["text"]) and w["top"] < 70)
    cor_top = min(w["top"] for w in w0 if w["text"] == "CORONEL"
                  and w["x0"] < 95 and w["top"] > htop)
    srows, seg, dwell, _ = _parse_table(w0, htop, htop + 28, cor_top + 3)
    names = [n for _, n in srows]
    stations = pd.DataFrame({"order": range(len(names)), "station": names})
    stations["seg_time_s"] = stations["station"].map(lambda n: _to_seconds(seg.get(n, "0:00:00")))
    stations["dwell_s"] = stations["station"].map(lambda n: _to_seconds(dwell.get(n, "00:00")))
    stations["cum_pos_min"] = stations["seg_time_s"].cumsum() / 60.0
    stations = _assign_km(stations)
    km_by = dict(zip(stations["station"], stations["km"]))

    def reconstruct(dep_clk, srows_dir, seg_d, dwell_d):
        h, m = map(int, dep_clk.split(":"))
        t = h * 3600 + m * 60
        out = []
        last = len(srows_dir) - 1
        for i, (_, name) in enumerate(srows_dir):
            if i > 0:
                t += _to_seconds(seg_d.get(name, "0:00:00"))
            arr = t
            t += _to_seconds(dwell_d.get(name, "00:00"))
            out.append({"station": name, "arr_s": arr, "dep_s": t,
                        "arr": _hhmm(arr), "dep": _hhmm(t) if i < last else "",
                        "stop_order": i})
        return out

    records = []
    for pno in pages:
        page = pdf.pages[pno - 1]
        period = PAGE_PERIOD.get(pno, "s/d")
        words = page.extract_words()
        trains_tops = sorted(w["top"] for w in words if _TRAIN.match(w["text"]))
        top_hdr = min((t for t in trains_tops if t < 70), default=None)
        bot_hdr = min((t for t in trains_tops if 235 < t < 260), default=None)

        for hdr, origin_name, term_name, direction in (
                (top_hdr, "CONCEPCIÓN", "CORONEL", "CC->CW"),
                (bot_hdr, "CORONEL", "CONCEPCIÓN", "CW->CC")):
            if hdr is None:
                continue
            term_top = min((w["top"] for w in words if w["text"] == term_name
                            and w["x0"] < 95 and w["top"] > hdr), default=hdr + 150)
            srows_d, seg_d, dwell_d, tcols = _parse_table(words, hdr, hdr + 28, term_top + 3)
            if not srows_d:
                continue
            origin_top = srows_d[0][0]
            for w in words:
                if _CLK.match(w["text"]) and abs(w["top"] - origin_top) < 4 and w["x0"] > 180:
                    train = min(tcols, key=lambda c: abs(c[1] - w["x0"]))[0]
                    for r in reconstruct(w["text"], srows_d, seg_d, dwell_d):
                        records.append({"train": train, "period": period,
                                        "direction": direction, **r,
                                        "km": km_by.get(r["station"])})

    trains = pd.DataFrame(records).drop_duplicates(subset=["train", "direction", "station"])
    return TimetableTable(stations=stations, trains=trains)
