"""Verificación de los relojes lógicos de Lamport con los CSV de eventos reales.

Qué hace:
  1. Busca en data/ todos los CSV de eventos (los que tienen las columnas
     run_id, message_id, node, peer, event, clock y kind).
  2. Empareja cada envío (send) con su recepción (receive).
  3. Comprueba que, en cada mensaje, el reloj al recibir sea mayor que al enviar.
  4. Guarda los resultados en analysis/resultados/ (CSV).

Uso (desde la raíz del repositorio):
    python analysis/verificar_lamport.py
    python analysis/verificar_lamport.py otra/carpeta/de/datos
"""

import re
import sys
from collections import defaultdict
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parent.parent
CARPETA_DATOS = RAIZ / "data"
CARPETA_SALIDA = RAIZ / "analysis" / "resultados"
COLUMNAS_EVENTOS = {"run_id", "message_id", "node", "peer", "event", "clock", "kind"}


# ---------------------------------------------------------------------------
# Paso 1: cargar los CSV de eventos
# ---------------------------------------------------------------------------
def cargar_conjuntos(carpeta: Path) -> dict[str, pd.DataFrame]:
    """Devuelve {nombre_del_conjunto: tabla_de_eventos}.

    TCP guarda un solo CSV con los tres nodos; gRPC guarda un CSV por nodo
    (..._nodo-A.csv, ..._nodo-B.csv, ..._nodo-C.csv). Por eso se quita el
    sufijo _nodo-X del nombre y se juntan los archivos que quedan iguales.
    """
    partes = defaultdict(list)
    for ruta in sorted(carpeta.rglob("*.csv")):
        cabecera = set(pd.read_csv(ruta, nrows=0).columns)
        if not COLUMNAS_EVENTOS.issubset(cabecera):
            continue  # es un CSV de latencias u otro, no de eventos
        nombre = re.sub(r"_nodo-[A-Z]$", "", ruta.stem)
        tabla = pd.read_csv(ruta, dtype={"run_id": str, "message_id": str})
        tabla["archivo"] = ruta.name
        partes[nombre].append(tabla)
    return {nombre: pd.concat(lista, ignore_index=True) for nombre, lista in partes.items()}


def mecanismo(nombre: str) -> str:
    return "gRPC" if "grpc" in nombre.lower() else "TCP"


# ---------------------------------------------------------------------------
# Paso 2: emparejar cada envío con su recepción
# ---------------------------------------------------------------------------
def emparejar(eventos: pd.DataFrame) -> pd.DataFrame:
    """Un send y un receive son el mismo mensaje si coinciden run_id,
    message_id y kind, y el nodo que envía es el 'peer' del que recibe."""
    envios = eventos[eventos["event"] == "send"]
    recepciones = eventos[eventos["event"] == "receive"]
    pares = envios.merge(
        recepciones,
        left_on=["run_id", "message_id", "kind", "node", "peer"],
        right_on=["run_id", "message_id", "kind", "peer", "node"],
        suffixes=("_env", "_rec"),
    )
    return pares


# ---------------------------------------------------------------------------
# Paso 3: comprobar la condición de Lamport en cada mensaje
# ---------------------------------------------------------------------------
def verificar_mensajes(pares: pd.DataFrame) -> pd.DataFrame:
    pares = pares.copy()
    pares["cumple"] = pares["clock_rec"] > pares["clock_env"]
    return pares


def main() -> int:
    carpeta = Path(sys.argv[1]) if len(sys.argv) > 1 else CARPETA_DATOS
    conjuntos = cargar_conjuntos(carpeta)
    if not conjuntos:
        print(f"No se encontraron CSV de eventos en {carpeta}")
        return 1
    CARPETA_SALIDA.mkdir(parents=True, exist_ok=True)

    resumen, todos_pares = [], []
    for nombre, eventos in conjuntos.items():
        eventos = eventos.reset_index(drop=True)
        eventos["id"] = eventos.index

        pares = verificar_mensajes(emparejar(eventos))
        sin_pareja = len(eventos) - 2 * len(pares)
        resumen.append({
            "conjunto": nombre, "mecanismo": mecanismo(nombre),
            "eventos": len(eventos), "mensajes": len(pares),
            "cumplen": int(pares["cumple"].sum()), "fallan": int((~pares["cumple"]).sum()),
            "sin_pareja": sin_pareja,
        })
        pares.insert(0, "conjunto", nombre)
        todos_pares.append(pares)

        print(f"\n=== {nombre} ({mecanismo(nombre)}) ===")
        print(f"Eventos: {len(eventos)} | mensajes emparejados: {len(pares)} | sin pareja: {sin_pareja}")
        print(f"Reloj recepción > reloj envío: {int(pares['cumple'].sum())} de {len(pares)}")
        for _, f in pares[~pares["cumple"]].iterrows():
            print(f"  FALLA: {f['node_env']}->{f['node_rec']} msg {f['message_id']} "
                  f"({f['kind']}): envío {f['clock_env']}, recepción {f['clock_rec']}")

    resumen = pd.DataFrame(resumen)
    resumen.to_csv(CARPETA_SALIDA / "lamport_resumen.csv", index=False)
    pd.concat(todos_pares, ignore_index=True).to_csv(CARPETA_SALIDA / "lamport_pares.csv", index=False)

    fallas = int(resumen["fallan"].sum())
    print(f"\nResultado global: {'TODOS los mensajes cumplen' if fallas == 0 else f'{fallas} mensajes fallan'}")
    print(f"Resultados guardados en {CARPETA_SALIDA}")
    return 0 if fallas == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
