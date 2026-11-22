"""Ejecuta una corrida de intercambios entre los tres nodos gRPC.

Levanta tres procesos (nodo-A en 5000, nodo-B en 5001, nodo-C en 5002), espera
a que los canales estén establecidos, ordena los envíos por el canal de control,
detiene los nodos y reúne sus registros en un CSV de eventos y otro de latencias.

Uso, desde la raíz del repositorio:

    python src/grpc/experimento.py --count 20 --size 100 --output data/grpc_20_100b
    python src/grpc/experimento.py --count 100 --size 10240 --output data/grpc_100_10kib_r1
    python src/grpc/experimento.py --count 102 --size 10240 --concurrent --output data/grpc_concurrente_10kib_r1
"""

import argparse
import csv
import shutil
import signal
import socket
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from threading import Barrier
from time import perf_counter
from uuid import uuid4

import grpc

import lamport_pb2 as pb
import lamport_pb2_grpc as pb_grpc
from entorno import condiciones
from nodo import EVENT_FIELDS, NODOS, PUERTOS

RAIZ = Path(__file__).resolve().parents[2]
RUTAS = (("nodo-A", "nodo-B"), ("nodo-B", "nodo-C"), ("nodo-C", "nodo-A"))
LATENCY_FIELDS = (
    "run_id", "message_id", "sender", "receiver", "payload_bytes", "rtt_ms", "mode",
)


def etiqueta_tamano(tamano):
    return f"{tamano}b" if tamano < 1024 else f"{tamano // 1024}kib"


def esperar_puerto(puerto, limite=30.0):
    fin = perf_counter() + limite
    while perf_counter() < fin:
        try:
            with socket.create_connection(("127.0.0.1", puerto), timeout=0.2):
                return
        except OSError:
            time.sleep(0.05)
    raise RuntimeError(f"El puerto {puerto} no se abrió en {limite:.0f} s")


class TresNodos:
    """Los tres procesos nodo mientras dura una corrida."""

    def __init__(self, host, verboso, directorio):
        self.host = host
        self.verboso = verboso
        self.directorio = Path(directorio)
        self.procesos = {}
        self.salidas = {}

    def iniciar(self):
        shutil.rmtree(self.directorio, ignore_errors=True)
        self.directorio.mkdir(parents=True, exist_ok=True)
        if any(self.directorio.glob("*.csv")):
            raise RuntimeError(f"No se pudieron limpiar los CSV previos en {self.directorio}")

        for nombre in NODOS:
            salida = self.directorio / f"{nombre}.csv"
            orden = [sys.executable, str(RAIZ / "src" / "grpc" / "server.py"),
                     "--node", nombre, "--output", str(salida)]
            if self.verboso:
                orden.append("--verbose")
            self.procesos[nombre] = subprocess.Popen(
                orden, cwd=RAIZ,
                stdout=None if self.verboso else subprocess.DEVNULL,
                stderr=None if self.verboso else subprocess.DEVNULL,
                creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
            )
            self.salidas[nombre] = salida

        for nombre, puerto in PUERTOS.items():
            esperar_puerto(puerto)
            proceso = self.procesos[nombre]
            if proceso.poll() is not None:
                raise RuntimeError(
                    f"{nombre} terminó al arrancar con código {proceso.returncode}; "
                    "revise el puerto ocupado o el archivo de salida"
                )

    def detener(self):
        for proceso in self.procesos.values():
            if proceso.poll() is not None:
                continue
            try:
                if hasattr(signal, "CTRL_BREAK_EVENT"):
                    proceso.send_signal(signal.CTRL_BREAK_EVENT)
                else:
                    proceso.terminate()
            except (OSError, ValueError):
                proceso.terminate()
        for nombre, proceso in self.procesos.items():
            try:
                proceso.wait(timeout=30)
            except subprocess.TimeoutExpired:
                proceso.kill()
                proceso.wait(timeout=10)
                raise RuntimeError(f"{nombre} no se detuvo a tiempo")

    def eventos(self):
        filas = []
        for nombre in NODOS:
            ruta = self.salidas[nombre]
            if not ruta.is_file():
                raise RuntimeError(f"{nombre} no escribió su CSV de eventos")
            with ruta.open(encoding="utf-8") as archivo:
                filas.extend(csv.DictReader(archivo))
        return filas


def escribir_csv(ruta, campos, filas):
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with ruta.open("x", encoding="utf-8", newline="") as salida:
        escritor = csv.DictWriter(salida, fieldnames=campos)
        escritor.writeheader()
        escritor.writerows(filas)


