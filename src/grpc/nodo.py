"""Reloj lógico de Lamport y registro de eventos de un nodo gRPC.

Las dos reglas del reloj son las mismas que usa el transporte TCP del mismo
repositorio, para que los registros de ambos mecanismos se puedan comparar:

    al enviar:    L = L + 1
    al recibir:   L = max(L, T) + 1,  donde T es el sello del mensaje recibido

Cada nodo tiene un solo reloj, aunque cumpla dos papeles: atiende las llamadas
que le llegan y origina las que le ordena el canal de control. El reloj, el
registro de eventos y el volcado a CSV viven en este módulo; la escritura queda
fuera del camino que se mide, para no sumar acceso a disco a la latencia.
"""

import csv
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock

NODOS = ("nodo-A", "nodo-B", "nodo-C")
PUERTOS = {"nodo-A": 5000, "nodo-B": 5001, "nodo-C": 5002}

EVENT_FIELDS = (
    "run_id", "message_id", "node", "peer", "event", "clock",
    "wall_time_utc", "kind", "payload_bytes",
)


class MensajeInvalido(ValueError):
    """La solicitud recibida no cumple el contrato del servicio."""


def validar_solicitud(mensaje, nombre_nodo):
    """Comprueba que la solicitud venga de otro nodo y tenga los campos esperados."""
    if mensaje.sender not in NODOS:
        raise MensajeInvalido(f"Emisor desconocido: {mensaje.sender!r}")
    if mensaje.sender == nombre_nodo:
        raise MensajeInvalido("Un nodo no se envía mensajes a sí mismo")
    if mensaje.kind != "request":
        raise MensajeInvalido(f"Se esperaba una solicitud, llegó {mensaje.kind!r}")
    if mensaje.timestamp < 1:
        raise MensajeInvalido("El sello lógico debe ser mayor o igual que 1")
    if not mensaje.run_id or not mensaje.message_id:
        raise MensajeInvalido("Falta run_id o message_id")


class Nodo:
    """Nodo con un único reloj de Lamport, registro de eventos y volcado a CSV."""

    def __init__(self, nombre):
        if nombre not in NODOS:
            raise ValueError(f"Nodo desconocido: {nombre}")
        self.nombre = nombre
        self._reloj = 0
        self._eventos = []
        self._candado = Lock()

    @property
    def reloj(self):
        return self._reloj

    def _anotar(self, evento, peer, run_id, message_id, kind, carga):
        self._eventos.append({
            "run_id": run_id,
            "message_id": message_id,
            "node": self.nombre,
            "peer": peer,
            "event": evento,
            "clock": self._reloj,
            "wall_time_utc": datetime.now(timezone.utc).isoformat(timespec="microseconds"),
            "kind": kind,
            "payload_bytes": len(carga.encode("utf-8")),
        })

    def sellar_envio(self, peer, run_id, message_id, kind, carga):
        """Aplica L = L + 1, anota el envío y devuelve el sello que viaja."""
        with self._candado:
            self._reloj += 1
            self._anotar("send", peer, run_id, message_id, kind, carga)
            return self._reloj

    def registrar_recibo(self, peer, run_id, message_id, kind, carga, sello_remoto):
        """Aplica L = max(L, T) + 1 y anota la recepción."""
        with self._candado:
            self._reloj = max(self._reloj, int(sello_remoto)) + 1
            self._anotar("receive", peer, run_id, message_id, kind, carga)
            return self._reloj

    @property
    def eventos(self):
        with self._candado:
            return list(self._eventos)

    def volcar_csv(self, ruta):
        """Escribe los eventos del nodo. Falla si el archivo ya existe."""
        ruta = Path(ruta)
        ruta.parent.mkdir(parents=True, exist_ok=True)
        with self._candado:
            with ruta.open("x", encoding="utf-8", newline="") as salida:
                escritor = csv.DictWriter(salida, fieldnames=EVENT_FIELDS)
                escritor.writeheader()
                escritor.writerows(self._eventos)
            return len(self._eventos)
