"""Nodo TCP y protocolo de mensajes para la práctica."""

import argparse
import csv
import json
import socket
import struct
from datetime import datetime, timezone
from pathlib import Path
from socketserver import BaseRequestHandler, ThreadingTCPServer
from threading import Lock

PORTS = {"nodo-A": 5101, "nodo-B": 5102, "nodo-C": 5103}
EVENT_FIELDS = (
    "run_id", "message_id", "node", "peer", "event", "clock",
    "wall_time_utc", "kind", "payload_bytes",
)
HEADER = struct.Struct("!I")
MAX_FRAME = 1024 * 1024


def read_exact(connection, count):
    data = bytearray()
    while len(data) < count:
        chunk = connection.recv(count - len(data))
        if not chunk:
            if not data:
                return None
            raise EOFError("Trama TCP incompleta")
        data.extend(chunk)
    return data


def send_frame(connection, packet):
    body = json.dumps(packet, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if not 0 < len(body) <= MAX_FRAME:
        raise ValueError("Longitud de trama inválida")
    connection.sendall(HEADER.pack(len(body)) + body)


def receive_frame(connection):
    header = read_exact(connection, HEADER.size)
    if header is None:
        return None
    (length,) = HEADER.unpack(header)
    if not 0 < length <= MAX_FRAME:
        raise ValueError("Longitud de trama inválida")
    body = read_exact(connection, length)
    if body is None:
        raise EOFError("Falta el cuerpo de la trama")
    packet = json.loads(body.decode("utf-8"))
    if (
        not isinstance(packet, dict)
        or not all(isinstance(packet.get(key), str) for key in (
            "sender", "message", "run_id", "message_id", "kind"
        ))
        or packet["sender"] not in PORTS
        or packet["kind"] not in {"request", "response"}
        or type(packet.get("timestamp")) is not int
        or packet["timestamp"] < 1
    ):
        raise ValueError("Mensaje TCP inválido")
    return packet


class Node:
    def __init__(self, name):
        self.name = name
        self.clock = 0
        self.events = []
        self.lock = Lock()

    def record(self, event, peer, packet):
        self.events.append({
            "run_id": packet["run_id"],
            "message_id": packet["message_id"],
            "node": self.name,
            "peer": peer,
            "event": event,
            "clock": self.clock,
            "wall_time_utc": datetime.now(timezone.utc).isoformat(timespec="microseconds"),
            "kind": packet["kind"],
            "payload_bytes": len(packet["message"].encode("utf-8")),
        })

    def send(self, connection, peer, **fields):
        with self.lock:
            self.clock += 1
            packet = {"sender": self.name, "timestamp": self.clock, **fields}
            self.record("send", peer, packet)
        send_frame(connection, packet)

    def receive(self, packet):
        with self.lock:
            self.clock = max(self.clock, packet["timestamp"]) + 1
            self.record("receive", packet["sender"], packet)


class Handler(BaseRequestHandler):
    def handle(self):
        connection = self.request
        connection.settimeout(10)
        connection.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        node = self.server.node
        try:
            while (packet := receive_frame(connection)) is not None:
                if packet["kind"] != "request" or packet["sender"] == node.name:
                    raise ValueError("Se esperaba una solicitud de otro nodo")
                node.receive(packet)
                node.send(
                    connection, packet["sender"], run_id=packet["run_id"],
                    message_id=packet["message_id"], kind="response", message=packet["message"],
                )
        except (OSError, EOFError, ValueError) as error:
            print(f"{node.name}: conexión cerrada ({error})", flush=True)


class NodeServer(ThreadingTCPServer):
    def __init__(self, address, node):
        self.node = node
        super().__init__(address, Handler)


def write_csv(path, fields, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("node", choices=PORTS)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("El archivo de salida ya existe")
    node = Node(args.node)
    with NodeServer((args.host, PORTS[args.node]), node) as server:
        print(f"{node.name} escucha en {args.host}:{PORTS[node.name]}", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
    write_csv(args.output, EVENT_FIELDS, node.events)


if __name__ == "__main__":
    main()
