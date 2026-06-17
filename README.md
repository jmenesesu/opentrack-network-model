# opentrack-network-model

Modelo en Python para **caracterizar la red ferroviaria de EFE Sur** a partir de las
exportaciones de OpenTrack, con el fin de optimizar itinerarios y crear escenarios de
operación. Pensado para crecer hacia un optimizador y desplegarse como app web en
Streamlit.

## Objetivo

1. Leer las exportaciones de infraestructura de OpenTrack (formatos **Netvisio** y
   **Metrolinx**) y construir un grafo de la red.
2. Caracterizar la red en dos niveles:
   - **Macroscópico** (Netvisio): estaciones como nodos, con número de vías (capacidad)
     y adyacencias entre estaciones. Es el nivel sobre el que corre la optimización.
   - **Microscópico** (Metrolinx): aristas de vía con largo, velocidades por sentido,
     pendiente y radio de curva. Aporta la física para estimar tiempos de marcha.
3. Validar conectividad y entregar un resumen de la red.

Objetivos de optimización previstos (fases siguientes): minimizar tiempo de viaje,
maximizar frecuencia/capacidad y robustez ante retrasos.

## Estructura

```
opentrack-network-model/
├── data/
│   └── raw/                  # exportaciones crudas de OpenTrack (no editar)
├── src/
│   └── otnet/
│       ├── parsers.py        # lectores de Netvisio y Metrolinx
│       ├── network.py        # construcción del grafo y resumen
│       └── running_time.py   # tiempo de marcha (free-run) por arista
├── scripts/
│   └── build_network.py      # CLI: construye la red e imprime el resumen
├── app/
│   └── streamlit_app.py      # interfaz de validación (Streamlit)
├── tests/
│   └── test_parsers.py
├── requirements.txt
└── README.md
```

## Uso

```bash
pip install -r requirements.txt

# construir la red e imprimir resumen
python scripts/build_network.py --data-dir data/raw

# levantar la app de validación
streamlit run app/streamlit_app.py
```

## Datos de entrada

Coloca en `data/raw/` los archivos exportados desde OpenTrack
(`Functions → Exchange Infrastructure Data → Export ...`):

| Archivo                                       | Formato   | Aporta                                              |
|-----------------------------------------------|-----------|-----------------------------------------------------|
| `*.node`, `*.nodeattr`, `*.edge`              | Netvisio  | Estaciones, nº de vías, adyacencias macroscópicas   |
| `Export Metrolinx-format Infraestructure.txt` | Metrolinx | Aristas con largo, velocidades, pendiente, radio    |

Codificación esperada: **ISO-8859-1** (Latin-1).

## Notas y límites

- Los tiempos de marcha que calcula `running_time.py` son **cotas inferiores en
  marcha libre** (largo / velocidad máxima), sin aceleración, frenado ni paradas.
  Los tiempos finos deben validarse con la simulación de OpenTrack (`.otsimcor`).
- Las coordenadas de los nodos Netvisio vienen en 0 (OpenTrack no las exportó); el
  layout del grafo se calcula con NetworkX.
- El grafo macroscópico y el microscópico se construyen por separado; la unión por
  estación se hará en la fase de optimización.
