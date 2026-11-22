"""Ejecuta las corridas del protocolo experimental para TCP y gRPC.

Cada ejecución crea data/protocolo/sesion_<fecha UTC>/ con condiciones.json,
manifiesto.csv y los archivos de cada corrida. Por cada combinación de
mecanismo, tamaño y modo se hace una corrida de calentamiento y luego las
repeticiones medidas. El orden de las combinaciones rota en cada repetición
para que un cambio de carga de la máquina no afecte siempre a la misma

Uso, desde la raíz del repositorio:
    python analysis/ejecutar_protocolo.py --mecanismos tcp grpc
"""

import argparse
import csv
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from itertools import product
from pathlib import Path

from entorno_experimento import condiciones

RAIZ = Path(__file__).resolve().parents[1]

# Ambos programas aceptan --count, --size, --concurrent y --output, escriben
# <prefijo>_eventos*.csv y <prefijo>_latencias.csv e imprimen "Duración: <s> s".
PROGRAMAS = {
    "tcp": RAIZ / "src" / "sockets" / "client.py",
    "grpc": RAIZ / "src" / "grpc" / "lanzador.py",
}
TIPO_EJECUCION = {
    "tcp": "tres nodos en un mismo proceso (servidores en hilos)",
    "grpc": "tres procesos locales",
}
TAMANOS = {100: "100b", 10240: "10kib"}
MODOS = ("secuencial", "concurrente")
PAUSA_S = 1.0
TIEMPO_MAXIMO_S = 300

CAMPOS_MANIFIESTO = (
    "sesion", "orden", "mecanismo", "tamano_bytes", "modo", "fase", "repeticion",
    "envios", "prefijo", "inicio_utc", "fin_utc", "duracion_reportada_s", "estado",
    "tipo_ejecucion",
)
DURACION = re.compile(r"Duración: ([0-9.]+) s")


def planificar(mecanismos, repeticiones):
    combinaciones = list(product(mecanismos, TAMANOS, MODOS))
    plan = [(*combinacion, "calentamiento", 0) for combinacion in combinaciones]
    for repeticion in range(1, repeticiones + 1):
        giro = (repeticion - 1) % len(combinaciones)
        for combinacion in combinaciones[giro:] + combinaciones[:giro]:
            plan.append((*combinacion, "medicion", repeticion))
    return plan


def contar_filas(ruta):
    with ruta.open(encoding="utf-8", newline="") as archivo:
        return sum(1 for _ in csv.DictReader(archivo))


def ejecutar_corrida(sesion, orden, mecanismo, tamano, modo, fase, repeticion, envios):
    """Lanza una corrida y devuelve su fila del manifiesto."""
    sufijo = "cal" if fase == "calentamiento" else f"r{repeticion:02d}"
    prefijo = sesion / f"{mecanismo}_{TAMANOS[tamano]}_{modo}_{sufijo}"
    comando = [sys.executable, str(PROGRAMAS[mecanismo]), "--count", str(envios),
               "--size", str(tamano), "--output", str(prefijo)]
    if modo == "concurrente":
        comando.append("--concurrent")

    # Sin UTF-8, la consola de Windows cambia la "ó" de "Duración" al pasar por la tubería.
    entorno = dict(os.environ, PYTHONIOENCODING="utf-8")
    inicio = datetime.now(timezone.utc)
    try:
        proceso = subprocess.run(comando, cwd=RAIZ, env=entorno, capture_output=True,
                                 encoding="utf-8", errors="replace", timeout=TIEMPO_MAXIMO_S)
        codigo, salida = proceso.returncode, proceso.stdout + proceso.stderr
    except subprocess.TimeoutExpired:
        codigo, salida = None, f"Se agotaron los {TIEMPO_MAXIMO_S} s de espera\n"
    fin = datetime.now(timezone.utc)
    prefijo.with_name(f"{prefijo.name}_salida.txt").write_text(
        " ".join(comando) + "\n\n" + salida, encoding="utf-8")

    latencias = prefijo.with_name(f"{prefijo.name}_latencias.csv")
    duracion = DURACION.search(salida)
    if codigo != 0:
        estado = f"falló con código {codigo}"
    elif not latencias.is_file() or not list(sesion.glob(f"{prefijo.name}_eventos*.csv")):
        estado = "faltan los CSV de eventos o de latencias"
    elif contar_filas(latencias) != envios:
        estado = f"el CSV de latencias no tiene {envios} filas"
    elif duracion is None:
        estado = "el programa no imprimió la duración de la tanda"
    else:
        estado = "ok"

    return {
        "sesion": sesion.name, "orden": orden, "mecanismo": mecanismo,
        "tamano_bytes": tamano, "modo": modo, "fase": fase, "repeticion": repeticion,
        "envios": envios, "prefijo": prefijo.name,
        "inicio_utc": inicio.isoformat(timespec="microseconds"),
        "fin_utc": fin.isoformat(timespec="microseconds"),
        "duracion_reportada_s": duracion.group(1) if duracion else "",
        "estado": estado, "tipo_ejecucion": TIPO_EJECUCION[mecanismo],
    }


