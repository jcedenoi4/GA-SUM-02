"""Verificación de los relojes lógicos de Lamport con los CSV de eventos reales.

Qué hace:
  1. Busca en data/ (y sus subcarpetas) todos los CSV de eventos: los que tienen
     las columnas run_id, message_id, node, peer, event, clock y kind.
  2. Empareja cada envío (send) con su recepción (receive).
  3. Comprueba que, en cada mensaje, el reloj al recibir sea mayor que al enviar.
  4. Reconstruye la relación "ocurrió antes" (->) entre los eventos y cuenta los
     pares de eventos de nodos distintos con el MISMO reloj que son concurrentes.
  5. Guarda los resultados en analysis/resultados/ (CSV y tablas .tex).

Cada archivo se analiza por separado (una corrida = un conjunto). La excepción
es la demo de gRPC, que guardó un CSV por nodo (demo_grpc_nodo-A.csv, ...):
esos archivos se juntan en un solo conjunto.

Las tablas del informe resumen solo la sesión oficial del protocolo
(data/protocolo/sesion_*/), sin las corridas de calentamiento. Los demás
archivos también se verifican y quedan en lamport_por_archivo.csv.

Uso (desde la raíz del repositorio):
    python analysis/verificar_lamport.py
    python analysis/verificar_lamport.py otra/carpeta/de/datos
"""

import re
import sys
from collections import defaultdict, deque
from pathlib import Path

import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parent.parent
CARPETA_DATOS = RAIZ / "data"
CARPETA_SALIDA = RAIZ / "analysis" / "resultados"
COLUMNAS_EVENTOS = {"run_id", "message_id", "node", "peer", "event", "clock", "kind"}

# tcp_100b_concurrente_r01_eventos -> mecanismo, tamaño, modo, fase
PATRON_PROTOCOLO = re.compile(
    r"^(?P<mecanismo>tcp|grpc)_(?P<tamano>100b|10kib)_(?P<modo>secuencial|concurrente)"
    r"_(?P<fase>cal|r\d+)_eventos$"
)
NOMBRE_MECANISMO = {"tcp": "TCP", "grpc": "gRPC"}
NOMBRE_TAMANO = {"100b": "100 B", "10kib": "10 KiB"}


# ---------------------------------------------------------------------------
# Paso 1: cargar los CSV de eventos
# ---------------------------------------------------------------------------
def cargar_conjuntos(carpeta: Path) -> dict[str, pd.DataFrame]:
    """Devuelve {ruta_relativa_del_conjunto: tabla_de_eventos}.

    La clave es la ruta relativa (con la carpeta), para que dos archivos con el
    mismo nombre en carpetas distintas no se mezclen. Solo se quita el sufijo
    _nodo-X, para juntar los CSV por nodo de la demo de gRPC.
    """
    partes = defaultdict(list)
    for ruta in sorted(carpeta.rglob("*.csv")):
        cabecera = set(pd.read_csv(ruta, nrows=0).columns)
        if not COLUMNAS_EVENTOS.issubset(cabecera):
            continue  # es un CSV de latencias, un manifiesto u otro
        relativa = ruta.relative_to(carpeta).with_suffix("").as_posix()
        nombre = re.sub(r"_nodo-[A-Z]$", "", relativa)
        tabla = pd.read_csv(ruta, dtype={"run_id": str, "message_id": str})
        tabla["archivo"] = ruta.name
        partes[nombre].append(tabla)
    return {nombre: pd.concat(lista, ignore_index=True) for nombre, lista in partes.items()}


