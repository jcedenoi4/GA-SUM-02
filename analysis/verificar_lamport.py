"""Verificación de los relojes lógicos de Lamport con los CSV de eventos reales.

Qué hace:
  1. Busca en data/ todos los CSV de eventos (los que tienen las columnas
     run_id, message_id, node, peer, event, clock y kind).
  2. Empareja cada envío (send) con su recepción (receive).
  3. Comprueba que, en cada mensaje, el reloj al recibir sea mayor que al enviar.
  4. Reconstruye la relación "ocurrió antes" (->) entre eventos y busca eventos
     de nodos distintos con el MISMO reloj que son concurrentes.
  5. Guarda los resultados en analysis/resultados/ (CSV y tablas .tex).

Uso (desde la raíz del repositorio):
    python analysis/verificar_lamport.py
    python analysis/verificar_lamport.py otra/carpeta/de/datos
"""

import re
import sys
from collections import defaultdict, deque
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


# ---------------------------------------------------------------------------
# Paso 4: relación "ocurrió antes" y eventos concurrentes
# ---------------------------------------------------------------------------
def construir_grafo(eventos: pd.DataFrame, pares: pd.DataFrame) -> dict[int, list[int]]:
    """Grafo de la relación 'ocurrió antes' (Lamport, 1978):
      - dentro de un mismo nodo, cada evento va antes que el siguiente
        (se ordenan por reloj, que en un nodo siempre crece);
      - un envío va antes que la recepción del mismo mensaje.
    """
    siguientes = defaultdict(list)
    for _, eventos_nodo in eventos.groupby("node"):
        orden = eventos_nodo.sort_values("clock").index.tolist()
        for anterior, posterior in zip(orden, orden[1:]):
            siguientes[anterior].append(posterior)
    for _, par in pares.iterrows():
        siguientes[par["id_env"]].append(par["id_rec"])
    return siguientes


def alcanzables(grafo: dict[int, list[int]], inicio: int) -> set[int]:
    """Todos los eventos a los que se llega desde 'inicio' (búsqueda en anchura)."""
    vistos, cola = set(), deque([inicio])
    while cola:
        actual = cola.popleft()
        for vecino in grafo.get(actual, []):
            if vecino not in vistos:
                vistos.add(vecino)
                cola.append(vecino)
    return vistos


def buscar_concurrentes(eventos: pd.DataFrame, grafo) -> tuple[pd.DataFrame, int, int]:
    """Devuelve:
      - pares de eventos de nodos distintos con el mismo reloj, indicando si son
        concurrentes (ninguno ocurrió antes que el otro);
      - cuántos pares con reloj distinto son, aun así, concurrentes
        (prueba de que un reloj menor NO implica que un evento causó al otro);
      - cuántos pares de eventos se revisaron en total.
    """
    despues_de = {i: alcanzables(grafo, i) for i in eventos.index}

    def concurrentes(a, b):
        return b not in despues_de[a] and a not in despues_de[b]

    filas = []
    for reloj, grupo in eventos.groupby("clock"):
        ids = grupo.index.tolist()
        for i, a in enumerate(ids):
            for b in ids[i + 1:]:
                if eventos.at[a, "node"] == eventos.at[b, "node"]:
                    continue
                filas.append({
                    "clock": reloj,
                    "nodo_1": eventos.at[a, "node"], "evento_1": eventos.at[a, "event"],
                    "mensaje_1": eventos.at[a, "message_id"], "tipo_1": eventos.at[a, "kind"],
                    "nodo_2": eventos.at[b, "node"], "evento_2": eventos.at[b, "event"],
                    "mensaje_2": eventos.at[b, "message_id"], "tipo_2": eventos.at[b, "kind"],
                    "concurrentes": concurrentes(a, b),
                })

    ids = eventos.index.tolist()
    total, menor_pero_concurrente = 0, 0
    for i, a in enumerate(ids):
        for b in ids[i + 1:]:
            total += 1
            if eventos.at[a, "clock"] != eventos.at[b, "clock"] and concurrentes(a, b):
                menor_pero_concurrente += 1
    return pd.DataFrame(filas), menor_pero_concurrente, total


# ---------------------------------------------------------------------------
# Paso 5: guardar resultados (CSV y tablas LaTeX)
# ---------------------------------------------------------------------------
def tex(texto) -> str:
    return str(texto).replace("_", r"\_")