def main():
    analizador = argparse.ArgumentParser(description=__doc__,
                                         formatter_class=argparse.RawDescriptionHelpFormatter)
    analizador.add_argument("--mecanismos", nargs="+", choices=PROGRAMAS, default=list(PROGRAMAS))
    analizador.add_argument("--repeticiones", type=int, default=5)
    analizador.add_argument("--envios", type=int, default=100, help="Envíos por corrida")
    analizador.add_argument("--destino", type=Path, default=RAIZ / "data" / "protocolo")
    args = analizador.parse_args()

    if args.repeticiones < 5:
        analizador.error("El protocolo exige al menos 5 repeticiones")
    if args.envios < 1:
        analizador.error("Use un número positivo de envíos")
    for mecanismo in args.mecanismos:
        if not PROGRAMAS[mecanismo].is_file():
            analizador.error(f"No existe {PROGRAMAS[mecanismo].relative_to(RAIZ)}; "
                             "ver la sección 6 de analysis/PROTOCOLO_EXPERIMENTAL.md")

    sesion = args.destino / f"sesion_{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}"
    sesion.mkdir(parents=True)
    datos = condiciones()
    datos["parametros"] = {"mecanismos": args.mecanismos, "repeticiones": args.repeticiones,
                           "envios_por_corrida": args.envios, "pausa_s": PAUSA_S}
    (sesion / "condiciones.json").write_text(
        json.dumps(datos, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    plan = planificar(args.mecanismos, args.repeticiones)
    print(f"{sesion.name}: {len(plan)} corridas de {args.envios} envíos en "
          f"{datos['equipo']} ({datos['usuario']})", flush=True)

    with (sesion / "manifiesto.csv").open("x", encoding="utf-8", newline="") as archivo:
        escritor = csv.DictWriter(archivo, fieldnames=CAMPOS_MANIFIESTO)
        escritor.writeheader()
        for orden, corrida in enumerate(plan, start=1):
            # Da tiempo a que la corrida anterior libere los puertos 5000-5002.
            if orden > 1:
                time.sleep(PAUSA_S)
            fila = ejecutar_corrida(sesion, orden, *corrida, args.envios)
            escritor.writerow(fila)
            archivo.flush()
            print(f"[{orden:02d}/{len(plan)}] {fila['prefijo']:<30} {fila['estado']} "
                  f"{fila['duracion_reportada_s']}", flush=True)
            if fila["estado"] != "ok":
                raise SystemExit(f"Sesión detenida; revise {fila['prefijo']}_salida.txt")

    print(f"Manifiesto: {sesion / 'manifiesto.csv'}")


if __name__ == "__main__":
    main()