def sesion(control, envios, tamano, run_id, modo, concurrente):
    """Ejecuta los envíos y devuelve las filas de latencia."""
    carga = "x" * tamano

    def un_envio(indice, ruta, barrera):
        emisor, destino = ruta
        if barrera is not None:
            barrera.wait(timeout=10)
        identificador = f"{indice + 1:04d}"
        respuesta = control[emisor].Intercambiar(
            pb.Orden(destino=destino, run_id=run_id, message_id=identificador, message=carga),
            timeout=60,
        )
        return {
            "run_id": run_id,
            "message_id": identificador,
            "sender": emisor,
            "receiver": destino,
            "payload_bytes": tamano,
            "rtt_ms": f"{respuesta.rtt_ms:.6f}",
            "mode": modo,
        }

    filas = []
    if not concurrente:
        for indice in range(envios):
            filas.append(un_envio(indice, RUTAS[indice % len(RUTAS)], None))
        return filas

    barrera = None
    with ThreadPoolExecutor(max_workers=len(RUTAS)) as grupo:
        for inicio in range(0, envios, len(RUTAS)):
            lote = RUTAS[:envios - inicio]
            barrera = Barrier(len(lote), timeout=10)
            trabajos = [grupo.submit(un_envio, inicio + posicion, ruta, barrera)
                        for posicion, ruta in enumerate(lote)]
            filas.extend(trabajo.result() for trabajo in trabajos)
    return filas


def ejecutar(prefijo, envios, tamano, concurrente=False, host="127.0.0.1",
             verboso=False, repeticion=1, etiqueta="medicion"):
    """Corre una tanda completa y deja los dos CSV. Devuelve sus metadatos."""
    prefijo = Path(prefijo)
    eventos_ruta = prefijo.with_name(f"{prefijo.name}_eventos.csv")
    latencias_ruta = prefijo.with_name(f"{prefijo.name}_latencias.csv")
    if eventos_ruta.exists() or latencias_ruta.exists():
        raise FileExistsError(f"Ya existen archivos para el prefijo {prefijo.name}")

    run_id = uuid4().hex
    modo = "concurrent" if concurrente else "sequential"
    directorio = prefijo.parent / "_nodos" / prefijo.name
    nodos = TresNodos(host, verboso, directorio)
    canales = {}
    try:
        nodos.iniciar()
        canales = {nombre: grpc.insecure_channel(f"{host}:{PUERTOS[nombre]}") for nombre in NODOS}
        control = {nombre: pb_grpc.ControlNodoStub(canal) for nombre, canal in canales.items()}
        for nombre, stub in control.items():
            estado = stub.Preparar(pb.Vacio(), timeout=30)
            if not estado.listo:
                raise RuntimeError(f"{nombre} no quedó listo: {estado.detalle}")

        inicio = perf_counter()
        filas = sesion(control, envios, tamano, run_id, modo, concurrente)
        duracion = perf_counter() - inicio
    finally:
        nodos.detener()
        for canal in canales.values():
            canal.close()

    eventos = nodos.eventos()
    escribir_csv(eventos_ruta, EVENT_FIELDS, eventos)
    escribir_csv(latencias_ruta, LATENCY_FIELDS, filas)

    esperados = envios * 4
    if len(eventos) != esperados:
        raise RuntimeError(f"Se esperaban {esperados} eventos y se registraron {len(eventos)}")

    shutil.rmtree(directorio, ignore_errors=True)

    meta = {
        "etiqueta": etiqueta,
        "prefijo": prefijo.name,
        "mecanismo": "gRPC",
        "modo": modo,
        "envios": envios,
        "tamano_b": tamano,
        "repeticion": repeticion,
        "duracion_s": round(duracion, 6),
        "eventos": len(eventos),
        "fecha_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    meta.update(condiciones())
    return meta


def main():
    analizador = argparse.ArgumentParser(description=__doc__)
    analizador.add_argument("--count", type=int, default=20, help="Cantidad de envíos")
    analizador.add_argument("--size", type=int, default=100,
                            help="Tamaño de la carga en bytes (el protocolo usa 100 y 10240)")
    analizador.add_argument("--concurrent", action="store_true",
                            help="Tres clientes enviando a la vez")
    analizador.add_argument("--output", type=Path, required=True,
                            help="Prefijo de los archivos CSV")
    analizador.add_argument("--host", default="127.0.0.1")
    analizador.add_argument("--verbose", action="store_true",
                            help="Muestra la salida de los tres nodos")
    args = analizador.parse_args()

    if args.count < 1:
        analizador.error("Use un conteo positivo")

    try:
        meta = ejecutar(args.output, args.count, args.size, args.concurrent, args.host, args.verbose)
    except FileExistsError as error:
        analizador.error(str(error))

    print(f"Duración: {meta['duracion_s']:.6f} s | {meta['envios']} intercambios | "
          f"{meta['tamano_b']} B | {meta['modo']} | {meta['eventos']} eventos")
    print(f"Eventos: {args.output.name}_eventos.csv")
    print(f"Latencias: {args.output.name}_latencias.csv")


if __name__ == "__main__":
    main()