def describir(nombre: str) -> dict:
    """Saca mecanismo, tamaño, modo y fase del nombre del archivo, si sigue el
    formato del protocolo. Si no, deja 'exploratorio'."""
    base = nombre.split("/")[-1]
    coincide = PATRON_PROTOCOLO.match(base)
    if coincide and nombre.startswith("protocolo/"):
        datos = coincide.groupdict()
        return {
            "origen": "protocolo",
            "mecanismo": NOMBRE_MECANISMO[datos["mecanismo"]],
            "tamano": NOMBRE_TAMANO[datos["tamano"]],
            "modo": datos["modo"],
            "fase": "calentamiento" if datos["fase"] == "cal" else "medida",
        }
    mecanismo = "gRPC" if "grpc" in base.lower() else "TCP"
    return {"origen": "exploratorio", "mecanismo": mecanismo, "tamano": "", "modo": "", "fase": ""}


# ---------------------------------------------------------------------------
# Paso 2: emparejar cada envío con su recepción
# ---------------------------------------------------------------------------
def emparejar(eventos: pd.DataFrame) -> pd.DataFrame:
    """Un send y un receive son el mismo mensaje si coinciden run_id,
    message_id y kind, y el nodo que envía es el 'peer' del que recibe."""
    envios = eventos[eventos["event"] == "send"]
    recepciones = eventos[eventos["event"] == "receive"]
    return envios.merge(
        recepciones,
        left_on=["run_id", "message_id", "kind", "node", "peer"],
        right_on=["run_id", "message_id", "kind", "peer", "node"],
        suffixes=("_env", "_rec"),
    )


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
        orden = eventos_nodo.sort_values("clock", kind="stable").index.tolist()
        for anterior, posterior in zip(orden, orden[1:]):
            siguientes[anterior].append(posterior)
    for id_env, id_rec in zip(pares["id_env"], pares["id_rec"]):
        siguientes[id_env].append(id_rec)
    return siguientes


