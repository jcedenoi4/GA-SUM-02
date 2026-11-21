"""Rol emisor de un nodo: ejecuta un intercambio y mide el RTT.

El nodo que origina el mensaje aplica el reloj de Lamport, hace una sola llamada
remota y cronometra desde antes de sellar el envío hasta que regresa el acuse.
Así el intervalo medido es equivalente al del cliente TCP del mismo repositorio:
incluye la serialización, el transporte y la decodificación de un único
intercambio de solicitud y respuesta.

También se puede usar como comando contra tres nodos que ya están en marcha, por
ejemplo durante la demostración en clase:

    python src/grpc/cliente.py --desde nodo-A --hasta nodo-B --count 5 --size 100

En ese caso no se escribe ningún CSV: los eventos quedan en los nodos y se
guardan cuando cada uno se detiene con Ctrl+C.
"""

import argparse
import statistics
from time import perf_counter
from uuid import uuid4

import grpc

import lamport_pb2 as pb
import lamport_pb2_grpc as pb_grpc
from nodo import NODOS, PUERTOS


class RespuestaInesperada(ValueError):
    """El acuse no corresponde a la solicitud enviada."""


class ClienteNodo:
    """Emisor de un nodo: mantiene los canales y mide cada intercambio."""

    def __init__(self, nodo, canales, timeout=10.0):
        self.nodo = nodo
        self.canales = dict(canales)
        self.timeout = timeout
        self._stubs = {
            nombre: pb_grpc.NodoLamportStub(canal) for nombre, canal in self.canales.items()
        }

    def preparar(self):
        """Espera a que los canales estén establecidos; queda fuera de la medición."""
        for _nombre, canal in sorted(self.canales.items()):
            grpc.channel_ready_future(canal).result(timeout=self.timeout)
        return len(self.canales)

    def intercambiar(self, destino, run_id, message_id, carga, modo="sequential"):
        """Envía un mensaje, espera el acuse y devuelve la fila de latencia."""
        if destino not in self._stubs:
            raise ValueError(f"Destino desconocido: {destino}")

        inicio = perf_counter()
        sello = self.nodo.sellar_envio(destino, run_id, message_id, "request", carga)
        peticion = pb.Mensaje(
            sender=self.nodo.nombre,
            timestamp=sello,
            message=carga,
            run_id=run_id,
            message_id=message_id,
            kind="request",
        )
        acuse = self._stubs[destino].EnviarMensaje(peticion, timeout=self.timeout)
        terminado = perf_counter()

        self._validar(acuse, destino, run_id, message_id, carga)
        self.nodo.registrar_recibo(acuse.sender, acuse.run_id, acuse.message_id,
                                   acuse.kind, acuse.message, acuse.timestamp)
        return {
            "run_id": run_id,
            "message_id": message_id,
            "sender": self.nodo.nombre,
            "receiver": destino,
            "payload_bytes": len(carga),
            "rtt_ms": f"{(terminado - inicio) * 1000:.6f}",
            "mode": modo,
            "sello_envio": sello,
            "sello_acuse": acuse.timestamp,
        }

    @staticmethod
    def _validar(acuse, destino, run_id, message_id, carga):
        if (
            acuse.sender != destino
            or acuse.run_id != run_id
            or acuse.message_id != message_id
            or acuse.kind != "response"
            or acuse.message != carga
            or not acuse.ok
        ):
            raise RespuestaInesperada(f"Respuesta inesperada para {message_id}")


def main():
    analizador = argparse.ArgumentParser(description=__doc__)
    analizador.add_argument("--desde", required=True, choices=NODOS,
                            help="Nodo que origina el envío (debe estar en marcha)")
    analizador.add_argument("--hasta", required=True, choices=NODOS,
                            help="Nodo que recibe")
    analizador.add_argument("--count", type=int, default=1, help="Cantidad de envíos")
    analizador.add_argument("--size", type=int, default=100, help="Tamaño de la carga en bytes")
    analizador.add_argument("--host", default="127.0.0.1")
    args = analizador.parse_args()

    if args.desde == args.hasta:
        analizador.error("El nodo de origen y el de destino deben ser distintos")
    if args.count < 1 or args.size < 1:
        analizador.error("Use una cantidad y un tamaño positivos")

    canal = grpc.insecure_channel(f"{args.host}:{PUERTOS[args.desde]}")
    control = pb_grpc.ControlNodoStub(canal)
    tiempos = []
    try:
        control.Preparar(pb.Vacio(), timeout=20)
        run_id = uuid4().hex
        print(f"{args.desde} -> {args.hasta} | {args.count} envíos de {args.size} B | run_id={run_id}",
              flush=True)
        for indice in range(args.count):
            respuesta = control.Intercambiar(
                pb.Orden(destino=args.hasta, run_id=run_id, message_id=f"{indice + 1:04d}",
                         message="x" * args.size),
                timeout=60,
            )
            tiempos.append(respuesta.rtt_ms)
            print(f"{indice + 1:04d} | sello={respuesta.sello_envio:>3} -> acuse="
                  f"{respuesta.sello_acuse:>3} | {respuesta.rtt_ms:.3f} ms", flush=True)
    except grpc.RpcError as error:
        raise SystemExit(f"Error de gRPC: {error.code().name}: {error.details()}")
    finally:
        canal.close()

    if tiempos:
        ordenados = sorted(tiempos)
        posicion = max(int(round(0.95 * len(ordenados))) - 1, 0)
        print(f"\nresumen: n={len(tiempos)} media={statistics.mean(tiempos):.4f} ms "
              f"mediana={statistics.median(tiempos):.4f} ms p95={ordenados[posicion]:.4f} ms")
    print("Los eventos quedaron en los nodos; se guardan al detenerlos con Ctrl+C.")


if __name__ == "__main__":
    main()
