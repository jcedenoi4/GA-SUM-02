"""Proceso de un nodo gRPC con reloj lógico de Lamport.

Cada nodo es un proceso independiente que escucha en su propio puerto, atiende
las llamadas EnviarMensaje que le llegan y origina las que le ordena el canal de
control. Al detenerse con Ctrl+C (o con la señal de interrupción que envía el
lanzador de experimentos) vuelca sus eventos a CSV.

Uso, desde la raíz del repositorio:

    python src/grpc/server.py --node nodo-A --output data/demo_nodo-A.csv

Para la demostración conviene abrir tres consolas y añadir --verbose a las tres.
"""

import argparse
import signal
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event

import grpc

import lamport_pb2 as pb
import lamport_pb2_grpc as pb_grpc
from cliente import ClienteNodo, RespuestaInesperada
from entorno import banner, condiciones
from nodo import NODOS, PUERTOS, MensajeInvalido, Nodo, validar_solicitud


class ServicioNodo(pb_grpc.NodoLamportServicer):
    """Servicio del enunciado: recibe el mensaje y responde con un acuse."""

    def __init__(self, nodo, verboso=False):
        self.nodo = nodo
        self.verboso = verboso

    def EnviarMensaje(self, peticion, contexto):
        try:
            validar_solicitud(peticion, self.nodo.nombre)
        except MensajeInvalido as error:
            contexto.abort(grpc.StatusCode.INVALID_ARGUMENT, str(error))
            return None

        self.nodo.registrar_recibo(peticion.sender, peticion.run_id, peticion.message_id,
                                   peticion.kind, peticion.message, peticion.timestamp)
        sello = self.nodo.sellar_envio(peticion.sender, peticion.run_id, peticion.message_id,
                                       "response", peticion.message)
        acuse = pb.Acuse(
            sender=self.nodo.nombre,
            timestamp=sello,
            message=peticion.message,
            run_id=peticion.run_id,
            message_id=peticion.message_id,
            kind="response",
            ok=True,
        )
        if self.verboso:
            print(f"{self.nodo.nombre} | {peticion.message_id} | recibe de {peticion.sender} "
                  f"sello={peticion.timestamp} -> acuse sello={sello} | "
                  f"carga={len(peticion.message)} B", flush=True)
        return acuse


class ServicioControl(pb_grpc.ControlNodoServicer):
    """Canal de control: ordena los envíos y devuelve el RTT medido en el nodo."""

    def __init__(self, cliente, verboso=False):
        self.cliente = cliente
        self.verboso = verboso

    def Preparar(self, peticion, contexto):
        try:
            listos = self.cliente.preparar()
        except grpc.FutureTimeoutError:
            contexto.abort(grpc.StatusCode.UNAVAILABLE, "Los canales hacia los otros nodos no se establecieron")
            return None
        return pb.EstadoListo(listo=True, detalle=f"{listos} canales establecidos")

    def Intercambiar(self, orden, contexto):
        try:
            fila = self.cliente.intercambiar(orden.destino, orden.run_id, orden.message_id, orden.message)
        except RespuestaInesperada as error:
            contexto.abort(grpc.StatusCode.FAILED_PRECONDITION, str(error))
            return None
        except ValueError as error:
            contexto.abort(grpc.StatusCode.INVALID_ARGUMENT, str(error))
            return None
        except grpc.RpcError as error:
            contexto.abort(error.code(), error.details())
            return None
        if self.verboso:
            print(f"{fila['sender']} -> {fila['receiver']} | {fila['message_id']} | "
                  f"sello={fila['sello_envio']} | acuse={fila['sello_acuse']} | "
                  f"{float(fila['rtt_ms']):.3f} ms", flush=True)
        return pb.Resultado(
            ok=True,
            rtt_ms=float(fila["rtt_ms"]),
            sello_envio=fila["sello_envio"],
            sello_acuse=fila["sello_acuse"],
        )


def main():
    analizador = argparse.ArgumentParser(description=__doc__)
    analizador.add_argument("--node", required=True, choices=NODOS, help="Nombre del nodo")
    analizador.add_argument("--host", default="127.0.0.1")
    analizador.add_argument("--port", type=int, default=None,
                            help="Puerto; por omisión 5000, 5001 o 5002 según el nodo")
    analizador.add_argument("--output", type=Path, required=True,
                            help="CSV de eventos; no debe existir")
    analizador.add_argument("--verbose", action="store_true",
                            help="Imprime cada intercambio (solo para demostraciones)")
    args = analizador.parse_args()

    if args.output.exists():
        analizador.error("El archivo de salida ya existe")
    puerto = args.port if args.port is not None else PUERTOS[args.node]
    direccion = f"{args.host}:{puerto}"

    nodo = Nodo(args.node)
    canales = {
        nombre: grpc.insecure_channel(f"{args.host}:{PUERTOS[nombre]}")
        for nombre in NODOS if nombre != args.node
    }
    cliente = ClienteNodo(nodo, canales)

    servidor = grpc.server(ThreadPoolExecutor(max_workers=8))
    pb_grpc.add_NodoLamportServicer_to_server(ServicioNodo(nodo, args.verbose), servidor)
    pb_grpc.add_ControlNodoServicer_to_server(ServicioControl(cliente, args.verbose), servidor)
    if servidor.add_insecure_port(direccion) != puerto:
        raise SystemExit(f"No se pudo abrir {direccion}")

    servidor.start()
    print(banner(args.node), flush=True)
    print(f"{args.node} escucha en {direccion} (gRPC sobre HTTP/2, Protocol Buffers)", flush=True)
    if args.verbose:
        print("condiciones: " + " | ".join(f"{clave}={valor}" for clave, valor in condiciones().items()),
              flush=True)

    detener = Event()

    def atender_senal(_numero, _marco):
        detener.set()

    signal.signal(signal.SIGINT, atender_senal)
    if hasattr(signal, "SIGBREAK"):
        signal.signal(signal.SIGBREAK, atender_senal)

    try:
        while not detener.wait(0.25):
            pass
    finally:
        servidor.stop(0).wait()
        for canal in canales.values():
            canal.close()
        filas = nodo.volcar_csv(args.output)
        print(f"{args.node}: {filas} eventos -> {args.output}", flush=True)


if __name__ == "__main__":
    main()