def escribir_tablas(resumen: pd.DataFrame, ejemplos: pd.DataFrame) -> None:
    lineas = [
        r"\begin{tabular}{llrrrrr}", r"\toprule",
        r"Conjunto & Mecanismo & Eventos & Mensajes & Cumplen & Fallan & Iguales conc. \\",
        r"\midrule",
    ]
    for _, f in resumen.iterrows():
        lineas.append(
            f"{tex(f['conjunto'])} & {f['mecanismo']} & {f['eventos']} & {f['mensajes']} & "
            f"{f['cumplen']} & {f['fallan']} & {f['iguales_concurrentes']} \\\\"
        )
    lineas += [r"\bottomrule", r"\end{tabular}"]
    (CARPETA_SALIDA / "lamport_resumen.tex").write_text("\n".join(lineas) + "\n", encoding="utf-8")

    lineas = [
        r"\begin{tabular}{lrll}", r"\toprule",
        r"Conjunto & Reloj & Evento 1 & Evento 2 \\", r"\midrule",
    ]
    for _, f in ejemplos.iterrows():
        e1 = f"{f['nodo_1']} {f['evento_1']} {f['tipo_1']} {f['mensaje_1']}"
        e2 = f"{f['nodo_2']} {f['evento_2']} {f['tipo_2']} {f['mensaje_2']}"
        lineas.append(f"{tex(f['conjunto'])} & {f['clock']} & {tex(e1)} & {tex(e2)} \\\\")
    lineas += [r"\bottomrule", r"\end{tabular}"]
    (CARPETA_SALIDA / "lamport_ejemplos.tex").write_text("\n".join(lineas) + "\n", encoding="utf-8")


def main() -> int:
    carpeta = Path(sys.argv[1]) if len(sys.argv) > 1 else CARPETA_DATOS
    conjuntos = cargar_conjuntos(carpeta)
    if not conjuntos:
        print(f"No se encontraron CSV de eventos en {carpeta}")
        return 1
    CARPETA_SALIDA.mkdir(parents=True, exist_ok=True)

    resumen, todos_pares, ejemplos = [], [], []
    for nombre, eventos in conjuntos.items():
        eventos = eventos.reset_index(drop=True)
        eventos["id"] = eventos.index

        pares = verificar_mensajes(emparejar(eventos))
        sin_pareja = len(eventos) - 2 * len(pares)
        grafo = construir_grafo(eventos, pares)
        iguales, menor_conc, total = buscar_concurrentes(eventos, grafo)

        n_iguales = len(iguales)
        n_iguales_conc = int(iguales["concurrentes"].sum()) if n_iguales else 0
        resumen.append({
            "conjunto": nombre, "mecanismo": mecanismo(nombre),
            "eventos": len(eventos), "mensajes": len(pares),
            "cumplen": int(pares["cumple"].sum()), "fallan": int((~pares["cumple"]).sum()),
            "sin_pareja": sin_pareja,
            "iguales_distinto_nodo": n_iguales, "iguales_concurrentes": n_iguales_conc,
            "reloj_distinto_pero_concurrentes": menor_conc, "pares_revisados": total,
        })
        pares.insert(0, "conjunto", nombre)
        todos_pares.append(pares)
        if n_iguales_conc:
            ejemplo = iguales[iguales["concurrentes"]].iloc[[0]].copy()
            ejemplo.insert(0, "conjunto", nombre)
            ejemplos.append(ejemplo)

        print(f"\n=== {nombre} ({mecanismo(nombre)}) ===")
        print(f"Eventos: {len(eventos)} | mensajes emparejados: {len(pares)} | sin pareja: {sin_pareja}")
        print(f"Reloj recepción > reloj envío: {int(pares['cumple'].sum())} de {len(pares)}")
        for _, f in pares[~pares["cumple"]].iterrows():
            print(f"  FALLA: {f['node_env']}->{f['node_rec']} msg {f['message_id']} "
                  f"({f['kind']}): envío {f['clock_env']}, recepción {f['clock_rec']}")
        print(f"Pares de nodos distintos con el mismo reloj: {n_iguales} "
              f"(concurrentes: {n_iguales_conc})")
        print(f"Pares con reloj distinto pero concurrentes: {menor_conc} de {total}")
        if n_iguales_conc:
            f = iguales[iguales["concurrentes"]].iloc[0]
            print(f"  Ejemplo: reloj {f['clock']} -> {f['nodo_1']} {f['evento_1']} "
                  f"{f['tipo_1']} {f['mensaje_1']}  y  {f['nodo_2']} {f['evento_2']} "
                  f"{f['tipo_2']} {f['mensaje_2']}")

    resumen = pd.DataFrame(resumen)
    ejemplos = pd.concat(ejemplos, ignore_index=True) if ejemplos else pd.DataFrame()
    resumen.to_csv(CARPETA_SALIDA / "lamport_resumen.csv", index=False)
    pd.concat(todos_pares, ignore_index=True).to_csv(CARPETA_SALIDA / "lamport_pares.csv", index=False)
    if not ejemplos.empty:
        ejemplos.to_csv(CARPETA_SALIDA / "lamport_ejemplos.csv", index=False)
    escribir_tablas(resumen, ejemplos)

    fallas = int(resumen["fallan"].sum())
    print(f"\nResultado global: {'TODOS los mensajes cumplen' if fallas == 0 else f'{fallas} mensajes fallan'}")
    print(f"Resultados guardados en {CARPETA_SALIDA}")
    return 0 if fallas == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
