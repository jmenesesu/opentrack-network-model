"""Parser de los programas de trenes de carga (TRANSAP / FEPASA) en PDF.

Extrae, para el corredor Concepción–Coronel, las horas de paso de cada tren de
carga (Llega/Sale por estación). Los trenes de carga son una RESTRICCIÓN fija de
la operación: ocupan canales de vía que el itinerario de pasajeros debe respetar.

Formato del PDF: malla con columnas Kilometraje | Dist. parciales | Estación |
[por tren: Llega Sale]. Las cabeceras de tren son números de 5 dígitos en la
parte superior. ".. .." indica paso sin detención.
"""

from __future__ import annotations

import re
import unicodedata

import pandas as pd

try:
    import pdfplumber
except ImportError:  # pragma: no cover
    pdfplumber = None

_TRAIN = re.compile(r"^\d{5}$")
_CLK = re.compile(r"^\d{1,2}:\d{2}$")

# Kilometraje (infraestructura) del corredor Concepción->Coronel, según el
# programa de carga. Las estaciones de carga difieren de los paraderos de
# pasajeros; estos son los puntos ferroviarios reales.
CC_CORONEL_KM = {
    "concepcion": 0.0,
    "biobio": 3.1,
    "boca sur": 7.4,
    "lomas coloradas": 11.5,
    "escuadron": 19.7,
    "lagunillas": 24.5,
    "coronel": 27.7,
}


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    return re.sub(r"\s+", " ", s).strip()


def _station_km(name: str) -> float | None:
    return CC_CORONEL_KM.get(_norm(name))


def parse_freight_corridor(pdf_path: str, operator: str) -> pd.DataFrame:
    """Devuelve las pasadas de trenes de carga por el corredor CC-Coronel.

    Columnas: operator, train, station, km, time_s, direction.
    """
    if pdfplumber is None:
        raise ImportError("pip install pdfplumber")

    pdf = pdfplumber.open(pdf_path)
    rows = []

    for page in pdf.pages:
        words = page.extract_words()
        # cabeceras de tren (números de 5 dígitos en la parte superior)
        heads = [w for w in words if _TRAIN.match(w["text"]) and w["top"] < 130]
        if not heads:
            continue
        # sub-columnas Llega/Sale
        lls = sorted([w for w in words if w["text"] in ("Llega", "Sale")],
                     key=lambda w: w["x0"])
        if not lls:
            continue
        # cada tren: Llega y Sale más cercanas a su x
        trains = []
        for h in heads:
            near = sorted(lls, key=lambda w: abs(w["x0"] - h["x0"]))[:2]
            near = sorted(near, key=lambda w: w["x0"])
            if len(near) == 2:
                trains.append({"id": h["text"], "llega_x": near[0]["x0"],
                               "sale_x": near[1]["x0"]})

        # filas de estación del corredor (por nombre)
        station_rows = []
        for w in words:
            if 100 < w["x0"] < 210 and _station_km(w["text"]) is not None:
                station_rows.append((w["top"], w["text"]))
        # nombres de 2 palabras (Boca Sur, Lomas Coloradas) -> reconstruir por fila
        # (se cubren porque _station_km normaliza; "Boca"/"Sur" sueltos no matchean,
        #  así que detectamos por la primera palabra clave)
        kw = {"boca": "Boca Sur", "lomas": "Lomas Coloradas"}
        for w in words:
            if 100 < w["x0"] < 210 and _norm(w["text"]) in kw:
                station_rows.append((w["top"], kw[_norm(w["text"])]))

        # tiempos por tren y estación
        times = [w for w in words if _CLK.match(w["text"])]
        for tr in trains:
            seq = []
            for top, name in station_rows:
                km = _station_km(name)
                # buscar token de tiempo en sub-columna Sale (preferente) o Llega
                best = None
                for w in times:
                    if abs(w["top"] - top) < 4:
                        for typ, xc in (("sale", tr["sale_x"]), ("llega", tr["llega_x"])):
                            if abs(w["x0"] - xc) < 16:
                                best = (typ, w["text"]);
                if best:
                    h, m = map(int, best[1].split(":"))
                    seq.append({"station": name, "km": km, "time_s": h * 3600 + m * 60})
            if len(seq) >= 2:
                seq.sort(key=lambda r: r["km"])
                # desenvolver cruce de medianoche: si el rango supera 6 h, las horas
                # de madrugada (<6:00) pertenecen al día siguiente -> +24 h
                ts = [r["time_s"] for r in seq]
                if max(ts) - min(ts) > 6 * 3600:
                    for r in seq:
                        if r["time_s"] < 6 * 3600:
                            r["time_s"] += 86400
                # dirección por el orden temporal vs km (ya desenvuelto)
                t_first, t_last = seq[0]["time_s"], seq[-1]["time_s"]
                direction = "CC->CW" if t_last >= t_first else "CW->CC"
                for r in seq:
                    rows.append({"operator": operator, "train": tr["id"],
                                 "station": r["station"], "km": r["km"],
                                 "time_s": r["time_s"], "direction": direction})

    df = pd.DataFrame(rows).drop_duplicates(subset=["operator", "train", "station"])
    return df.reset_index(drop=True)