def matriz_alcance(grafo: dict[int, list[int]], n: int) -> np.ndarray:
    """alcance[a, b] es True si a -> b (desde a se llega a b siguiendo flechas).

    Se recorre el grafo en orden topológico inverso y cada evento hereda los
    alcanzables de sus sucesores. Los conjuntos se guardan como enteros de bits.
    """
    entrantes = [0] * n
    for origen, destinos in grafo.items():
        for destino in destinos:
            entrantes[destino] += 1
    cola = deque(i for i in range(n) if entrantes[i] == 0)
    orden = []
    while cola:
        actual = cola.popleft()
        orden.append(actual)
        for vecino in grafo.get(actual, []):
            entrantes[vecino] -= 1
            if entrantes[vecino] == 0:
                cola.append(vecino)
    if len(orden) != n:
        raise ValueError("El grafo tiene un ciclo: los relojes no son consistentes")

    bits = [0] * n
    for actual in reversed(orden):
        for vecino in grafo.get(actual, []):
            bits[actual] |= (1 << vecino) | bits[vecino]

    alcance = np.zeros((n, n), dtype=bool)
    for i, valor in enumerate(bits):
        if valor:
            fila = np.frombuffer(valor.to_bytes((n + 7) // 8, "little"), dtype=np.uint8)
            alcance[i] = np.unpackbits(fila, bitorder="little")[:n].astype(bool)
    return alcance


def analizar_concurrencia(eventos: pd.DataFrame, grafo) -> tuple[dict, pd.DataFrame]:
    """Cuenta, sobre todos los pares de eventos de nodos distintos:
      - cuántos tienen el mismo reloj y cuántos de esos son concurrentes;
      - cuántos tienen reloj distinto y aun así son concurrentes
        (prueba de que un reloj menor NO implica que un evento causó al otro).
    Devuelve también un ejemplo de par concurrente con el mismo reloj.
    """
    n = len(eventos)
    alcance = matriz_alcance(grafo, n)
    concurrentes = ~(alcance | alcance.T)

    relojes = eventos["clock"].to_numpy()
    nodos = eventos["node"].to_numpy()
    superior = np.triu(np.ones((n, n), dtype=bool), k=1)  # cada par una sola vez
    distinto_nodo = (nodos[:, None] != nodos[None, :]) & superior
    mismo_reloj = relojes[:, None] == relojes[None, :]

    iguales = distinto_nodo & mismo_reloj
    iguales_conc = iguales & concurrentes
    distinto_conc = distinto_nodo & ~mismo_reloj & concurrentes
    conteo = {
        "pares_distinto_nodo": int(distinto_nodo.sum()),
        "iguales_distinto_nodo": int(iguales.sum()),
        "iguales_concurrentes": int(iguales_conc.sum()),
        "reloj_distinto_concurrentes": int(distinto_conc.sum()),
    }

    ejemplo = pd.DataFrame()
    filas, columnas = np.nonzero(iguales_conc)
    if len(filas):
        a, b = eventos.iloc[filas[0]], eventos.iloc[columnas[0]]
        ejemplo = pd.DataFrame([{
            "clock": a["clock"],
            "nodo_1": a["node"], "evento_1": a["event"], "tipo_1": a["kind"], "mensaje_1": a["message_id"],
            "nodo_2": b["node"], "evento_2": b["event"], "tipo_2": b["kind"], "mensaje_2": b["message_id"],
        }])
    return conteo, ejemplo


# ---------------------------------------------------------------------------
# Paso 5: guardar resultados (CSV y tablas LaTeX)
# ---------------------------------------------------------------------------
def tex(texto) -> str:
    return str(texto).replace("_", r"\_")


def miles(numero) -> str:
    """12345 -> '12\\,345' (separador de miles de LaTeX)."""
    return f"{int(numero):,}".replace(",", r"\,")


def escribir_tablas(por_archivo: pd.DataFrame, ejemplos: pd.DataFrame) -> pd.DataFrame:
    medidas = por_archivo[(por_archivo["origen"] == "protocolo") & (por_archivo["fase"] == "medida")]
    if medidas.empty:
        medidas = por_archivo  # sin sesión oficial: se resume todo lo que haya
        claves = ["mecanismo"]
    else:
        claves = ["mecanismo", "tamano", "modo"]
    resumen = (
        medidas.groupby(claves, sort=False)
        .agg(corridas=("conjunto", "count"), eventos=("eventos", "sum"), mensajes=("mensajes", "sum"),
             cumplen=("cumplen", "sum"), fallan=("fallan", "sum"),
             iguales_concurrentes=("iguales_concurrentes", "sum"),
             iguales_distinto_nodo=("iguales_distinto_nodo", "sum"),
             reloj_distinto_concurrentes=("reloj_distinto_concurrentes", "sum"))
        .reset_index()
    )
    resumen.to_csv(CARPETA_SALIDA / "lamport_resumen.csv", index=False)

    encabezado = " & ".join(["Mecanismo", "Carga", "Modo"][: len(claves)])
    lineas = [
        r"\begin{tabular}{" + "l" * len(claves) + "rrrrr}", r"\toprule",
        encabezado + r" & Corridas & Mensajes & Cumplen & Fallan & Iguales y conc. \\",
        r"\midrule",
    ]
    for _, f in resumen.iterrows():
        inicio = " & ".join(str(f[c]) for c in claves)
        lineas.append(
            f"{inicio} & {f['corridas']} & {miles(f['mensajes'])} & {miles(f['cumplen'])} & "
            f"{miles(f['fallan'])} & {miles(f['iguales_concurrentes'])} \\\\"
        )
    lineas += [r"\bottomrule", r"\end{tabular}"]
    (CARPETA_SALIDA / "lamport_resumen.tex").write_text("\n".join(lineas) + "\n", encoding="utf-8")

    lineas = [
        r"\begin{tabular}{lllr}", r"\toprule",
        r"Corrida & Evento 1 & Evento 2 & Reloj \\", r"\midrule",
    ]
    for _, f in ejemplos.iterrows():
        e1 = f"{f['nodo_1']} {f['evento_1']} {f['tipo_1']} {f['mensaje_1']}"
        e2 = f"{f['nodo_2']} {f['evento_2']} {f['tipo_2']} {f['mensaje_2']}"
        lineas.append(f"{tex(f['conjunto'].split('/')[-1])} & {e1} & {e2} & {f['clock']} \\\\")
    lineas += [r"\bottomrule", r"\end{tabular}"]
    (CARPETA_SALIDA / "lamport_ejemplos.tex").write_text("\n".join(lineas) + "\n", encoding="utf-8")
    return resumen


def main() -> int:
    carpeta = Path(sys.argv[1]) if len(sys.argv) > 1 else CARPETA_DATOS
    conjuntos = cargar_conjuntos(carpeta)
    if not conjuntos:
        print(f"No se encontraron CSV de eventos en {carpeta}")
        return 1
    CARPETA_SALIDA.mkdir(parents=True, exist_ok=True)

    filas, todos_pares, ejemplos = [], [], []
    for nombre, eventos in conjuntos.items():
        eventos = eventos.reset_index(drop=True)
        eventos["id"] = eventos.index
        info = describir(nombre)

        pares = verificar_mensajes(emparejar(eventos))
        sin_pareja = len(eventos) - 2 * len(pares)
        conteo, ejemplo = analizar_concurrencia(eventos, construir_grafo(eventos, pares))

        filas.append({
            "conjunto": nombre, **info,
            "eventos": len(eventos), "mensajes": len(pares),
            "cumplen": int(pares["cumple"].sum()), "fallan": int((~pares["cumple"]).sum()),
            "sin_pareja": sin_pareja, **conteo,
        })
        pares.insert(0, "conjunto", nombre)
        todos_pares.append(pares)
        # Un ejemplo por mecanismo y modo, tomado de la primera corrida medida
        if not ejemplo.empty and info["fase"] == "medida" and nombre.endswith("_r01_eventos") \
                and info["tamano"] == "100 B":
            ejemplo.insert(0, "conjunto", nombre)
            ejemplos.append(ejemplo)

        estado = "OK" if pares["cumple"].all() and sin_pareja == 0 else "REVISAR"
        print(f"[{estado}] {nombre}: {int(pares['cumple'].sum())}/{len(pares)} mensajes cumplen, "
              f"sin pareja {sin_pareja}, iguales y concurrentes {conteo['iguales_concurrentes']}")
        for _, f in pares[~pares["cumple"]].iterrows():
            print(f"    FALLA: {f['node_env']}->{f['node_rec']} msg {f['message_id']} "
                  f"({f['kind']}): envío {f['clock_env']}, recepción {f['clock_rec']}")

    por_archivo = pd.DataFrame(filas)
    ejemplos = pd.concat(ejemplos, ignore_index=True) if ejemplos else pd.DataFrame(
        columns=["conjunto", "clock", "nodo_1", "evento_1", "tipo_1", "mensaje_1",
                 "nodo_2", "evento_2", "tipo_2", "mensaje_2"])

    por_archivo.to_csv(CARPETA_SALIDA / "lamport_por_archivo.csv", index=False)
    pd.concat(todos_pares, ignore_index=True).to_csv(CARPETA_SALIDA / "lamport_pares.csv", index=False)
    ejemplos.to_csv(CARPETA_SALIDA / "lamport_ejemplos.csv", index=False)
    resumen = escribir_tablas(por_archivo, ejemplos)

    print("\nResumen de la sesión oficial (corridas medidas):")
    print(resumen.to_string(index=False))
    fallas = int(por_archivo["fallan"].sum())
    sin_pareja = int(por_archivo["sin_pareja"].sum())
    print(f"\nArchivos verificados: {len(por_archivo)} | mensajes: {int(por_archivo['mensajes'].sum())} "
          f"| fallan: {fallas} | eventos sin pareja: {sin_pareja}")
    print("Resultado global: " + ("TODOS los mensajes cumplen" if fallas == 0 and sin_pareja == 0
                                  else "hay mensajes que revisar"))
    print(f"Resultados guardados en {CARPETA_SALIDA}")
    return 0 if fallas == 0 and sin_pareja == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
